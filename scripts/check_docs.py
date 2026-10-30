#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档 ↔ 代码 交叉引用检查。

改 A 处忘了 B 处，是这个 skill 最容易犯的错（v2.5.1 一次审计就抓出 6 处）。
这个脚本把那些「写死在文档里的数字、名字、编号」和代码里的真值对账，
离线可跑，不需要网络。

用法:
    python3 scripts/check_docs.py            # 用 scripts/snapshots/westock.json 快照
    python3 scripts/check_docs.py --refresh  # 重新抓工具/字段快照（需要能连 WeStock）
    python3 scripts/check_docs.py -v         # 打印每条检查项
    python3 scripts/check_docs.py --selftest # 变异测试：故意写错 8 处，确认都抓得到

退出码: 0 = 无错误（警告不算失败），1 = 有错误。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SNAP = SKILL / "scripts" / "snapshots" / "westock.json"
DOCS = ["SKILL.md", "CHANGELOG.md",
        "references/指标体系.md", "references/解读范式.md",
        "references/westock-接口.md", "references/接入WeStock.md"]

sys.path.insert(0, str(SKILL / "scripts"))
from render_report import SECTION_TITLES  # noqa: E402

# 文档里合法出现、但不是接口工具的串（JSON 键、我们自己的字段名）
NOT_A_TOOL = {
    "data_gaps",       # 我们自己的 JSON 键
    "data_valuation",  # 不存在的工具，文档里专门用来说明「没有它」
}

issues: list[tuple[str, str]] = []   # (level, message)


def err(msg: str) -> None:
    issues.append(("error", msg))


def warn(msg: str) -> None:
    issues.append(("warn", msg))


def read(rel: str) -> str:
    p = SKILL / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def all_docs() -> dict[str, str]:
    return {rel: read(rel) for rel in DOCS}


# ---------------------------------------------------------------- 1. 版本一致
def check_version(docs: dict[str, str]) -> None:
    skill = docs["SKILL.md"]
    m = re.search(r"^version:\s*([\d.]+)", skill, re.M)
    if not m:
        err("SKILL.md 缺 frontmatter version")
        return
    ver = m.group(1)
    log = docs["CHANGELOG.md"]
    top = re.search(r"^## v([\d.]+)", log, re.M)
    if not top:
        err("CHANGELOG.md 找不到 `## vX.Y.Z` 条目")
    elif top.group(1) != ver:
        err(f"版本不一致：SKILL.md={ver}，CHANGELOG 最新={top.group(1)}")

    sv = re.search(r'^schema_version:\s*"?(\d+)"?', skill, re.M)
    renderer = read("scripts/render_report.py")
    m2 = re.search(r'str\(sv\)\s*!=\s*"(\d+)"', renderer)
    if sv and m2 and sv.group(1) != m2.group(1):
        err(f"schema_version 不一致：SKILL={sv.group(1)}，渲染器认的是 {m2.group(1)}")


# ------------------------------------------------------- 2. 章节号 §N 是否存在
def check_section_refs(docs: dict[str, str]) -> None:
    zb = docs["references/指标体系.md"]
    defined = {int(x) for x in re.findall(r"^##\s*(\d+)\.", zb, re.M)}
    if not defined:
        err("指标体系.md 里没解析到 `## N.` 章节标题")
        return
    for name, text in docs.items():
        if name == "CHANGELOG.md":
            continue          # 变更记录是历史存档，会提到已删掉的章节，不参与对账
        for ref in sorted({int(x) for x in re.findall(r"§(\d+)", text)}):
            if ref not in defined:
                err(f"{name} 引用了 §{ref}，但指标体系里没有这一章")


# ---------------------------------------------------- 3. 文档里提到的文件都在
def check_paths(docs: dict[str, str]) -> None:
    pat = r"`((?:references|scripts|evals)/[A-Za-z0-9_./-]+\.(?:md|py|js|json|txt))`"
    seen = set()
    for name, text in docs.items():
        for rel in re.findall(pat, text):
            if rel in seen:
                continue
            seen.add(rel)
            if not (SKILL / rel).exists():
                err(f"{name} 引用了不存在的文件：{rel}")


