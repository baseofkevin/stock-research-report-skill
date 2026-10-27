#!/usr/bin/env python3
"""把个股分析数据 JSON 渲染成美化的 HTML 报告。

用法:
    python3 render_report.py data.json -o 报告.html
    python3 render_report.py data.json            # 默认输出到同目录 report.html

JSON 结构见 scripts/sample.json（所有字段都可省略，缺失的区块会自动隐藏）。
设计原则：任何字段缺失都不能让渲染崩溃——宁可少一块，也不要报错。
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 样式

CSS = """
:root{
  --ink:#1f2430; --sub:#5b6472; --line:#e3e0da; --bg:#f7f5f1;
  --card:#fff; --accent:#8b1a1a; --accent-soft:#f6ece9;
  --up:#c0392b; --down:#1e8449; --warn:#c77f08; --ok:#1e8449;
  --risk:#c0392b; --mid:#c77f08;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Noto Serif CJK SC","Source Han Serif SC","Songti SC",serif;
  font-size:15px; line-height:1.78;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:0 20px 60px}

/* ---------- 头部 ---------- */
.hero{
  background:linear-gradient(135deg,#8b1a1a 0%,#5e1414 55%,#3d0f0f 100%);
  color:#fff; padding:34px 0 30px; margin-bottom:26px;
  box-shadow:0 2px 14px rgba(0,0,0,.18);
}
.hero .wrap{padding-bottom:0}
.hero-top{display:flex; align-items:baseline; gap:14px; flex-wrap:wrap}
.hero h1{margin:0; font-size:30px; font-weight:700; letter-spacing:.5px}
.hero .code{
  font-family:"DejaVu Sans Mono",monospace; font-size:15px;
  background:rgba(255,255,255,.16); padding:3px 10px; border-radius:4px;
}
.hero .tagline{margin-top:8px; font-size:14px; opacity:.85}
.hero-metrics{display:flex; gap:34px; margin-top:22px; flex-wrap:wrap}
.hm-label{font-size:12px; opacity:.75; letter-spacing:1px}
.hm-value{font-size:24px; font-weight:700; font-family:"DejaVu Sans Mono",monospace}
.hm-sub{font-size:12.5px; opacity:.8}

/* ---------- 通用区块 ---------- */
section{
  background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:22px 26px 24px; margin-bottom:20px;
  box-shadow:0 1px 3px rgba(0,0,0,.04);
}
h2{
  font-family:"Noto Sans CJK SC",sans-serif; font-size:19px; margin:0 0 16px;
  padding-left:11px; border-left:4px solid var(--accent); color:#161a22;
}
h3{
  font-family:"Noto Sans CJK SC",sans-serif; font-size:15.5px; margin:20px 0 9px;
  color:#3a4252;
}
p{margin:0 0 11px}
p:last-child{margin-bottom:0}
.muted{color:var(--sub)}

/* ---------- 结论卡 ---------- */
.verdict{border-left:5px solid var(--accent)}
.vhead{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:12px}
.stance{
  font-family:"Noto Sans CJK SC",sans-serif; font-weight:700; font-size:20px;
  padding:5px 16px; border-radius:5px; color:#fff;
}
.st-good{background:var(--ok)} .st-mid{background:var(--mid)}
.st-bad{background:var(--risk)} .st-watch{background:#4a6fa5}
.chips{display:flex; gap:8px; flex-wrap:wrap; margin-top:14px}
.chip{
  font-family:"Noto Sans CJK SC",sans-serif; font-size:12.5px;
  padding:4px 11px; border-radius:13px; background:var(--accent-soft);
  color:var(--accent); border:1px solid #eddcd8;
}
.chip.warn{background:#fdf4e3; color:#8a5d00; border-color:#f0e0bd}
.chip.bad{background:#fbeae8; color:#8f2018; border-color:#f2d6d2}

/* ---------- 指标卡 ---------- */
.grid{display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(158px,1fr))}
.metric{
  border:1px solid var(--line); border-radius:6px; padding:12px 13px; background:#fcfbfa;
}
.metric.warn{background:#fdf8ef; border-color:#f0e2c4}
.metric.bad{background:#fdf3f1; border-color:#f2d8d3}
.m-label{font-size:12.5px; color:var(--sub); margin-bottom:3px}
.m-value{
  font-family:"DejaVu Sans Mono",monospace; font-size:19px; font-weight:700; color:#161a22;
}
.m-note{font-size:12px; color:#7a8494; margin-top:4px; line-height:1.5}

/* ---------- 表格 ---------- */
table{
  width:100%; border-collapse:collapse;
  font-family:"Noto Sans CJK SC",sans-serif; font-size:13.5px; margin:6px 0 4px;
}
th{
  background:#f2efe9; text-align:left; padding:9px 11px; font-weight:700;
  border-bottom:1.5px solid #d9d3c8; color:#3a4252; white-space:nowrap;
}
td{padding:9px 11px; border-bottom:1px solid #eeebe5; vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:#fbfaf8}
.num{font-family:"DejaVu Sans Mono",monospace; white-space:nowrap}
.up{color:var(--up); font-weight:600}
.down{color:var(--down); font-weight:600}
.center{text-align:center}

.lv{font-family:"Noto Sans CJK SC",sans-serif; font-size:12px; font-weight:700;
    padding:2px 9px; border-radius:3px; color:#fff; white-space:nowrap}
.lv-high{background:var(--risk)} .lv-mid{background:var(--mid)}
.lv-ok{background:var(--ok)} .lv-na{background:#97a0ad}

/* ---------- 信号行 ---------- */
.signal{
  display:flex; gap:12px; align-items:flex-start; padding:11px 13px;
  border:1px solid var(--line); border-left:4px solid var(--lv,#ccc);
  border-radius:5px; margin-bottom:9px; background:#fcfbfa;
}
.signal.pass{border-left-color:var(--ok)}
.signal.fail{border-left-color:var(--risk)}
.signal.na{border-left-color:#97a0ad}
.s-name{
  font-family:"Noto Sans CJK SC",sans-serif; font-weight:700; font-size:13.5px;
  min-width:118px;
}
.s-body{flex:1; font-size:13.5px}
.s-reason{color:var(--sub); font-size:12.5px; margin-top:2px}

/* ---------- 评分条 ---------- */
.bar-row{display:flex; align-items:center; gap:12px; margin-bottom:9px; font-size:13.5px}
.bar-name{font-family:"Noto Sans CJK SC",sans-serif; min-width:104px; color:#3a4252}
.bar-track{flex:1; height:9px; background:#eceae5; border-radius:5px; overflow:hidden}
.bar-fill{height:100%; border-radius:5px; background:linear-gradient(90deg,#9d2a2a,#c0392b)}
.bar-fill.neg{background:linear-gradient(90deg,#14663a,#1e8449)}
.bar-val{font-family:"DejaVu Sans Mono",monospace; min-width:56px; text-align:right; font-size:13px}

/* ---------- 走势图 ---------- */
.chart-box{border:1px solid var(--line); border-radius:6px; padding:14px; background:#fcfbfa}
.chart-box svg{width:100%; height:auto; display:block}

/* ---------- 结论 ---------- */
.concl p{margin-bottom:13px; text-align:justify}
ol.watch,ul.watch{padding-left:22px; margin:0}
ol.watch li,ul.watch li{margin-bottom:8px}
ol.watch li::marker{color:var(--accent); font-weight:700}

blockquote{
  margin:12px 0; padding:11px 15px; border-left:3px solid #cbb9a4;
  background:#fbf8f4; font-size:14px; color:#4a4038;
}

.src{font-size:12.5px; color:var(--sub); line-height:1.9}
footer{
  text-align:center; color:#8b93a1; font-size:12.5px; padding:22px 10px 0;
  border-top:1px solid var(--line); margin-top:8px;
}

@media print{
  body{background:#fff} .hero{background:#8b1a1a !important; -webkit-print-color-adjust:exact}
  section{box-shadow:none; page-break-inside:avoid} .wrap{max-width:100%}
}
@media (max-width:640px){
  .hero h1{font-size:23px} .hero-metrics{gap:20px} .wrap{padding:0 14px 40px}
  section{padding:18px 15px} table{font-size:12.5px} th,td{padding:7px 8px}
  .s-name{min-width:auto}
}
"""

# ---------------------------------------------------------------- 工具


def esc(v: Any) -> str:
    """转 HTML，空值统一显示占位符。"""
    if v is None or v == "":
        return "—"
    return html.escape(str(v))


def get(d: Any, *keys, default=None):
    """安全取嵌套字典。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def cls_num(s: Any) -> str:
    """给同比增速字符串加涨跌色（A 股习惯：涨红跌绿）。"""
    t = str(s)
    if t.startswith("+") or (t and t[0].isdigit() and "增长" in t):
        return "up"
    if t.startswith("-") or "下降" in t or "减少" in t:
        return "down"
    return ""


def svg_chart(points: list[dict], unit: str = "元") -> str:
    """用季度收盘价画一张简洁的折线面积图。"""
    vals = [float(p["value"]) for p in points if p.get("value") is not None]
    labels = [str(p.get("label", "")) for p in points if p.get("value") is not None]
    if len(vals) < 2:
        return ""

    w, h = 980, 260
    pad_l, pad_r, pad_t, pad_b = 56, 18, 18, 34
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    lo -= span * 0.12
    hi += span * 0.12
    rng = hi - lo

    def x(i: int) -> float:
        return pad_l + (w - pad_l - pad_r) * i / (len(vals) - 1)

    def y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (hi - v) / rng

    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    area = f"{pad_l},{h - pad_b} " + line + f" {w - pad_r},{h - pad_b}"

    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="股价走势">',
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#8b1a1a" stop-opacity=".26"/>'
        '<stop offset="100%" stop-color="#8b1a1a" stop-opacity=".02"/>'
        "</linearGradient></defs>",
    ]
    # 网格与纵轴刻度
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        yy = pad_t + (h - pad_t - pad_b) * frac
        vv = hi - rng * frac
        parts.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{w - pad_r}" y2="{yy:.1f}" '
            f'stroke="#e6e3dd" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#8b93a1">{vv:.2f}</text>'
        )
    parts.append(f'<polygon points="{area}" fill="url(#g)"/>')
    parts.append(
        f'<polyline points="{line}" fill="none" stroke="#8b1a1a" '
        f'stroke-width="2.2" stroke-linejoin="round"/>'
    )
    # 末点强调
    parts.append(
        f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="4" '
        f'fill="#fff" stroke="#8b1a1a" stroke-width="2.2"/>'
    )
    # 首末数值标注
    parts.append(
        f'<text x="{x(len(vals) - 1):.1f}" y="{y(vals[-1]) - 11:.1f}" text-anchor="end" '
        f'font-size="12.5" font-weight="700" fill="#8b1a1a">{vals[-1]:.2f}{unit}</text>'
    )
    # 横轴标签（稀疏显示）
    step = max(1, len(labels) // 9)
    for i, lb in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            parts.append(
                f'<text x="{x(i):.1f}" y="{h - pad_b + 17}" text-anchor="middle" '
                f'font-size="11" fill="#8b93a1">{html.escape(lb)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- 区块渲染


def sec_metrics(title: str, items: list[dict]) -> str:
    if not items:
        return ""
    cells = []
    for it in items:
        flag = it.get("flag", "")
        cells.append(
            f'<div class="metric {flag}">'
            f'<div class="m-label">{esc(it.get("label"))}</div>'
            f'<div class="m-value">{esc(it.get("value"))}</div>'
            f'<div class="m-note">{esc(it.get("note"))}</div>'
            "</div>"
        )
    return f"<section><h2>{esc(title)}</h2><div class='grid'>{''.join(cells)}</div></section>"


def sec_verdict(v: dict) -> str:
    if not v:
        return ""
    level = str(v.get("level", "")).lower()
    stance_map = {
        "good": "st-good", "mid": "st-mid", "bad": "st-bad", "watch": "st-watch",
    }
    cls = stance_map.get(level, "st-watch")
    out = [
        '<section class="verdict">',
        '<div class="vhead">',
        f'<span class="stance {cls}">{esc(v.get("stance", "待判断"))}</span>',
        f'<span class="muted">{esc(v.get("headline"))}</span>',
        "</div>",
        f"<p>{esc(v.get('summary'))}</p>",
    ]
    tags = v.get("tags") or []
    if tags:
        out.append('<div class="chips">')
        for t in tags:
            kind = t.get("kind", "")
            out.append(f'<span class="chip {kind}">{esc(t.get("text"))}</span>')
        out.append("</div>")
    out.append("</section>")
    return "".join(out)


def sec_price(data: dict) -> str:
    """股价位置区块：历史区间 + 季 K 走势图。"""
    if not data:
        return ""
    out = ["<section><h2>一、股价位置</h2>"]
    rows = data.get("records") or []
    if rows:
        out.append(
            "<table><thead><tr><th>周期</th><th>最高 / 最低</th>"
            "<th>说明</th></tr></thead><tbody>"
        )
        for r in rows:
            out.append(
                f"<tr><td>{esc(r.get('name'))}</td>"
                f"<td class='num'>{esc(r.get('range'))}</td>"
                f"<td>{esc(r.get('note'))}</td></tr>"
            )
        out.append("</tbody></table>")
    if data.get("chart_data"):
        title = data.get("chart_title", "季度收盘走势")
        unit = data.get("unit", "元")
        svg = svg_chart(data["chart_data"], unit)
        if svg:
            out.append(
                f'<h3>{esc(title)}</h3><div class="chart-box">{svg}</div>'
            )
    if data.get("comment"):
        out.append(f"<p style='margin-top:14px'>{esc(data['comment'])}</p>")
    out.append("</section>")
    return "".join(out)


def sec_business(b: dict) -> str:
    if not b:
        return ""
    out = ["<section><h2>三、生意本身</h2>"]
    if b.get("intro"):
        out.append(f"<p>{esc(b['intro'])}</p>")
    segs = b.get("segments") or []
    if segs:
        out.append(
            "<table><thead><tr><th>业务板块</th><th>营收占比</th>"
            "<th>毛利率</th><th>点评</th></tr></thead><tbody>"
        )
        for s in segs:
            out.append(
                f"<tr><td>{esc(s.get('name'))}</td>"
                f"<td class='num'>{esc(s.get('rev_pct'))}</td>"
                f"<td class='num'>{esc(s.get('margin'))}</td>"
                f"<td>{esc(s.get('comment'))}</td></tr>"
            )
        out.append("</tbody></table>")
    for key, title in (("moat", "护城河"), ("policy", "行业与政策"),
                       ("upstream", "上游"), ("downstream", "下游")):
        if b.get(key):
            out.append(f"<h3>{title}</h3><p>{esc(b[key])}</p>")
    if b.get("comment"):
        out.append(f"<blockquote>{esc(b['comment'])}</blockquote>")
    out.append("</section>")
    return "".join(out)


def sec_trends(t: dict) -> str:
    """多年财务趋势表。"""
    if not t or not (t.get("series") and t.get("years")):
        return ""
    years = t["years"]
    out = [
        f"<section><h2>{esc(t.get('title', '多年财务趋势'))}</h2>",
        "<table><thead><tr><th>指标</th>",
    ]
    for y in years:
        out.append(f"<th class='center'>{esc(y)}</th>")
    out.append("</tr></thead><tbody>")
    for s in t["series"]:
        out.append(f"<tr><td>{esc(s.get('name'))}</td>")
        vals = s.get("values") or []
        for v in vals:
            out.append(f"<td class='num center'>{esc(v)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    if t.get("comment"):
        out.append(f"<p style='margin-top:12px'>{esc(t['comment'])}</p>")
    out.append("</section>")
    return "".join(out)


def sec_latest(l: dict) -> str:
    """最新一期财报解读。"""
    if not l:
        return ""
    out = [f"<section><h2>四、最新财报解读（{esc(l.get('period'))}）</h2>"]
    if l.get("comment"):
        out.append(f"<p>{esc(l['comment'])}</p>")
    items = l.get("items") or []
    if items:
        out.append(
            "<table><thead><tr><th>项目</th><th class='center'>数值</th>"
            "<th class='center'>同比</th><th>说明</th></tr></thead><tbody>"
        )
        for it in items:
            out.append(
                f"<tr><td>{esc(it.get('label'))}</td>"
                f"<td class='num center'>{esc(it.get('value'))}</td>"
                f"<td class='num center {cls_num(it.get('yoy'))}'>{esc(it.get('yoy'))}</td>"
                f"<td>{esc(it.get('note'))}</td></tr>"
            )
        out.append("</tbody></table>")
    sigs = l.get("signals") or []
    if sigs:
        out.append("<h3>三项改善信号判定</h3>")
        for s in sigs:
            st = str(s.get("state", "na")).lower()
            out.append(
                f'<div class="signal {st}">'
                f'<div class="s-name">{esc(s.get("name"))}</div>'
                f'<div class="s-body">{esc(s.get("result"))}'
                f'<div class="s-reason">{esc(s.get("reason"))}</div></div>'
                "</div>"
            )
    out.append("</section>")
    return "".join(out)


def sec_balance(bs: dict) -> str:
    """资产负债表明细 + 安全指标。"""
    if not bs:
        return ""
    out = ["<section><h2>五、资产负债与安全边际</h2>"]
    if bs.get("comment"):
        out.append(f"<p>{esc(bs['comment'])}</p>")
    items = bs.get("items") or []
    if items:
        out.append(
            "<table><thead><tr><th>科目</th><th class='center'>金额</th>"
            "<th>说明</th></tr></thead><tbody>"
        )
        for it in items:
            out.append(
                f"<tr><td>{esc(it.get('label'))}</td>"
                f"<td class='num center'>{esc(it.get('value'))}</td>"
                f"<td>{esc(it.get('note'))}</td></tr>"
            )
        out.append("</tbody></table>")
    risks = bs.get("risks") or []
    if risks:
        out.append("<h3>四项安全指标</h3>")
        out.append(
            "<table><thead><tr><th>指标</th><th class='center'>数值</th>"
            "<th class='center'>判定</th><th>阈值与说明</th></tr></thead><tbody>"
        )
        lv_map = {"高危": "lv-high", "关注": "lv-mid", "紧张": "lv-mid",
                  "正常": "lv-ok", "健康": "lv-ok", "无数据": "lv-na"}
        for r in risks:
            lv = str(r.get("level", "无数据"))
            cls = next((v for k, v in lv_map.items() if lv.startswith(k)), "lv-na")
            out.append(
                f"<tr><td>{esc(r.get('name'))}</td>"
                f"<td class='num center'>{esc(r.get('value'))}</td>"
                f"<td class='center'><span class='lv {cls}'>{esc(lv)}</span></td>"
                f"<td>{esc(r.get('threshold'))}</td></tr>"
            )
        out.append("</tbody></table>")
    out.append("</section>")
    return "".join(out)


def sec_redflags(items: list[dict]) -> str:
    if not items:
        return ""
    hits = [r for r in items if r.get("hit")]
    out = [
        f"<section><h2>六、排雷扫描（命中 {len(hits)} / {len(items)} 项）</h2>",
    ]
    if not hits:
        out.append("<p>暂未命中已知的高危组合信号。</p>")
    else:
        out.append(
            "<table><thead><tr><th class='center'>等级</th><th>信号</th>"
            "<th>依据</th></tr></thead><tbody>"
        )
        lv_map = {"高危": "lv-high", "危险": "lv-high", "关注": "lv-mid",
                  "警告": "lv-mid", "留意": "lv-mid"}
        for r in hits:
            lv = str(r.get("level", "关注"))
            cls = next((v for k, v in lv_map.items() if lv.startswith(k)), "lv-mid")
            out.append(
                f"<tr><td class='center'><span class='lv {cls}'>{esc(lv)}</span></td>"
                f"<td>{esc(r.get('text'))}</td>"
                f"<td class='muted'>{esc(r.get('evidence'))}</td></tr>"
            )
        out.append("</tbody></table>")
    out.append("</section>")
    return "".join(out)


def sec_scorecard(sc: dict) -> str:
    """七步研判结论 + 加权评分条。"""
    if not sc:
        return ""
    out = ["<section><h2>七、七步研判</h2>"]
    steps = sc.get("steps") or []
    if steps:
        out.append(
            "<table><thead><tr><th class='center'>步</th><th>维度</th>"
            "<th class='center'>结论</th><th>要点</th></tr></thead><tbody>"
        )
        st_map = {"pass": "lv-ok", "fail": "lv-high", "warn": "lv-mid", "na": "lv-na"}
        txt_map = {"pass": "通过", "fail": "否决", "warn": "存疑", "na": "无数据"}
        for s in steps:
            raw = str(s.get("state", "na")).lower()
            cls = st_map.get(raw, "lv-na")
            txt = s.get("state_text") or txt_map.get(raw, "无数据")
            out.append(
                f"<tr><td class='center'>{esc(s.get('no'))}</td>"
                f"<td>{esc(s.get('name'))}</td>"
                f"<td class='center'><span class='lv {cls}'>{esc(txt)}</span></td>"
                f"<td>{esc(s.get('conclusion'))}</td></tr>"
            )
        out.append("</tbody></table>")
    items = sc.get("items") or []
    if items:
        out.append("<h3>加权评分</h3>")
        max_abs = max((abs(float(i.get("value", 0))) for i in items), default=1) or 1
        for i in items:
            val = float(i.get("value", 0))
            w = int(100 * abs(val) / max_abs)
            neg = "neg" if val < 0 else ""
            out.append(
                f'<div class="bar-row"><div class="bar-name">{esc(i.get("dim"))}</div>'
                f'<div class="bar-track"><div class="bar-fill {neg}" style="width:{w}%">'
                f"</div></div>"
                f'<div class="bar-val">{val:+.0f} ×{esc(i.get("weight"))}</div></div>'
            )
        if sc.get("total") is not None:
            out.append(
                f'<p style="margin-top:12px"><strong>加权总分：{esc(sc["total"])}</strong>'
                f'<span class="muted">　{esc(sc.get("total_note"))}</span></p>'
            )
    out.append("</section>")
    return "".join(out)


def sec_conclusion(c: dict) -> str:
    if not c:
        return ""
    out = ["<section class='concl'><h2>八、综合研判</h2>"]
    for p in c.get("paragraphs") or []:
        out.append(f"<p>{esc(p)}</p>")
    if c.get("watchlist"):
        out.append("<h3>后续跟踪清单</h3><ol class='watch'>")
        for w in c["watchlist"]:
            out.append(f"<li>{esc(w)}</li>")
        out.append("</ol>")
    if c.get("triggers"):
        out.append("<h3>判断修正的触发条件</h3><ul class='watch'>")
        for t in c["triggers"]:
            out.append(f"<li>{esc(t)}</li>")
        out.append("</ul>")
    out.append("</section>")
    return "".join(out)


def sec_sources(items: list) -> str:
    if not items:
        return ""
    out = ["<section><h2>数据来源与口径</h2><div class='src'>"]
    for s in items:
        name = s.get("name") if isinstance(s, dict) else s
        detail = s.get("detail") if isinstance(s, dict) else ""
        out.append(f"· {esc(name)}　{esc(detail)}<br>")
    out.append("</div></section>")
    return "".join(out)


# ---------------------------------------------------------------- 组装


def build_hero(m: dict) -> str:
    if not m:
        return ""
    chg = str(m.get("change_pct", ""))
    cls = cls_num(chg)
    metrics = [
        ("最新价", f"{esc(m.get('price'))}", esc(m.get("unit", "元"))),
        ("涨跌幅", esc(chg), esc(m.get("chg_note", ""))),
        ("总市值", esc(m.get("market_cap")), esc(m.get("cap_note", ""))),
        ("所属行业", esc(m.get("industry")), esc(m.get("industry_note", ""))),
    ]
    cells = "".join(
        f'<div><div class="hm-label">{esc(a)}</div>'
        f'<div class="hm-value {cls if i == 1 else ""}">{b}</div>'
        f'<div class="hm-sub">{c}</div></div>'
        for i, (a, b, c) in enumerate(metrics)
    )
    return (
        '<div class="hero"><div class="wrap">'
        '<div class="hero-top">'
        f'<h1>{esc(m.get("name"))}</h1>'
        f'<span class="code">{esc(m.get("code"))}</span>'
        "</div>"
        f'<div class="tagline">{esc(m.get("tagline"))}</div>'
        f'<div class="hero-metrics">{cells}</div>'
        "</div></div>"
    )


def render(data: dict) -> str:
    m = data.get("meta") or {}
    title = f'{m.get("name", "个股")}（{m.get("code", "")}）企业信息解读'
    body = "".join([
        build_hero(m),
        sec_verdict(data.get("verdict") or {}),
        sec_metrics("二、核心指标", data.get("core_metrics") or []),
        sec_price(data.get("price") or {}),
        sec_business(data.get("business") or {}),
        sec_trends(data.get("trends") or {}),
        sec_latest(data.get("latest") or {}),
        sec_balance(data.get("balance") or {}),
        sec_redflags(data.get("redflags") or []),
        sec_scorecard(data.get("scorecard") or {}),
        sec_conclusion(data.get("conclusion") or {}),
        sec_sources(data.get("sources") or []),
    ])
    date_line = ""
    if m.get("report_date"):
        date_line = f'<footer>{esc(m["report_date"])} 生成　·　' \
                    f'本 报 告 基于公开数据整理，仅供参考，不构成投资建议</footer>'
    return (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f'<body>{body}<div class="wrap">{date_line}</div></body></html>'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="个股分析 JSON → 美化 HTML 报告")
    ap.add_argument("json_path", help="数据 JSON 文件路径")
    ap.add_argument("-o", "--out", help="输出 HTML 路径，默认与 JSON 同目录 report.html")
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

    out = Path(args.out).expanduser() if args.out else src.with_name("report.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"已生成：{out}  （{out.stat().st_size / 1024:.1f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
