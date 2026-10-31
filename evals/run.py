#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：对 evals/cases/ 下每个样例跑 validate + 两个渲染器，按 cases.json 断言；
最后再跑一遍 scripts/check_docs.py（文档里的数字/工具名/字段名/章节号与代码对账）。

用法:
    python3 evals/run.py            # 全跑
    python3 evals/run.py -v         # 打印每个用例的渲染耗时与告警

改完脚本先跑这个，全绿再提交——它覆盖的正是「静默降级」那类不报错但产出错的毛病。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent
SCRIPTS = SKILL / "scripts"


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_output_pipeline(verbose: bool = False) -> int:
    """v2.8.0 输出契约：env 中文路径 + raw_data 合并 + 三件套同名。"""
    case = ROOT / "cases" / "mingyue-v2.json"
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out_dir = root / "中文 目录" / "股票报告"
        env_file = root / "env"
        env_file.write_text(f"REPORT_OUTPUT_DIR={out_dir}\n", encoding="utf-8")
        raw_file = root / "raw.json"
        raw_file.write_text(json.dumps({
            "schema": "raw-v1",
            "code": "sz301101",
            "calls": [{
                "source": "westock",
                "tool": "data_search",
                "params": {"query": "明月镜片"},
                "at": "2026-10-31 14:00:00",
                "ok": True,
                "response": {"ok": True, "data": [{"code": "sz301101", "name": "明月镜片"}]},
            }],
        }, ensure_ascii=False), encoding="utf-8")

        rc, out, err = run([sys.executable, str(SCRIPTS / "save_report.py"),
                            str(case), "--raw", str(raw_file), "--env-file", str(env_file)])
        if rc != 0:
            problems.append(f"save_report 失败 rc={rc} {(err or out)[:300]}")
        else:
            jsons = list(out_dir.glob("*.json"))
            htmls = list(out_dir.glob("*.html"))
            mds = list(out_dir.glob("*.md"))
            if not (len(jsons) == len(htmls) == len(mds) == 1):
                problems.append(f"三件套数量不对：json={len(jsons)} html={len(htmls)} md={len(mds)}")
            else:
                stems = {jsons[0].stem, htmls[0].stem, mds[0].stem}
                if len(stems) != 1:
                    problems.append(f"三件套主文件名不一致：{sorted(stems)}")
                if "中文 目录" not in str(jsons[0]):
                    problems.append("中文/空格输出目录没有生效")
                data = json.loads(jsons[0].read_text(encoding="utf-8"))
                raw = data.get("raw_data") or {}
                if raw.get("call_count") != 1 or not raw.get("calls"):
                    problems.append("交付 JSON 没有正确并入 raw_data")
                if "_data_package" not in data:
                    problems.append("交付 JSON 缺 _data_package 说明")
                # 已研究过：能按 6 位代码查到缓存；--reuse 只更新三件套
                rc3, o3, e3 = run([sys.executable, str(SCRIPTS / "report_cache.py"),
                                   "lookup", "--code", "301101",
                                   "--env-file", str(env_file), "--json"])
                try:
                    cache = json.loads(o3)
                except json.JSONDecodeError:
                    cache = {}
                    problems.append(f"report_cache 输出不是 JSON：{(o3 or e3)[:200]}")
                if rc3 != 0 or not cache.get("cached"):
                    problems.append(f"已保存的报告没有被识别为缓存 rc={rc3}")
                rc4, o4, e4 = run([sys.executable, str(SCRIPTS / "save_report.py"),
                                   "--reuse", "--code", "sz301101",
                                   "--env-file", str(env_file)])
                if rc4 != 0:
                    problems.append(f"save_report --reuse 失败 rc={rc4} {(e4 or o4)[:200]}")
                if len(list(out_dir.glob("*.json"))) != 1:
                    problems.append("--reuse 不应为同一公司新增第二份 JSON")
                rc5, o5, e5 = run([sys.executable, str(SCRIPTS / "report_cache.py"),
                                   "lookup", "--code", "600519",
                                   "--env-file", str(env_file), "--json"])
                try:
                    missing = json.loads(o5)
                except json.JSONDecodeError:
                    missing = {}
                if missing.get("cached"):
                    problems.append("未研究过的公司被误判为已有缓存")
                # 旧产物只有 HTML/MD：应识别成 legacy_only，不能冒充可复用数据
                legacy_dir = root / "旧 报告"
                legacy_dir.mkdir(parents=True, exist_ok=True)
                (legacy_dir / "测试公司-企业信息解读-20261030.md").write_text(
                    "# 测试公司（sz300999）企业信息解读\n\n旧版报告，没有 JSON。\n",
                    encoding="utf-8")
                legacy_env = root / "env-legacy"
                legacy_env.write_text(f"REPORT_OUTPUT_DIR={legacy_dir}\n", encoding="utf-8")
                rc6, o6, e6 = run([sys.executable, str(SCRIPTS / "report_cache.py"),
                                   "lookup", "--code", "sz300999",
                                   "--env-file", str(legacy_env), "--json"])
                try:
                    legacy = json.loads(o6)
                except json.JSONDecodeError:
                    legacy = {}
                    problems.append(f"legacy 查询输出不是 JSON：{(o6 or e6)[:200]}")
                if not legacy.get("cached") or not legacy.get("legacy_only"):
                    problems.append("只有旧 HTML/MD 的公司没有被识别为 legacy_only")
                if legacy.get("has_data"):
                    problems.append("没有 JSON 的旧报告被误判为 has_data")
                if verbose:
                    print(f"  · 输出契约实测：{jsons[0].name} / "
                          f"{htmls[0].name} / {mds[0].name}")
    status = "PASS" if not problems else "FAIL"
    print(f"[{status}] 输出契约 — env 中文路径 + raw_data + 三件套同名")
    for p in problems:
        print(f"        ! {p}")
    return 1 if problems else 0