# ------------------------------------------------------------ 4. 工具名核对
def check_tools(docs: dict[str, str], snap: dict) -> None:
    live = set(snap.get("tools") or [])
    if not live:
        warn("快照里没有工具清单，跳过工具名核对（跑 --refresh 重建）")
        return
    for name, text in docs.items():
        for tool in sorted(set(re.findall(r"\b((?:data|tool)_[a-z_]+)\b", text))):
            if tool in live or tool in NOT_A_TOOL:
                continue
            if re.fullmatch(r"(?:data|tool)_x+", tool):
                continue         # data_xxx 这种是文档里的占位符，不是真工具名
            # tool_ 前缀是排版工具（tool_ranking 等），以快照为准
            err(f"{name} 提到工具 `{tool}`，快照里没有——是不是记错了名字？")


# ------------------------------------------------------------ 5. 字段名核对
FIELD_ALLOW = {
    "WorkBuddy", "WeStock", "DeepSeek", "EastMoney", "Mcp", "Report",
    "OAuth", "Bearer", "SHA256", "AES", "GCM", "HKDF",
    "AttributeError", "TypeError", "KeyError", "JSONDecodeError",
    "Goodwill",  # 文档里专门用来提醒「不是这个拼写」的反例
}

# 这些字段确实可能不在接口里；只有在「不存在/不返回」语境里才放行。
ABSENT_OK = {"ShortTermLoan", "InventoryBreakdown", "Top5Customer"}


def check_fields(docs: dict[str, str], snap: dict) -> None:
    fields = set()
    for group in (snap.get("fields") or {}).values():
        fields |= set(group)
    if not fields:
        warn("快照里没有字段清单，跳过字段名核对（跑 --refresh 重建）")
        return
    # 只查反引号里的驼峰标识符：`InfoPublDate` 这种，避免把普通英文当字段
    NEG = r"(?:不存在|拿不到|没有|缺失|缺该|无此|取不到|不返回)"
    def said_absent(token: str, start: int, text: str) -> bool:
        """只在字段名附近的「字段 + 不存在」句式里判，不用 120 字宽窗误伤。"""
        seg = text[max(0, start - 40):start + len(token) + 40]
        pats = (
            rf"`{re.escape(token)}`\s*{NEG}",
            rf"{NEG}[^。；\n]{{0,20}}`{re.escape(token)}`",
        )
        return any(re.search(p, seg) for p in pats)

    for name, text in docs.items():
        for token in sorted(set(re.findall(r"`([A-Z][A-Za-z]{6,})`", text))):
            if token in FIELD_ALLOW or token.isupper():
                continue
            occ = [m.start() for m in re.finditer(re.escape(token), text)]
            neg = any(said_absent(token, pos, text) for pos in occ)
            if token in fields:
                # 字段存在，但文档若在同一句里说它「不存在/拿不到」，属于反向错误。
                if neg:
                    err(f"{name} 说 `{token}` 不存在/拿不到，但快照里明确有这个字段——"
                        f"字段存在性写反了")
                continue
            if token in ABSENT_OK and neg:
                continue
            err(f"{name} 里的 `{token}` 不在字段快照里，也没有明确说它「不存在」——"
                f"字段名可能拼错；若确属接口未返回，请改写成 `{token}` 不存在并加入 ABSENT_OK")


# ------------------------------------------------- 6. 文档里的数字 ↔ 代码常量
def _table_rows(seg: str, first_cell_int: bool = False) -> list[list[str]]:
    rows = []
    for line in seg.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(set(c) <= set(":- ") for c in cells):
            continue
        if first_cell_int and not re.fullmatch(r"\d{1,2}", cells[0]):
            continue
        rows.append(cells)
    return rows


