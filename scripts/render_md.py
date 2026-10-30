#!/usr/bin/env python3
"""把个股分析数据 JSON 渲染成纯文本 Markdown 报告（不插图，趋势图用文字描述）。

用法:
    python3 render_md.py data.json -o 报告.md
    python3 render_md.py data.json            # 默认输出到同目录 report.md

与 render_report.py 共用同一份 JSON，保证两种格式内容一致。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_report import get, redflag_head  # noqa: E402

STATE_TXT = {"pass": "通过", "fail": "否决", "warn": "存疑", "na": "无数据"}


# ---------------------------------------------------------------- 工具


def t(v: Any) -> str:
    """纯文本取值，空值统一占位符。"""
    if v is None or v == "":
        return "—"
    return str(v).replace("|", "\\|").strip()


def md_table(headers: list, rows: list[list[str]], aligns: str | None = None) -> str:
    """生成标准 Markdown 表格。"""
    if not headers:
        return ""
    n = len(headers)
    if aligns is None:
        aligns = "l" + "c" * (n - 1)
    sep = " | ".join(
        {"l": "---", "c": ":---:", "r": "---:"}.get(a, "---") for a in aligns[:n]
    )
    out = ["| " + " | ".join(t(h) for h in headers) + " |", "| " + sep + " |"]
    for r in rows:
        cells = [t(c) for c in r] + ["—"] * (n - len(r))
        out.append("| " + " | ".join(cells[:n]) + " |")
    return "\n".join(out)


def matrix_md(headers: list, series: list[dict], first_col: str = "指标") -> str:
    """「首列 + 若干期」矩阵。"""
    if not headers or not series:
        return ""
    rows = [[t(s.get("name")), *[t(v) for v in (s.get("values") or [])]] for s in series]
    return md_table([first_col, *[t(h) for h in headers]], rows)


def bullets(items: list, marker: str = "-", indent: str = "") -> str:
    return "\n".join(f"{indent}{marker} {t(i)}" for i in items) if items else ""


# ---------------------------------------------------------------- 各区块


def b_title(m: dict) -> str:
    name, code = t(m.get("name")), t(m.get("code"))
    return f"# {name}（{code}）企业信息解读\n"


def b_head(m: dict) -> str:
    rows = [
        ["最新价", f"{t(m.get('price'))} {t(m.get('unit', '元'))}"],
        ["涨跌幅", f"{t(m.get('change_pct'))}　{t(m.get('chg_note'))}"],
        ["总市值", f"{t(m.get('market_cap'))}　{t(m.get('cap_note'))}"],
        ["所属行业", f"{t(m.get('industry'))}　{t(m.get('industry_note'))}"],
    ]
    out = [md_table(["项目", "内容"], rows, "lc"), ""]
    if m.get("tagline"):
        out.append(f"> {t(m.get('tagline'))}\n")
    return "\n".join(out)


def b_verdict(v: dict) -> str:
    if not v:
        return ""
    out = ["## 核心结论\n", f"**评级：{t(v.get('stance'))}**　{t(v.get('headline'))}\n",
           t(v.get("summary")), ""]
    tags = v.get("tags") or []
    if tags:
        out.append("关键标签：" + "、".join(
            t(tg if isinstance(tg, str) else tg.get("text")) for tg in tags) + "\n")
    return "\n".join(out)


def b_metrics(items: list[dict], title: str = "核心指标") -> str:
    if not items:
        return ""
    rows = [[t(i.get("label")), t(i.get("value")), t(i.get("note"))] for i in items]
    return f"## {t(title)}\n\n" + md_table(["指标", "数值", "说明"], rows, "lcl") + "\n"


def b_price(p: dict) -> str:
    if not p:
        return ""
    out = ["## 一、股价位置\n"]
    recs = p.get("records") or []
    if recs:
        rows = [[t(r.get("name")), t(r.get("range")), t(r.get("note"))] for r in recs]
        out += [md_table(["周期", "最高 / 最低", "说明"], rows, "lcl"), ""]
    cd = p.get("chart_data") or []
    if cd:
        vals = [float(c["value"]) for c in cd if c.get("value") is not None]
        lbs = [t(c.get("label")) for c in cd if c.get("value") is not None]
        if len(vals) >= 2:
            seq = " → ".join(f"{l} {v:.2f}" for l, v in zip(lbs, vals))
            lo_i, hi_i = vals.index(min(vals)), vals.index(max(vals))
            # 区间位置（0=最低，1=最高）与形态，按数据算，不写死
            span = max(vals) - min(vals)
            pos = (vals[-1] - min(vals)) / span if span else 0.5
            where = "上沿" if pos >= 0.66 else ("下沿" if pos <= 0.33 else "中部")
            chg_first = vals[-1] / vals[0] - 1 if vals[0] else 0
            slope = "自起点震荡上行" if chg_first > 0.05 else ("自起点震荡下行" if chg_first < -0.05 else "在区间内横盘震荡")
            desc = (
                f"**趋势图（折线面积图，季度收盘价，{t(p.get('unit','元'))}）**："
                f"共 {len(vals)} 个季度，序列为 {seq}。"
                f"区间低点出现在 {lbs[lo_i]}（{min(vals):.2f}），"
                f"高点出现在 {lbs[hi_i]}（{max(vals):.2f}），"
                f"最新一期 {lbs[-1]} 为 {vals[-1]:.2f}，"
                f"较区间高点回撤 {(vals[-1] / max(vals) - 1) * 100:.1f}%，"
                f"较区间低点高出 {(vals[-1] / min(vals) - 1) * 100:.1f}%，"
                f"位于区间 {pos * 100:.0f}% 分位（{where}）。"
                f"折线{slope}，区间内幅度 {(chg_first) * 100:+.1f}%。"
            )
            out.append(f"*{t(p.get('chart_title') or '季度收盘走势')}*\n")
            out.append(desc + "\n")
    if p.get("comment"):
        out.append(t(p["comment"]) + "\n")
    return "\n".join(out)


MOAT_STRENGTH_MD = {"wide": "宽", "narrow": "窄", "none": "无"}
MOAT_SRC_MD = {"strong": "强", "mid": "中", "weak": "弱", "none": "无"}


def b_moat(m) -> str:
    """三、生意本身 · 护城河（与 HTML 版同构，向后兼容纯字符串）。"""
    if not isinstance(m, dict):
        return "\n".join([f"### 护城河\n", t(m), ""])

    out = ["### 护城河\n"]
    label = MOAT_STRENGTH_MD.get(str(m.get("strength", "")))
    if label:
        note = t(m.get("strength_note", ""))
        out += [f"**护城河 {t(m.get('strength_text') or label)}**　{note}".rstrip(), ""]
    if m.get("text"):
        out += [t(m["text"]), ""]

    years = m.get("years") or []
    mt = m.get("metrics") or {}
    rows = mt.get("rows") or []
    if years and rows:
        out += ["#### ① 五个财务体征，拉长看\n"]
        body = [[t(r.get("name"))] + [t(v) for v in (r.get("values") or [])] for r in rows]
        out += [md_table(["指标"] + [t(y) for y in years], body, "l" + "c" * len(years)), ""]
        judge = mt.get("judge") or {}
        if judge:
            for v in (judge.values() if isinstance(judge, dict) else judge):
                out.append(f"- {t(v)}")
            out.append("")
    if mt.get("consistency"):
        out += [f"*{t(mt['consistency'])}*", ""]

    for idx, ch in enumerate(m.get("charts") or []):
        out += [describe_chart({**ch, "labels": ch.get("labels") or years}), ""]

    r = m.get("roic") or {}
    if r:
        out += ["#### ③ 进阶验证：ROIC 减 WACC\n"]
        body = []
        if r.get("value") is not None:
            body.append(["ROIC 投入资本回报率", f"{t(r.get('value'))}%"])
        if r.get("wacc") is not None:
            body.append(["WACC 资金成本", f"{t(r.get('wacc'))}%"])
        if r.get("spread") is not None:
            body.append(["差值（ROIC − WACC）", f"{t(r.get('spread'))}pct"])
        if body:
            out += [md_table(["项", "值"], body, "lc"), ""]
        if r.get("note"):
            out += [f"*{t(r['note'])}*", ""]

    src = m.get("sources") or []
    if src:
        out += ["#### ④ 护城河的来源（财务只是证据，这里才是答案）\n"]
        body = [[t(it.get("type")), MOAT_SRC_MD.get(str(it.get("strength", "")), "—"),
                 t(it.get("evidence"))] for it in src]
        out += [md_table(["来源", "强度", "证据"], body, "lcl"), ""]

    if m.get("verdict"):
        out += ["> " + t(m["verdict"]), ""]
    return "\n".join(out)


def b_business(b: dict) -> str:
    if not b:
        return ""
    out = ["## 三、生意本身\n"]
    if b.get("intro"):
        out += [t(b["intro"]), ""]
    segs = b.get("segments") or []
    if segs:
        rows = [[t(s.get("name")), t(s.get("rev_pct")), t(s.get("margin")),
                 t(s.get("comment"))] for s in segs]
        out += [md_table(["业务板块", "营收占比", "毛利率", "点评"], rows, "lccl"), ""]
    if b.get("moat"):
        out.append(b_moat(b["moat"]))
    for key, title in (("policy", "行业与政策"),
                       ("upstream", "上游"), ("downstream", "下游")):
        if b.get(key):
            out += [f"### {title}\n", t(b[key]), ""]
    if b.get("comment"):
        out += ["> " + t(b["comment"]), ""]
    return "\n".join(out)


def describe_chart(ch: dict) -> str:
    """把组合图的形状写成一段文字。"""
    series = ch.get("series") or []
    parts = [f"**{t(ch.get('title'))}**"]
    kind = []
    for s in series:
        stype = "柱状" if (s.get("type") or "line") == "bar" else "折线"
        axis = "右轴" if s.get("axis") == "r" else "左轴"
        kind.append(f"{t(s.get('name'))}（{stype}，{axis}）")
    parts.append("　图形构成：" + "；".join(kind) + "。")
    for s in series:
        vals = [v for v in (s.get("values") or []) if isinstance(v, (int, float))]
        if not vals:
            continue
        labels = ch.get("labels") or []
        if len(vals) == len(labels) and labels:
            lo_i, hi_i = vals.index(min(vals)), vals.index(max(vals))
            seq = " → ".join(
                f"{t(labels[i])} {v:g}" for i, v in enumerate(vals)
                if len(vals) <= 12 or i % 2 == 0 or i == len(vals) - 1
            )
            shape = (
                f"{t(s.get('name'))}：{seq}。"
                f"最低 {t(labels[lo_i])} {min(vals):g}，最高 {t(labels[hi_i])} {max(vals):g}，"
                f"首尾变动 {((vals[-1] - vals[0]) / abs(vals[0]) * 100 if vals[0] else 0):+.1f}%，"
                f"最新值 {vals[-1]:g}。"
            )
        else:
            shape = (
                f"{t(s.get('name'))}：{min(vals):g} ~ {max(vals):g}，最新 {vals[-1]:g}。"
            )
        parts.append(shape)
    if ch.get("note"):
        parts.append(t(ch["note"]))
    return "".join(parts)


def b_financials(f: dict) -> str:
    if not f:
        return ""
    out = [f"## {t(f.get('title') or '财务全景与跨年趋势研判')}\n"]
    if f.get("lead"):
        out += [t(f["lead"]), ""]

    periods = f.get("periods") or []
    qt = f.get("quarterly") or []
    if periods and qt:
        out += [f"### {t(f.get('quarterly_title') or '① 季度主表（单季口径）')}\n",
                matrix_md(periods, qt), ""]
        if f.get("quarterly_note"):
            out += [f"*{t(f['quarterly_note'])}*", ""]

    charts = f.get("charts") or []
    if charts:
        out.append(f"### {t(f.get('charts_title') or '② 跨年趋势图')}\n")
        out.append("> 以下为 HTML 报告中各张趋势图的文字读法（本 Markdown 版不插图）。\n")
        for c in charts:
            out += [describe_chart({**c, "labels": c.get("labels") or periods}), ""]

    yoy = f.get("yoy") or {}
    if yoy.get("headers"):
        out += [f"### {t(yoy.get('title') or '③ 同季同比对照')}\n",
                matrix_md(yoy["headers"], yoy.get("series") or [],
                          yoy.get("first_col", "对照项")), ""]
        if yoy.get("note"):
            out += [f"*{t(yoy['note'])}*", ""]

    cum = f.get("cumulative") or {}
    if cum.get("headers") and cum.get("series"):
        out += [f"### {t(cum.get('title') or '④ 累计口径（年报 / 中报）')}\n",
                matrix_md(cum["headers"], cum["series"], cum.get("first_col", "指标")), ""]
        if cum.get("note"):
            out += [f"*{t(cum['note'])}*", ""]

    lat = f.get("latest") or {}
    if lat:
        head = t(lat.get("title") or "最新一期财报")
        if lat.get("period"):
            head += f"（{t(lat.get('period'))}）"
        out += [f"### {head}\n"]
        if lat.get("comment"):
            out += [t(lat["comment"]), ""]
        items = lat.get("items") or []
        if items:
            rows = [[t(i.get("label")), t(i.get("value")), t(i.get("yoy")),
                     t(i.get("note"))] for i in items]
            out += [md_table(["项目", "数值", "同比", "说明"], rows, "lccl"), ""]
        sigs = lat.get("signals") or []
        if sigs:
            out.append("**三项改善信号判定**\n")
            for s in sigs:
                out.append(
                    f"- **{t(s.get('name'))}**：{t(s.get('result'))}"
                    f"　口径：{t(s.get('reason'))}"
                )
            out.append("")

    bs = f.get("balance") or {}
    if bs:
        out += [f"### {t(bs.get('title') or '资产负债与安全边际')}\n"]
        if bs.get("comment"):
            out += [t(bs["comment"]), ""]
        items = bs.get("items") or []
        if items:
            rows = [[t(i.get("label")), t(i.get("value")), t(i.get("note"))] for i in items]
            out += [md_table(["科目", "金额", "说明"], rows, "lcl"), ""]
        risks = bs.get("risks") or []
        if risks:
            rows = [[t(r.get("name")), t(r.get("value")), t(r.get("level")),
                     t(r.get("threshold"))] for r in risks]
            out += ["**四项安全判定**\n",
                    md_table(["指标", "数值", "判定", "阈值与说明"], rows, "lccl"), ""]

    ins = f.get("insights") or []
    if ins:
        out += [f"### {t(f.get('insights_title') or '跨年趋势归纳')}\n"]
        for it in ins:
            tag = t(it.get("tag") or it.get("dim") or "")
            title_txt = t(it.get("title"))
            out.append(f"**[{tag}] {title_txt}**\n")
            pts = it.get("points") or []
            if pts:
                out += [bullets(pts), ""]
    return "\n".join(out)


def b_trends(tr: dict) -> str:
    """旧版独立趋势块（兼容）。"""
    if not tr or not (tr.get("series") and tr.get("years")):
        return ""
    rows = [[t(s.get("name")), *[t(v) for v in (s.get("values") or [])]]
            for s in tr["series"]]
    out = [f"## {t(tr.get('title', '多年财务趋势'))}\n",
           md_table(["指标", *[t(y) for y in tr["years"]]], rows), ""]
    if tr.get("comment"):
        out.append(t(tr["comment"]) + "\n")
    return "\n".join(out)


def b_latest_old(l: dict) -> str:
    if not l:
        return ""
    out = [f"## 最新财报解读（{t(l.get('period'))}）\n"]
    if l.get("comment"):
        out += [t(l["comment"]), ""]
    items = l.get("items") or []
    if items:
        rows = [[t(i.get("label")), t(i.get("value")), t(i.get("yoy")), t(i.get("note"))]
                for i in items]
        out += [md_table(["项目", "数值", "同比", "说明"], rows, "lccl"), ""]
    sigs = l.get("signals") or []
    if sigs:
        out.append("**三项改善信号判定**\n")
        for s in sigs:
            out.append(f"- **{t(s.get('name'))}**：{t(s.get('result'))}　{t(s.get('reason'))}")
        out.append("")
    return "\n".join(out)


def b_balance_old(bs: dict) -> str:
    if not bs:
        return ""
    out = ["## 资产负债与安全边际\n"]
    if bs.get("comment"):
        out += [t(bs["comment"]), ""]
    items = bs.get("items") or []
    if items:
        rows = [[t(i.get("label")), t(i.get("value")), t(i.get("note"))] for i in items]
        out += [md_table(["科目", "金额", "说明"], rows, "lcl"), ""]
    risks = bs.get("risks") or []
    if risks:
        rows = [[t(r.get("name")), t(r.get("value")), t(r.get("level")),
                 t(r.get("threshold"))] for r in risks]
        out += [md_table(["指标", "数值", "判定", "阈值与说明"], rows, "lccl"), ""]
    return "\n".join(out)


def b_redflags(items: list[dict], title: str = "排雷扫描") -> str:
    if not items:
        return ""
    hits = [r for r in items if r.get("hit")]
    out = [f"## {t(redflag_head(title, items))}\n"]
    if not hits:
        out.append("暂未命中已知的高危组合信号。\n")
    else:
        rows = [[t(r.get("level")),
                 (f"#{t(r.get('id'))} " if r.get("id") is not None else "") + t(r.get("text")),
                 t(r.get("evidence"))] for r in hits]
        out += [md_table(["等级", "信号", "依据"], rows, "cll"), ""]
    return "\n".join(out)


def b_scorecard(sc: dict, title: str = "七步研判") -> str:
    if not sc:
        return ""
    out = [f"## {t(title)}\n"]
    steps = sc.get("steps") or []
    if steps:
        rows = [[t(s.get("no")), t(s.get("name")),
                 t(s.get("state_text") or STATE_TXT.get(str(s.get("state", "na")).lower(), "无数据")),
                 t(s.get("conclusion"))] for s in steps]
        out += [md_table(["步", "维度", "结论", "要点"], rows, "clll"), ""]
    items = sc.get("items") or []
    if items:
        out.append("**加权评分**\n")
        rows = []
        for i in items:
            v = i.get("value")
            if v is None:                       # 不可评（数据缺口）：不计分、不进分母
                rows.append([t(i.get("dim")), "不可评", f"×{t(i.get('weight'))}",
                             "—（缺数据，不计入分母）"])
            else:
                rows.append([t(i.get("dim")), f"{float(v):+.0f}",
                             f"×{t(i.get('weight'))}",
                             str(round(float(v) * float(i.get("weight", 1)), 1))])
        out += [md_table(["维度", "分值", "权重", "加权"], rows, "lccc"), ""]
        scored = [i for i in items if i.get("value") is not None]
        total = sum(float(i["value"]) * float(i.get("weight", 1)) for i in scored)
        maxv = sum(abs(float(i.get("weight", 1))) * 2 for i in scored)
        line = f"**加权总分：{total:+.0f} / 满分 {maxv:.0f}**"
        declared = sc.get("total")
        if declared:
            m2 = re.match(r"\s*([+-]?\d+)", str(declared))
            if not m2 or abs(int(m2.group(1)) - total) > 0.5:
                line += f"（⚠ 与 JSON 标注值 {t(declared)} 不一致，以实算为准）"
        if len(scored) < len(items):
            rate = (total / maxv * 100) if maxv else 0
            line += f"（可评 {len(scored)} / {len(items)} 项，归一化得分率 {rate:.1f}%）"
        out += [line, ""]
        if sc.get("total_note"):
            out += [t(sc["total_note"]), ""]
    return "\n".join(out)


def b_conclusion(c: dict, title: str = "综合研判") -> str:
    if not c:
        return ""
    out = [f"## {t(title)}\n"]
    out += [t(p) + "\n" for p in (c.get("paragraphs") or [])]
    if c.get("watchlist"):
        out += ["### 后续跟踪清单\n", bullets(c["watchlist"], "1."), ""]
    if c.get("triggers"):
        out += ["### 判断修正的触发条件\n", bullets(c["triggers"]), ""]
    return "\n".join(out)


def b_gaps(items: list, title: str = "数据缺口与口径风险") -> str:
    if not items:
        return ""
    out = [f"## {t(title)}\n"]
    for g in items:
        out.append(f"- {t(g)}")
    out.append("")
    return "\n".join(out)


def b_sources(items: list) -> str:
    if not items:
        return ""
    out = ["## 数据来源与口径\n"]
    for s in items:
        name = s.get("name") if isinstance(s, dict) else s
        detail = s.get("detail") if isinstance(s, dict) else ""
        out.append(f"- **{t(name)}**：{t(detail)}")
    out.append("")
    return "\n".join(out)


def render_md(data: dict) -> str:
    m = data.get("meta") or {}
    has_new = bool(data.get("financials"))
    blocks = [
        b_title(m), b_head(m), b_verdict(data.get("verdict") or {}),
        # 顺序与编号、与笔记范式一致：先看股价位置，再看估值，再看生意，最后看财务
        b_price(data.get("price") or {}),
        b_metrics(data.get("core_metrics") or [], "二、核心指标与估值"),
        b_business(data.get("business") or {}),
        b_financials(data.get("financials") or {}),
        *([] if has_new else [
            b_trends(data.get("trends") or {}),
            b_latest_old(data.get("latest") or {}),
            b_balance_old(data.get("balance") or {}),
        ]),
        # v1 结构多出三块，编号整体后移一位（与 HTML 版一致）
        b_redflags(data.get("redflags") or [],
                   data.get("redflags_title") or ("五、排雷扫描" if has_new else "六、排雷扫描")),
        b_scorecard(data.get("scorecard") or {},
                    data.get("scorecard_title") or ("六、七步研判" if has_new else "七、七步研判")),
        b_conclusion(data.get("conclusion") or {},
                     data.get("conclusion_title") or ("七、综合研判" if has_new else "八、综合研判")),
        b_gaps(data.get("data_gaps") or []),
        b_sources(data.get("sources") or []),
    ]
    body = "\n".join(b for b in blocks if b)
    if m.get("report_date"):
        _at = f"　·　行情时点 {t(m['price_at'])}" if m.get("price_at") else ""
        body += (f"\n---\n\n*{t(m['report_date'])} 生成{_at}　·　"
                 f"本报告基于公开数据整理，仅供参考，不构成投资建议*\n")
    # 收敛多余空行
    while "\n\n\n\n" in body:
        body = body.replace("\n\n\n\n", "\n\n\n")
    return body


def main() -> int:
    ap = argparse.ArgumentParser(description="个股分析 JSON → Markdown 报告")
    ap.add_argument("json_path", help="数据 JSON 文件路径")
    ap.add_argument("-o", "--out", help="输出 Markdown 路径，默认同目录 report.md")
    args = ap.parse_args()

    src = Path(args.json_path).expanduser()
    if not src.exists():
        print(f"错误：找不到 {src}", file=sys.stderr)
        return 1
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"错误：JSON 解析失败 {e}", file=sys.stderr)
        return 1

    out = Path(args.out).expanduser() if args.out else src.with_name("report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    text = render_md(data)
    out.write_text(text, encoding="utf-8")
    kb = len(text.encode("utf-8")) / 1024
    print(f"已生成：{out}  （{kb:.1f} KB，{text.count(chr(10)) + 1} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