def test_silent_guards(verbose: bool = False) -> int:
    """v2.10 静默降级防护：judge 字符串、表头错列、price.records、排雷补充说明。"""
    case = ROOT / "cases" / "mingyue-v2.json"
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data = json.loads(case.read_text(encoding="utf-8"))
        data["business"]["moat"]["metrics"]["judge"] = "五年里 ROE 有 3 年低于 15%，护城河偏窄"
        data["financials"]["yoy"]["headers"].append("测试多一列")
        data["price"]["records"] = [{"label": "2021 年", "value": "1.88 ~ 5.12 元"}]
        data["redflags"] = [{"id": 9, "level": "关注", "text": "低 PB 里三成是现金",
                             "evidence": "测试依据", "hit": True}]
        data["redflags_note"] = "这是命中项之后的补充说明，不能丢。"
        bad = root / "bad.json"
        bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        rc, out, err = run([sys.executable, str(SCRIPTS / "validate.py"), str(bad)])
        joined = out + err
        if rc == 0:
            problems.append("judge 字符串 / headers 错列 / price.records 错键，validate 应失败")
        for needle in ("judge 必须是对象", "financials.yoy", "price.records"):
            if needle not in joined:
                problems.append(f"validate 没报出 {needle!r}")
        md = root / "bad.md"
        html = root / "bad.html"
        rc1, o1, e1 = run([sys.executable, str(SCRIPTS / "render_md.py"), str(bad), "-o", str(md)])
        rc2, o2, e2 = run([sys.executable, str(SCRIPTS / "render_report.py"), str(bad), "-o", str(html)])
        if rc1 != 0 or not md.exists():
            problems.append(f"MD 渲染失败 rc={rc1} {(e1 or o1)[:200]}")
        if rc2 != 0 or not html.exists():
            problems.append(f"HTML 渲染失败 rc={rc2} {(e2 or o2)[:200]}")
        md_text = md.read_text(encoding="utf-8") if md.exists() else ""
        html_text = html.read_text(encoding="utf-8") if html.exists() else ""
        if "这是命中项之后的补充说明，不能丢。" not in md_text:
            problems.append("MD 命中项之后的 redflags_note 丢了")
        if "这是命中项之后的补充说明，不能丢。" not in html_text:
            problems.append("HTML 命中项之后的 redflags_note 丢了")
        if "五年里 ROE 有 3 年低于 15%，护城河偏窄" not in md_text:
            problems.append("judge 字符串没有按一整条渲染")
        if "\n- 五\n" in md_text or "\n- 年\n" in md_text:
            problems.append("judge 字符串仍被逐字拆成多条")

        # 合法样例不应再出现「labels 7 ≠ periods 17」这种跨图误报
        rc3, o3, e3 = run([sys.executable, str(SCRIPTS / "validate.py"), str(case)])
        if "≠ periods" in (o3 + e3):
            problems.append("合法年度子集 labels 仍被拿 periods 长度误报")

        # 采集包不存在：默认拒绝，不能静默 new_bundle
        missing = root / "不存在" / "raw.json"
        rc4, o4, e4 = run([sys.executable, str(SCRIPTS / "collect_raw.py"), "run",
                           str(missing), "--tool", "data_quote", "--params", "{}"])
        if rc4 != 2 or missing.exists():
            problems.append(f"collect_raw run 对缺失包应 rc=2 且不建文件，实际 rc={rc4}")
        if "请先 init" not in (o4 + e4):
            problems.append("collect_raw run 缺失包时没有提示 init")
        rc5, o5, e5 = run([sys.executable, str(SCRIPTS / "collect_raw.py"), "status", str(missing)])
        if rc5 != 1 or "请先 init" not in (o5 + e5):
            problems.append("collect_raw status 对缺失包没有友好报错")

        # 月末采样：只补缺失月份，dry-run 不联网
        raw = root / "raw.json"
        raw.write_text(json.dumps({
            "schema": "raw-v1", "code": "sz000629", "created_at": "x", "updated_at": "x",
            "calls": [{"source": "westock", "tool": "data_quote",
                       "params": {"code": "sz000629", "date": "2026-06-30"},
                       "at": "x", "ok": True,
                       "response": {"ok": True, "data": {"sz000629": {"close": 1.0}}}}],
        }, ensure_ascii=False), encoding="utf-8")
        rc6, o6, e6 = run([sys.executable, str(SCRIPTS / "sample_valuation.py"),
                           "--code", "sz000629", "--raw", str(raw),
                           "--start", "2026-06-01", "--end", "2026-09-30", "--dry-run"])
        if rc6 != 0 or "待补 3" not in (o6 + e6):
            problems.append(f"sample_valuation dry-run 应识别已有 1 个月、待补 3 个，实际 rc={rc6} {(o6 + e6)[:200]}")
        rc7, o7, e7 = run([sys.executable, str(SCRIPTS / "sample_valuation.py"),
                           "--code", "sz000629", "--raw", str(root / "nope.json"), "--dry-run"])
        if rc7 != 2 or "请先" not in (o7 + e7):
            problems.append("sample_valuation 对缺失采集包没有拒绝")
        if verbose:
            print("  · 静默防护实测：judge/错列/price.records/redflags_note/采样 dry-run")
    status = "PASS" if not problems else "FAIL"
    print(f"[{status}] 静默降级防护 — judge/错列/records/补充说明/采集包守卫/采样 dry-run")
    for p in problems:
        print(f"        ! {p}")
    return 1 if problems else 0