def check_numbers(docs: dict[str, str]) -> None:
    zb = docs["references/指标体系.md"]
    val = read("scripts/validate.py")

    # (a) 排雷 25 条
    seg12 = zb.split("## 12.")[-1].split("## 13.")[0]
    ids = [r for r in _table_rows(seg12, first_cell_int=True)]
    ids = [r for r in ids if 1 <= int(r[0]) <= 25]
    if len(ids) != 25:
        err(f"指标体系 §12 排雷清单应为 25 条，实际解析到 {len(ids)} 条")
    if "1~25" not in val:
        warn("validate.py 里没找到 `1~25` 的排雷编号范围说明")

    # (b) 护城河五指标
    seg9 = zb.split("### 9.4")[-1].split("###")[0]
    rows9 = []
    started = False
    for line in seg9.splitlines():
        if line.strip().startswith("|"):
            started = True
            rows9.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif started:
            break          # 第一张表结束
    rows9 = [r for r in rows9 if len(r) >= 3]
    moat_metrics = {"自由现金流", "FCF / 营收", "净利率", "ROE", "ROA"}
    got = sum(1 for r in rows9 if any(k in r[0] for k in moat_metrics))
    if got != 5:
        err(f"指标体系 §9.4 应有 5 个护城河指标，实际 {got} 个")
    keys = set(re.findall(r'"(fcf|fcf_margin|net_margin|roe|roa)"', val))
    if len(keys) < 5:
        err(f"validate.py 里护城河 rows 的 key 只定义了 {len(keys)} 个（应 5 个）")

    # (c) 打分卡 16 项 / 权重和 33 / 满分 66
    seg13 = zb.split("## 13.")[-1]
    rows13 = [r for r in _table_rows(seg13) if len(r) >= 3 and "×" in r[-1]]
    total_w = sum(int(re.search(r"(\d+)", r[-1]).group(1)) for r in rows13)
    if len(rows13) != 16:
        err(f"指标体系 §13 打分卡应为 16 项，实际 {len(rows13)} 项")
    if total_w != 33:
        err(f"指标体系 §13 权重和应为 33，实际 {total_w}（满分 {total_w * 2}）")
    if "满分 66" not in docs["SKILL.md"]:
        err("SKILL 必须明确写「满分 66」；否则校验器无法与 16 项 × 2 对账")
    elif total_w * 2 != 66:
        err(f"SKILL 写「满分 66」，但文档权重算出来是 {total_w * 2}")
    if "16 项" not in docs["SKILL.md"]:
        err("SKILL 必须明确写「16 项」打分卡；否则 16 项结构无法对账")

    # (c2) 采样口径：SKILL 与接入文档必须一致
    skill_txt = docs["SKILL.md"]
    if "40~85" not in skill_txt:
        err("SKILL 应写「40~85 个采样点」")
    if "1.6" not in skill_txt:
        err("SKILL 应写采样间隔 ≥1.6 秒")
    acc_txt = docs["references/接入WeStock.md"]
    if "24~120" in acc_txt and "40~85" not in acc_txt:
        err("接入WeStock.md 仍写 24~120，与 SKILL 的 40~85 不一致")

    # (c2b) 限频三数：客户端默认间隔 ↔ 两份文档写的「80 次 / 60 秒 / 1.6 秒」
    client = read("scripts/westock_client.js")
    m_int = re.search(r"WESTOCK_INTERVAL\s*\|\|\s*(\d+)", client)
    if not m_int:
        err("westock_client.js 里找不到 `WESTOCK_INTERVAL || <默认值>`")
    elif int(m_int.group(1)) != 1600:
        err(f"westock_client.js 默认间隔 {m_int.group(1)}ms，但文档写的是 1.6 秒（1600ms）")
    for doc, label in ((docs["references/westock-接口.md"], "westock-接口.md"),
                       (acc_txt, "接入WeStock.md")):
        for phrase in ("80 次", "60 秒", "1.6"):
            if phrase not in doc:
                warn(f"{label} 没写限频口径「{phrase}」——这是实测数字，别在改采样策略时丢掉")

    # (c2c) 跨源补数：两个外补字段都要有可复制的 URL 模板
    api = docs["references/westock-接口.md"]
    for name, what in (("CONSTRUCT_LONG_ASSET", "资本支出（护城河 FCF）"),
                       ("RPT_F10_FN_MAINOP", "主营构成（分部表）")):
        if name not in api:
            err(f"westock-接口.md 缺跨源补数字段 {name}（{what}）")
    if "MAINOP_TYPE" not in api:
        err("westock-接口.md 写主营构成时必须说明 `MAINOP_TYPE` 的 1/2/3 含义")

    # (d) 取数清单：接口文档 §2 表格行数 ↔ SKILL 声称的次数
    seg2 = api.split("## 二、")[-1].split("## 三、")[0]
    rows_api = [r for r in _table_rows(seg2) if r and re.match(r"\d+", r[0])]
    if len(rows_api) != 16:
        err(f"接口文档 §2 必取数据表应为 16 行，实际 {len(rows_api)} 行")
    m = re.search(r"\*\*(\d+) 次接口调用", docs["SKILL.md"])
    if m and int(m.group(1)) != len(rows_api):
        err(f"SKILL 说「{m.group(1)} 次接口调用」，接口文档表是 {len(rows_api)} 行")
    # SKILL 取数代码块里的工具行数（去重采样行）
    block = docs["SKILL.md"].split("按 `references/westock-接口.md`")[-1]
    block = re.split(r"\*\*另有[一二三]个补充动作", block)[0]
    calls = [l for l in block.splitlines() if re.match(r"^\s*(data_|tool_)", l)]
    if calls and len(calls) - 1 != len(rows_api):
        err(f"SKILL 取数块有 {len(calls)} 行工具调用（含 1 行采样），"
            f"接口文档表是 {len(rows_api)} 行——两处应差 1")


# ---------------------------------------- 7. 文档承诺的 JSON 键，渲染器必须认
def check_json_keys(docs: dict[str, str]) -> None:
    renderer = read("scripts/render_report.py") + read("scripts/render_md.py")
    if not renderer:
        err("读不到渲染器源码")
        return
    keys = {
        "meta", "verdict", "price", "core_metrics", "core_summary", "business", "valuation",
        "financials", "data_gaps", "redflags", "redflags_checked", "redflags_note",
        "scorecard", "conclusion", "sources",
    }
    for k in sorted(keys):
        if f'"{k}"' not in renderer:
            err(f"文档承诺的 `{k}` 字段，渲染器里没有引用——写了也不会显示")
        elif f"`{k}`" not in docs["SKILL.md"]:
            err(f"渲染器读了 `{k}`，但 SKILL 的 JSON 字段表没登记——"
                f"写的人不知道该填，等于这个字段不存在")
    if '"moat"' not in renderer:
        err("文档承诺的 `business.moat`，渲染器里没有引用")


# ------------------------------------------- 8. 骨架节数 = 渲染器输出的节数
def check_skeleton(docs: dict[str, str]) -> None:
    skill = docs["SKILL.md"]
    seg = skill.split("## 报告骨架")[-1].split("\n---\n")[0] if "## 报告骨架" in skill else ""
    rows = [r for r in _table_rows(seg) if r and r[0] in "一二三四五六七八"]
    if len(rows) != 8:
        err(f"报告骨架应为 8 节，实际 {len(rows)} 节")
    # 每节声明的 JSON 键都要能被渲染器读到
    renderer = read("scripts/render_report.py")
    for r in rows:
        cell = r[-1]
        for k in re.findall(r"`([A-Za-z_.]+)`", cell):   # 大写也算：别名拼错也要抓
            root = k.split(".")[0]
            if f'"{root}"' not in renderer:
                err(f"骨架第 {r[0]} 节声明的 `{k}`，渲染器里读不到")
    # 节次编号必须连续
    nums = [r[0] for r in rows]
    if nums != list("一二三四五六七八"):
        err(f"骨架节次不连续：{nums}")