def test_concurrency(verbose: bool = False) -> int:
    """并发写采集包：锁内「重读→追加→写回」之后，一条都不能丢、seq 不能重号。

    2026-10-31 的 P0：采样脚本拿着启动时的旧副本整包写回，把同时 add 的 F10 覆盖掉，
    终端却已打印「已记录」。这里用两个子进程同时 update 来复现那个场景。
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "并发.json"
        rc, o, e = run([sys.executable, str(SCRIPTS / "collect_raw.py"),
                        "init", str(raw), "--code", "sz300224"])
        if rc != 0:
            problems.append(f"init 失败 rc={rc} {(o + e)[:200]}")
        worker = Path(td) / "worker.py"
        worker.write_text(
            "import sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import raw_bundle\n"
            "p, tag, n = sys.argv[2], sys.argv[3], int(sys.argv[4])\n"
            "for i in range(n):\n"
            "    raw_bundle.update(p, source='westock', tool='data_quote',\n"
            "                      params={'code': 'sz300224', 'date': f'2026-01-{i%28+1:02d}'},\n"
            "                      response={'ok': True, 'data': {'sz300224': {'pe_ratio': i}}},\n"
            "                      note=tag)\n"
            "    time.sleep(0.002)\n",
            encoding="utf-8")
        procs = [
            subprocess.Popen([sys.executable, str(worker), str(SCRIPTS),
                              str(raw), tag, "40"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for tag in ("A", "B")
        ]
        for proc in procs:
            proc.communicate()
        import json as _json
        got = _json.loads(raw.read_text(encoding="utf-8"))
        calls = got.get("calls") or []
        seqs = [c.get("seq") for c in calls]
        if len(calls) != 80:
            problems.append(f"并发写丢了条目：应 80 条，实际 {len(calls)}（锁没生效）")
        if len(seqs) != len(set(seqs)):
            problems.append(f"并发写出现重号 seq：{sorted(seqs)[:10]}…")
        if seqs != list(range(1, len(seqs) + 1)):
            problems.append("seq 不是从 1 连续编号")

        # 「已记录」必须回读真实条数：连加两条后打印「共 2 条」
        rc1, o1, _ = run([sys.executable, str(SCRIPTS / "collect_raw.py"), "add", str(raw),
                          "--tool", "data_kline", "--params", "{}",
                          "--response", '{"ok": true, "data": []}'])
        if "包内共 81 条" not in o1:
            problems.append(f"collect_raw add 没打印回读后的总条数：{o1.strip()[:120]}")
        if verbose:
            print(f"  · 并发实测：{len(calls)} 条 / 唯一 seq {len(set(seqs))} / 回读打印正常")
    status = "PASS" if not problems else "FAIL"
    print(f"[{status}] 采集包并发防护 — 两进程同时写 80 条，零丢失、seq 连续")
    for p in problems:
        print(f"        ! {p}")
    return 1 if problems else 0


def test_api_semantics(verbose: bool = False) -> int:
    """接口口径的实测回归：总市值单位、MAINOP_TYPE 枚举。

    2026-10-31 这两处文档与接口不符，各造成过一次静默算错。结构校验抓不到，
    所以这里拿「真实采集包保存下来的基准」（evals/fixtures/api-semantics.json）
    反推口径，再要求 SKILL 与接口文档写的是同一个结论——**文档不是基准，返回才是**。
    """
    problems: list[str] = []
    fx = json.loads((ROOT / "fixtures" / "api-semantics.json").read_text(encoding="utf-8"))

    # ① total_market_cap：cap ≈ price × shares ⇒ 单位「元」（当前与历史一致）
    for s in fx["data_quote"]["samples"]:
        price, shares, cap = s.get("price"), s.get("shares"), s.get("cap")
        if not (price and shares and cap):
            problems.append(f"基准样本缺字段：{s}")
            continue
        ratio = cap / (price * shares)
        if not 0.99 <= ratio <= 1.01:
            problems.append(
                f"{s['code']} {s['date']} 的 cap/(price×shares) = {ratio:.4g}，"
                f"不是 1.0——有人按「亿元」解释当前值了？")
        if verbose:
            print(f"  · {s['code']} {s['date']}: cap/(price×shares) = {ratio:.4f}")

    # ② MAINOP_TYPE：按 ITEM_NAME 反推语义，再和文档对照
    GEO = {"国内", "国外", "境内", "境外"}
    groups = fx["mainop"]["groups"]

    def classify(items):
        names = [i["name"] for i in items if "其他" not in i["name"]]
        if names and all(n in GEO for n in names):
            return "地区"
        if len(names) == 1 and items[0]["ratio"] >= 0.95:
            return "行业"
        if len(names) >= 3:
            return "产品"
        return None

    derived = {t: classify(items) for t, items in groups.items()}
    expect = {"1": "行业", "2": "产品", "3": "地区"}
    if derived != expect:
        problems.append(f"MAINOP_TYPE 语义与基准不符：反推 {derived}，预期 {expect}"
                        f"（基准来自 {fx['mainop']['code']} {fx['mainop']['report']}）")

    # ③ 文档必须和基准同口径
    texts = {
        "SKILL.md": (SKILL / "SKILL.md").read_text(encoding="utf-8"),
        "references/westock-接口.md": (SKILL / "references" / "westock-接口.md").read_text(encoding="utf-8"),
    }
    def norm(t: str) -> str:
        return re.sub(r"[\s`*_]+", "", t)

    for rel, text in texts.items():
        flat = norm(text)
        for digit, kind in (("1", "行业"), ("2", "产品"), ("3", "地区")):
            if not re.search(rf"{digit}(?:是按|是|按|=)?{kind}", flat):
                problems.append(f"{rel} 没有写「{digit} = {kind}」（与基准反推的枚举不一致）")
        for digit, kind in (("1", "产品"), ("2", "行业")):
            if re.search(rf"{digit}(?:是按|是|按|=)?{kind}", flat):
                problems.append(f"{rel} 仍写着旧口径「{digit} = {kind}」")
        if "当前值是「亿元」" in text:
            problems.append(f"{rel} 仍写着旧口径「当前值是「亿元」」")
        if "/1e8" not in text:
            problems.append(f"{rel} 没有写「/1e8」的市值换算规则")

    status = "PASS" if not problems else "FAIL"
    print(f"[{status}] 接口口径基准 — 市值单位（元）+ MAINOP_TYPE（1 行业 / 2 产品 / 3 地区）")
    for p in problems:
        print(f"        ! {p}")
    return 1 if problems else 0


def main() -> int:
    verbose = "-v" in sys.argv
    man = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    failed = 0
    for case in man["cases"]:
        path = ROOT / case["file"]
        name = path.name
        problems: list[str] = []

        rc, out, err = run([sys.executable, str(SCRIPTS / "validate.py"), str(path)])
        if case.get("expect_valid"):
            if rc != 0:
                problems.append(f"validate 应通过，实际退出码 {rc}")
        else:
            if rc == 0:
                problems.append("validate 应失败，实际通过")
        for needle in case.get("expect_error_contains") or []:
            if needle not in out:
                problems.append(f"校验输出缺少关键信息：{needle!r}")
        for needle in case.get("expect_warn_contains") or []:
            if needle not in out:
                problems.append(f"校验输出缺少关键提醒：{needle!r}")
        if case.get("allow_only_warns") and "[错误]" in out:
            problems.append("v1 用例只应产生警告，不应有错误")

        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "r.html"
            md = Path(td) / "r.md"
            rc1, o1, e1 = run([sys.executable, str(SCRIPTS / "render_report.py"), str(path), "-o", str(html)])
            rc2, o2, e2 = run([sys.executable, str(SCRIPTS / "render_md.py"), str(path), "-o", str(md)])
            if rc1 != 0 or not html.exists():
                problems.append(f"HTML 渲染失败 rc={rc1} {e1[:200]}")
            if rc2 != 0 or not md.exists():
                problems.append(f"MD 渲染失败 rc={rc2} {e2[:200]}")
            body_md = md.read_text(encoding="utf-8") if md.exists() else ""
            body_html = html.read_text(encoding="utf-8") if html.exists() else ""
            for needle in case.get("html_contains") or []:
                if needle not in body_html:
                    problems.append(f"HTML 缺少关键串 {needle!r}")
            for needle in case.get("html_not_contains") or []:
                if needle in body_html:
                    problems.append(f"HTML 不该出现 {needle!r}（渲染器没处理这种输入）")
            for needle in case.get("md_not_contains") or []:
                if needle in body_md:
                    problems.append(f"MD 不该出现 {needle!r}")
            for needle in case.get("must_contain") or []:
                if needle not in body_md or needle not in body_html:
                    where = []
                    if needle not in body_md:
                        where.append("md")
                    if needle not in body_html:
                        where.append("html")
                    problems.append(f"产物缺少关键串 {needle!r}（{'+'.join(where)}）")
            if case.get("expect_stance"):
                if case["expect_stance"] not in body_html:
                    problems.append(f"HTML 未渲染出 stance {case['expect_stance']!r}")
            # 节编号必须从「一」开始连续，不能跳号/重号
            seq = re.findall(r"<h2>([一二三四五六七八九十])、", body_html)
            expected = list("一二三四五六七八九十")[:len(seq)]
            if seq != expected:
                problems.append(f"HTML 节编号不连续：{''.join(seq)}（应为 {''.join(expected)}）")
            # 编码/乱码检查也要进 CI；golden sample 不能自己过不了 lint
            if html.exists() and md.exists():
                rcl, ol, el = run([sys.executable, str(SCRIPTS / "lint_encoding.py"),
                                   str(html), str(md)])
                if rcl != 0:
                    problems.append(f"lint_encoding 未通过：{(ol + el).strip()[-300:]}")
            if verbose:
                if e1.strip() or e2.strip():
                    print(f"  · {name} 渲染告警：{(e1 + e2).strip()[:300]}")

        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {name} — {case['desc']}")
        for p in problems:
            print(f"        ! {p}")
        failed += bool(problems)

    print(f"\n{len(man['cases']) - failed}/{len(man['cases'])} 个用例通过")

    # ---- 输出契约：env 中文路径、raw_data 合并、三件套同名 ----
    failed += test_output_pipeline(verbose)

    # ---- 静默降级防护：judge / 表头错列 / records / 补充说明 / 采集包守卫 ----
    failed += test_silent_guards(verbose)

    # ---- 采集包并发：锁内读-改-写，两进程同时写不能丢条目 ----
    failed += test_concurrency(verbose)

    # ---- 接口口径基准：市值单位 / MAINOP_TYPE，文档必须与真实返回一致 ----
    failed += test_api_semantics(verbose)

    # ---- 文档交叉引用检查（改文档忘了改代码，是这类 skill 最常见的错） ----
    rc, out, err = run([sys.executable, str(SCRIPTS / "check_docs.py")])
    tail = [l for l in (out or "").splitlines() if l.strip()][-1:] or [err[:200]]
    print(f"[{'PASS' if rc == 0 else 'FAIL'}] 文档交叉引用 — {tail[0]}")
    if rc != 0:
        for line in out.splitlines():
            if line.startswith("[错误]"):
                print(f"        ! {line[len('[错误] '):]}")
        failed += 1

    # ---- 编码自检：skill 自己的文档也要过（以前只扫产物，CHANGELOG 的 undici 一直漏着） ----
    rc, out, err = run([sys.executable, str(SCRIPTS / "lint_encoding.py"), str(SKILL)])
    tail = [l for l in (out or "").splitlines() if l.strip()][-1:] or [err[:200]]
    print(f"[{'PASS' if rc == 0 else 'FAIL'}] 文档编码自检 — {tail[0]}")
    if rc != 0:
        for line in out.splitlines():
            if "[error]" in line:
                print(f"        ! {line.strip()}")
        failed += 1

    # ---- 取数层回归：纯文本返回必须被判非 JSON（离线，不需要凭据/网络） ----
    node = shutil.which("node")
    if node:
        rc, out, err = run([node, str(SCRIPTS / "westock_client.js"), "selftest"])
        last = ((out or err).strip().splitlines() or [""])[-1]
        print(f"[{'PASS' if rc == 0 else 'FAIL'}] 客户端 selftest — {last}")
        if rc != 0:
            failed += 1
    else:
        print("[SKIP] 客户端 selftest — 没有 node，跳过（不判失败）")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