# --------------------------------- 9. 八节标题三方对账（骨架 / 范式 / 渲染器）
def check_section_titles(docs: dict[str, str]) -> None:
    """SKILL 骨架表、解读范式 §二 小节、渲染器 SECTION_TITLES，三处必须指同一节。"""
    skill = docs["SKILL.md"]
    seg = skill.split("## 报告骨架")[-1].split("\n---\n")[0]
    skel = {}
    for r in _table_rows(seg):
        if len(r) >= 2 and r[0] in "一二三四五六七八":
            skel[r[0]] = r[1].strip()

    fan = docs["references/解读范式.md"]
    seg2 = fan.split("\n## 二、")[1].split("\n## ")[0]
    fan_map = {}
    for m in re.finditer(r"^### ([一二三四五六七八])、(.+)$", seg2, re.M):
        fan_map[m.group(1)] = m.group(2).strip()

    # 骨架节次 → 渲染器 SECTION_TITLES 的 key；改标题必须三处同步。
    key_map = {
        "一": "price", "二": "core_metrics", "三": "business", "四": "financials",
        "五": "redflags", "六": "scorecard", "七": "valuation", "八": "conclusion",
    }

    def same(a: str, b: str) -> bool:
        return a == b or a.startswith(b) or b.startswith(a)

    for num, title in skel.items():
        key = key_map.get(num)
        expected = SECTION_TITLES.get(key or "")
        if not expected:
            err(f"第{num}节在渲染器 SECTION_TITLES 里没有对应 key（{key!r}）")
            continue
        if not same(title, expected):
            err(f"第{num}节标题不一致：骨架写「{num}、{title}」，渲染器写「{expected}」")
        if num in fan_map and not same(title, fan_map[num]):
            err(f"第{num}节标题不一致：骨架写「{num}、{title}」，解读范式写「{num}、{fan_map[num]}」")
    if set(skel) - set(fan_map):
        warn(f"解读范式 §二 缺这些节的小节标题：{sorted(set(skel) - set(fan_map))}")


# ---------------------------------------------------------------- 快照处理
def load_snapshot() -> dict:
    if SNAP.exists():
        return json.loads(SNAP.read_text(encoding="utf-8"))
    return {}


def refresh_snapshot() -> dict:
    """连 WeStock 重建工具/字段快照（需要 node + 已授权）。

    字段快照是「三只股票并集」，不是单只股票：某字段只在 600315 出现，
    单抓 600519 会把它误删。只有全部抓取成功后才原子替换旧快照。
    """
    client = SKILL / "scripts" / "westock_client.js"
    codes = ("sh600519", "sz301101", "sh600315")
    snap: dict = {"generated": "", "tools": [], "fields": {}}
    try:
        out = subprocess.run(["node", str(client), "tools"], capture_output=True,
                             text=True, timeout=120).stdout
        snap["tools"] = sorted(l.split("\t")[0].strip() for l in out.splitlines() if l.strip())
        for kind in ("balance", "income", "cashflow"):
            union: set[str] = set()
            for code in codes:
                p = subprocess.run(
                    ["node", str(client), "call", "data_finance",
                     json.dumps({"code": code, "type": kind, "fields": "all", "num": 4})],
                    capture_output=True, text=True, timeout=120)
                data = json.loads(p.stdout)["data"]["data"]
                first = next(iter(data.values()))[0]
                union |= set(first)
            snap["fields"][kind] = sorted(union)
        snap["generated"] = (
            f"{__import__('datetime').date.today().isoformat()} · "
            f"三只股票并集（600519/301101/600315）"
        )
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        tmp = SNAP.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(SNAP)
        print(f"快照已更新：{len(snap['tools'])} 个工具，"
              f"{sum(len(v) for v in snap['fields'].values())} 个字段 → {SNAP.relative_to(SKILL)}")
    except Exception as e:  # noqa: BLE001
        warn(f"重建快照失败（{e}），沿用旧快照")
    return snap


MUTATIONS = [
    ("SKILL.md", "@VER@", "version: 9.9.9", "版本号不一致"),
    ("SKILL.md", "§13 打分卡", "§14 打分卡", "引用不存在的章节"),
    ("SKILL.md", "data_score", "data_scorez", "工具名写错"),
    ("SKILL.md", "`NotAccountsPayable`", "`NotAccountPayableZ`", "字段名拼错"),
    ("SKILL.md", "| `valuation` |", "| `valuationZ` |", "骨架声明的键渲染器不认"),
    ("references/指标体系.md", "| 安全 | 商誉/净资产（反向） | ×2 |",
     "| 安全 | 商誉/净资产（反向） | ×4 |", "打分卡权重被改"),
    ("references/指标体系.md", "| 25 | 收入↓", "| 26 | 收入↓", "排雷条数不对"),
    ("SKILL.md", "@SEC2@", "| 二 | 核心指标估值 |", "节标题与范式/渲染器不一致"),
]


def selftest() -> int:
    """在临时副本里注入已知错误，确认每一种都被抓到。"""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "skill"
        # 注意：skill 目录本身是软链接，cp -r 会复制链接；必须解引用
        shutil.copytree(SKILL, dst, symlinks=False,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        # 占位符换成当前真值，版本号/标题以后改了自测也不会失效
        ver = re.search(r"^version:\s*([\d.]+)", (dst / "SKILL.md").read_text(encoding="utf-8"), re.M)
        sec2 = re.search(r"\| 二 \| ([^|]+?) \|",
                         (dst / "SKILL.md").read_text(encoding="utf-8"))
        subst = {"@VER@": f"version: {ver.group(1) if ver else '0.0.0'}",
                 "@SEC2@": f"| 二 | {sec2.group(1).strip() if sec2 else '?'} |"}

        for rel, old, new, desc in MUTATIONS:
            f = dst / rel
            text = f.read_text(encoding="utf-8")
            for k, v in subst.items():
                old = old.replace(k, v)
            if old not in text:
                print(f"[自测失败] 找不到注入点：{desc}（`{old}`）")
                return 1
            f.write_text(text.replace(old, new, 1), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(dst / "scripts" / "check_docs.py")],
                              capture_output=True, text=True)
        out = proc.stdout
        print(out.strip().splitlines()[-1] if out.strip() else "(无输出)")
        for line in out.splitlines():
            if line.startswith("[错误]"):
                print(f"  ✓ 抓到：{line[5:]}")
        caught = out.count("[错误]")
        print(f"\n注入 {len(MUTATIONS)} 处，抓到 {caught} 处")
        return 0 if caught >= len(MUTATIONS) and proc.returncode != 0 else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    verbose = "-v" in sys.argv
    snap = refresh_snapshot() if "--refresh" in sys.argv else load_snapshot()
    docs = all_docs()
    checks = [
        ("版本一致", lambda: check_version(docs)),
        ("章节引用", lambda: check_section_refs(docs)),
        ("文件路径", lambda: check_paths(docs)),
        ("工具名", lambda: check_tools(docs, snap)),
        ("字段名", lambda: check_fields(docs, snap)),
        ("数量常量", lambda: check_numbers(docs)),
        ("JSON 键可达", lambda: check_json_keys(docs)),
        ("报告骨架", lambda: check_skeleton(docs)),
        ("节标题对账", lambda: check_section_titles(docs)),
    ]
    for name, fn in checks:
        before = len(issues)
        fn()
        added = len(issues) - before
        if verbose:
            print(f"  · {name}: {added} 个问题")

    errs = [m for lv, m in issues if lv == "error"]
    warns = [m for lv, m in issues if lv == "warn"]
    for m in errs:
        print(f"[错误] {m}")
    for m in warns:
        print(f"[提醒] {m}")
    print(f"\n{len(errs)} 个错误，{len(warns)} 个提醒"
          f"（{len(docs)} 份文档 + {len(snap.get('tools') or [])} 个工具快照）")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
