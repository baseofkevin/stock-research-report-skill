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
import re
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
h4{
  font-family:"Noto Sans CJK SC",sans-serif; font-size:14px; margin:16px 0 7px;
  color:#4a5464; font-weight:700;
}
p{margin:0 0 11px}
p:last-child{margin-bottom:0}
.muted{color:var(--sub)}
.lead{
  font-size:15px; line-height:1.85; background:#fbf8f4; border:1px solid #ece4d8;
  border-radius:6px; padding:13px 16px; margin-bottom:18px;
}

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
.tbl-scroll{overflow-x:auto; margin:6px 0 4px; -webkit-overflow-scrolling:touch}
table{
  width:100%; border-collapse:collapse; min-width:520px;
  font-family:"Noto Sans CJK SC",sans-serif; font-size:13.5px; margin:0;
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
td.rowhead{
  font-weight:700; color:#3a4252; white-space:nowrap;
  background:#fbfaf8; border-right:1px solid #eeebe5;
}

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
.bar-fill.na{background:repeating-linear-gradient(45deg,#ecebe7,#ecebe7 6px,#f7f5f1 6px,#f7f5f1 12px)}
.bar-val.muted{font-size:11.5px;color:#8b93a1}
.bar-row.na .bar-name{color:#8b93a1}
.bar-fill{height:100%; border-radius:5px; background:linear-gradient(90deg,#9d2a2a,#c0392b)}
.bar-fill.neg{background:linear-gradient(90deg,#14663a,#1e8449)}
.bar-val{font-family:"DejaVu Sans Mono",monospace; min-width:56px; text-align:right; font-size:13px}

/* ---------- 走势图 ---------- */
.chart-box{border:1px solid var(--line); border-radius:6px; padding:14px; background:#fcfbfa}
.chart-box svg{width:100%; height:auto; display:block}
.chart-note{font-size:12.5px; color:var(--sub); margin-top:10px; line-height:1.7}
.val-item{border:1px solid var(--line); border-radius:6px; padding:14px 16px 6px;
  background:#fcfbfa; margin-bottom:14px}
.val-head{display:flex; align-items:baseline; gap:11px; flex-wrap:wrap; margin-bottom:8px}
.val-name{font-weight:700; font-size:14.5px; color:#3a4252}
.val-cur{font-family:"DejaVu Sans Mono",monospace; font-size:20px; font-weight:700; color:#9d2a2a}
.val-sub{font-size:12.5px; color:var(--sub)}
.val-note{font-size:12.5px; color:var(--sub); margin:2px 0 0}
.moat-head{display:flex; align-items:center; gap:9px; margin:6px 0 10px}
.moat-sub{font-size:12.5px; color:var(--sub)}
.moat-judge{margin:10px 0 4px}
.moat-kpi{display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:10px; margin:12px 0 6px}
.moat-kpi .box{border:1px solid var(--line); border-radius:6px; padding:11px 13px; background:#fcfbfa}
.moat-kpi .k{font-size:12px; color:var(--sub); margin-bottom:5px}
.moat-kpi .v{font-size:20px; font-weight:700; font-family:"DejaVu Sans Mono",monospace}
.moat-kpi .v.pos{color:var(--ok)} .moat-kpi .v.neg{color:var(--risk)}
.moat-kpi .v.mid{color:var(--mid)}

/* ---------- 归纳卡 ---------- */
.insights{display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.insight{
  border:1px solid var(--line); border-radius:6px; padding:13px 15px; background:#fcfbfa;
  border-top:3px solid var(--accent);
}
.insight.warn{border-top-color:var(--mid)}
.insight.bad{border-top-color:var(--risk)}
.insight.ok{border-top-color:var(--ok)}
.i-head{
  font-family:"Noto Sans CJK SC",sans-serif; font-weight:700; font-size:14px;
  margin-bottom:7px; color:#2b3140;
}
.i-tag{
  font-size:11.5px; color:#fff; background:var(--accent); padding:2px 8px;
  border-radius:3px; margin-right:7px; vertical-align:1px;
}
.insight.warn .i-tag{background:var(--mid)}
.insight.bad .i-tag{background:var(--risk)}
.insight.ok .i-tag{background:var(--ok)}
ul.i-list{padding-left:19px; margin:0; font-size:13.5px; line-height:1.75}
ul.i-list li{margin-bottom:6px}
ul.i-list li:last-child{margin-bottom:0}

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
  .tbl-scroll{overflow:visible}
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


# ---------------------------------------------------------------- 图表


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
    parts.append(
        f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="4" '
        f'fill="#fff" stroke="#8b1a1a" stroke-width="2.2"/>'
    )
    parts.append(
        f'<text x="{x(len(vals) - 1):.1f}" y="{y(vals[-1]) - 11:.1f}" text-anchor="end" '
        f'font-size="12.5" font-weight="700" fill="#8b1a1a">{vals[-1]:.2f}{unit}</text>'
    )
    step = max(1, len(labels) // 9)
    for i, lb in enumerate(labels):
        if i % step == 0 or i == len(labels) - 1:
            parts.append(
                f'<text x="{x(i):.1f}" y="{h - pad_b + 17}" text-anchor="middle" '
                f'font-size="11" fill="#8b93a1">{html.escape(lb)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


PALETTE = ["#8b1a1a", "#2a6099", "#1e8449", "#c77f08", "#6b4c9a", "#0f7d82"]


def svg_multi(labels: list, series: list, unit_l: str = "", unit_r: str = "",
              height: int = 300) -> str:
    """多序列组合图：柱（左轴）+ 折线（可走右轴）。

    series 每项：{name, type:'bar'|'line', values[], axis:'l'|'r', color?}
    """
    if not labels or not series:
        return ""
    clean = []
    for s in series:
        vals = [float(v) if isinstance(v, (int, float)) else None for v in s.get("values") or []]
        if any(v is not None for v in vals):
            clean.append({**s, "_v": vals})
    if not clean:
        return ""

    n = len(labels)
    w = 980
    pad_l, pad_r, pad_t, pad_b = 60, 60, 26, 34
    legend_h = 24
    plot_h = height - pad_t - pad_b - legend_h

    def collect(axis: str) -> list[float]:
        out = []
        for s in clean:
            if (s.get("axis") or "l") == axis:
                out += [v for v in s["_v"] if v is not None]
        return out

    def rng(vs: list[float]) -> tuple[float, float]:
        if not vs:
            return 0.0, 1.0
        lo, hi = min(vs), max(vs)
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        if lo > 0 and lo / abs(hi) < 0.5:
            lo = 0.0
        span = (hi - lo) or 1.0
        return lo - span * 0.12, hi + span * 0.15

    lo_l, hi_l = rng(collect("l"))
    lo_r, hi_r = rng(collect("r"))
    has_r = any((s.get("axis") or "l") == "r" for s in clean)

    slot = (w - pad_l - pad_r) / n

    def xc(i: int) -> float:
        return pad_l + slot * (i + 0.5)

    def yy(v: float, axis: str) -> float:
        lo, hi = (lo_r, hi_r) if axis == "r" else (lo_l, hi_l)
        return pad_t + plot_h * (hi - v) / (hi - lo)

    def fmt(v: float) -> str:
        a = abs(v)
        if a >= 1000:
            return f"{v:,.0f}"
        if a >= 100:
            return f"{v:.0f}"
        return f"{v:.1f}"

    parts = [f'<svg viewBox="0 0 {w} {height}" role="img" aria-label="趋势图">']
    # 横向网格 + 左右轴刻度
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + plot_h * frac
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e6e3dd" stroke-width="1"/>'
        )
        vl = hi_l - (hi_l - lo_l) * frac
        parts.append(
            f'<text x="{pad_l - 7}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="10.5" fill="#8b93a1">{fmt(vl)}</text>'
        )
        if has_r:
            vr = hi_r - (hi_r - lo_r) * frac
            parts.append(
                f'<text x="{w - pad_r + 7}" y="{gy + 4:.1f}" text-anchor="start" '
                f'font-size="10.5" fill="#8b93a1">{fmt(vr)}</text>'
            )
    # 零轴
    if lo_l < 0 < hi_l:
        zy = yy(0, "l")
        parts.append(
            f'<line x1="{pad_l}" y1="{zy:.1f}" x2="{w - pad_r}" y2="{zy:.1f}" '
            f'stroke="#b9b3aa" stroke-width="1.2" stroke-dasharray="4 3"/>'
        )

    bars = [s for s in clean if (s.get("type") or "line") == "bar"]
    lines = [s for s in clean if (s.get("type") or "line") == "line"]
    nb = len(bars)
    bw = (slot * 0.62) / max(nb, 1)

    for bi, s in enumerate(bars):
        color = s.get("color") or PALETTE[bi % len(PALETTE)]
        off = -slot * 0.31 + bw * bi + (slot * 0.62 - bw * nb) / 2
        for i, v in enumerate(s["_v"]):
            if v is None:
                continue
            top = yy(v, s.get("axis") or "l")
            base = yy(0 if lo_l < 0 else lo_l, "l")
            parts.append(
                f'<rect x="{xc(i) + off:.1f}" y="{min(top, base):.1f}" '
                f'width="{bw:.1f}" height="{abs(base - top):.1f}" rx="2" '
                f'fill="{color}" opacity=".82"/>'
            )

    for li, s in enumerate(lines):
        color = s.get("color") or PALETTE[(li + 2) % len(PALETTE)]
        axis = s.get("axis") or "l"
        pts = [(xc(i), yy(v, axis)) for i, v in enumerate(s["_v"]) if v is not None]
        idx = [i for i, v in enumerate(s["_v"]) if v is not None]
        dash = ' stroke-dasharray="6 3"' if s.get("dashed") else ""
        parts.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            + f'" fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linejoin="round"{dash}/>'
        )
        for i, (px, py) in zip(idx, pts):
            parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.4" fill="#fff" '
                f'stroke="{color}" stroke-width="2"/>'
            )
        # 末值标注
        if pts:
            px, py = pts[-1]
            parts.append(
                f'<text x="{px:.1f}" y="{py - 9:.1f}" text-anchor="middle" '
                f'font-size="11" font-weight="700" fill="{color}">'
                f'{fmt(s["_v"][idx[-1]])}</text>'
            )

    # 横轴标签
    step = max(1, n // 11)
    for i, lb in enumerate(labels):
        if i % step == 0 or i == n - 1:
            parts.append(
                f'<text x="{xc(i):.1f}" y="{pad_t + plot_h + 17}" text-anchor="middle" '
                f'font-size="10.5" fill="#8b93a1">{html.escape(str(lb))}</text>'
            )

    # 图例
    total_w = sum(58 + len(str(s.get("name", ""))) * 13 for s in clean)
    lx = (w - total_w) / 2
    ly = height - 8
    for si, s in enumerate(clean):
        color = s.get("color") or PALETTE[si % len(PALETTE)]
        name = str(s.get("name", ""))
        if (s.get("type") or "line") == "bar":
            parts.append(f'<rect x="{lx:.1f}" y="{ly - 8:.1f}" width="11" height="11" rx="2" fill="{color}"/>')
        else:
            parts.append(
                f'<line x1="{lx:.1f}" y1="{ly - 3:.1f}" x2="{lx + 11:.1f}" y2="{ly - 3:.1f}" '
                f'stroke="{color}" stroke-width="2.6"/>'
            )
        parts.append(
            f'<text x="{lx + 16:.1f}" y="{ly + 2:.1f}" font-size="11.5" '
            f'fill="#5b6472">{html.escape(name)}</text>'
        )
        lx += 58 + len(name) * 13

    # 轴单位
    if unit_l:
        parts.append(
            f'<text x="{pad_l - 7}" y="{pad_t - 12:.1f}" text-anchor="end" '
            f'font-size="10" fill="#a6adba">{html.escape(unit_l)}</text>'
        )
    if unit_r and has_r:
        parts.append(
            f'<text x="{w - pad_r + 7}" y="{pad_t - 12:.1f}" text-anchor="start" '
            f'font-size="10" fill="#a6adba">{html.escape(unit_r)}</text>'
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
        f'<span class="stance {cls}">{_rich(v.get("stance", "待判断"))}</span>',
        f'<span class="muted">{esc(v.get("headline"))}</span>',
        "</div>",
        f"<p>{esc(v.get('summary'))}</p>",
    ]
    tags = v.get("tags") or []
    if tags:
        out.append('<div class="chips">')
        for t in tags:
            if isinstance(t, str):            # 允许直接写字符串标签
                kind, txt = "", t
            else:
                kind, txt = t.get("kind", ""), t.get("text")
            out.append(f'<span class="chip {kind}">{esc(txt)}</span>')
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
            "<div class='tbl-scroll'><table><thead><tr><th>周期</th><th>最高 / 最低</th>"
            "<th>说明</th></tr></thead><tbody>"
        )
        for r in rows:
            out.append(
                f"<tr><td>{esc(r.get('name'))}</td>"
                f"<td class='num'>{esc(r.get('range'))}</td>"
                f"<td>{esc(r.get('note'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
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


MOAT_STRENGTH = {"wide": ("宽", "lv-ok"), "narrow": ("窄", "lv-mid"),
                 "none": ("无", "lv-high")}
MOAT_SRC = {"strong": ("强", "lv-ok"), "mid": ("中", "lv-mid"),
            "weak": ("弱", "lv-na"), "none": ("无", "lv-na")}


def _rich(txt) -> str:
    """转义后用 **加粗** / `代码` 做轻量标记（护城河的长文本里到处是强调）。"""
    out = esc(txt)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def _moat_block(m) -> str:
    """三、生意本身 · 护城河：五指标长周期 → ROIC/WACC → 来源论证。

    m 为字符串时按旧版纯段落渲染（向后兼容）。
    """
    if not isinstance(m, dict):
        return f"<h3>护城河</h3><p>{esc(m)}</p>"

    out = ["<h3>护城河</h3>"]
    label, cls = MOAT_STRENGTH.get(str(m.get("strength", "")), ("", ""))
    if label:
        note = _rich(m.get("strength_note", ""))
        out.append(
            f"<p class='moat-head'><span class='lv {cls}'>护城河 {esc(m.get('strength_text') or label)}</span>"
            f"<span class='moat-sub'>{note}</span></p>"
        )
    if m.get("text"):
        out.append(f"<p>{_rich(m['text'])}</p>")

    # ① 五指标矩阵
    years = m.get("years") or []
    mt = m.get("metrics") or {}
    rows = mt.get("rows") or []
    if years and rows:
        out.append("<h4>① 五个财务体征，拉长看</h4>")
        out.append(_matrix_table(years, rows, first_col="指标", colorize=False))
        judge = mt.get("judge") or {}
        if judge:
            out.append("<ul class='watch moat-judge'>")
            for v in (judge.values() if isinstance(judge, dict) else judge):
                out.append(f"<li>{_rich(v)}</li>")
            out.append("</ul>")
    if mt.get("consistency"):
        out.append(f"<p class='chart-note'>{_rich(mt['consistency'])}</p>")

    # ② 趋势图
    charts = m.get("charts") or []
    for idx, ch in enumerate(charts):
        svg = svg_multi(ch.get("labels") or years, ch.get("series") or [],
                        ch.get("unit_l", ""), ch.get("unit_r", ""),
                        int(ch.get("height", 300)))
        if not svg:
            print(f"[warn] 护城河趋势图「{ch.get('title') or idx + 1}」没有可绘制数值，已跳过",
                  file=sys.stderr)
            continue
        out.append(f"<h4>{esc(ch.get('title') or f'趋势图 {idx + 1}')}</h4>")
        out.append(f"<div class='chart-box'>{svg}</div>")
        if ch.get("note"):
            out.append(f"<p class='chart-note'>{esc(ch['note'])}</p>")

    # ③ ROIC vs WACC
    r = m.get("roic") or {}
    if r:
        out.append("<h4>③ 进阶验证：ROIC 减 WACC</h4>")
        cards = []
        for key, name in (("value", "ROIC 投入资本回报率"), ("wacc", "WACC 资金成本")):
            v = r.get(key)
            if v is None:
                continue
            unit = "%" if key == "wacc" or r.get("unit", "%") == "%" else ""
            cards.append(f"<div class='box'><div class='k'>{name}</div>"
                         f"<div class='v'>{esc(v)}{unit}</div></div>")
        sp = r.get("spread")
        if sp is not None:
            try:
                positive = float(sp) > 0
            except (TypeError, ValueError):
                positive = None
            cls_v = "pos" if positive else ("neg" if positive is False else "")
            cards.append(f"<div class='box'><div class='k'>差值 ROIC − WACC</div>"
                         f"<div class='v {cls_v}'>{esc(sp)}pct</div></div>")
        if cards:
            out.append(f"<div class='moat-kpi'>{''.join(cards)}</div>")
        if r.get("note"):
            out.append(f"<p class='chart-note'>{_rich(r['note'])}</p>")

    # ④ 来源论证
    src = m.get("sources") or []
    if src:
        out.append("<h4>④ 护城河的来源（财务只是证据，这里才是答案）</h4>")
        out.append("<div class='tbl-scroll'><table><thead><tr><th>来源</th><th>强度</th>"
                   "<th>证据</th></tr></thead><tbody>")
        for it in src:
            label, cls = MOAT_SRC.get(str(it.get("strength", "")), ("", "lv-na"))
            out.append(
                f"<tr><td class='rowhead'>{esc(it.get('type'))}</td>"
                f"<td class='center'><span class='lv {cls}'>{esc(label)}</span></td>"
                f"<td>{_rich(it.get('evidence'))}</td></tr>"
            )
        out.append("</tbody></table></div>")

    if m.get("verdict"):
        out.append(f"<blockquote>{_rich(m['verdict'])}</blockquote>")
    return "".join(out)


def _stats(vals: list) -> dict:
    """给一组估值样本算分位/中位/区间（当前值单独传）。"""
    xs = sorted(v for v in vals if isinstance(v, (int, float)) and v > 0)
    if not xs:
        return {}
    n = len(xs)
    mid = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    return {"n": n, "min": xs[0], "max": xs[-1], "median": mid}


def _points(series: list) -> list:
    """兼容两种写法：[{d,v},…]（带日期，推荐）或 [v,…]（旧写法，横轴退化为序号）。"""
    pts = []
    for i, it in enumerate(series or []):
        if isinstance(it, dict):
            d, v = it.get("d"), it.get("v")
        else:
            d, v = str(i), it
        if isinstance(v, (int, float)) and v > 0:
            pts.append((str(d), float(v)))
    return pts


def svg_series(points: list, unit: str = "x", tone: str = "mid",
               median: float | None = None, height: int = 230) -> str:
    """横轴时间、纵轴估值：一条曲线 + 中位虚线 + 当前值标在曲线末端。"""
    if len(points) < 5:
        return ""
    vals = [v for _, v in points]
    lo, hi = min(vals), max(vals)
    if median is not None:
        lo, hi = min(lo, median), max(hi, median)
    span = hi - lo or 1
    lo, hi = lo - span * 0.10, hi + span * 0.16
    w, pad_l, pad_r, pad_t, pad_b = 980, 46, 40, 26, 34
    plot_h = height - pad_t - pad_b
    n = len(points)
    color = {"ok": "#14663a", "high": "#c0392b", "mid": "#b7791f", "na": "#6b7280"}.get(tone, "#b7791f")

    def xx(i: int) -> float:
        return pad_l + (w - pad_l - pad_r) * (i / (n - 1))

    def yy(v: float) -> float:
        return pad_t + plot_h * (hi - v) / (hi - lo)

    def lab(v: float) -> str:
        return f"{v:.1f}" if abs(v) < 100 else f"{v:.0f}"

    parts = [f'<svg viewBox="0 0 {w} {height}" role="img" aria-label="估值时间序列">']
    for frac in (0, .25, .5, .75, 1):
        gy = pad_t + plot_h * frac
        gv = hi - (hi - lo) * frac
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" '
                     f'stroke="#e6e3dd" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'font-size="10.5" fill="#8b93a1">{lab(gv)}</text>')
    # 面积 + 曲线
    pts = [(xx(i), yy(v)) for i, (_, v) in enumerate(points)]
    base = pad_t + plot_h
    parts.append('<polygon points="' + " ".join(f"{p:.1f},{q:.1f}" for p, q in pts)
                 + f' {pts[-1][0]:.1f},{base:.1f} {pts[0][0]:.1f},{base:.1f}" '
                 f'fill="{color}" opacity=".07"/>')
    parts.append('<polyline points="' + " ".join(f"{p:.1f},{q:.1f}" for p, q in pts)
                 + '" fill="none" stroke="#6b7280" stroke-width="1.8" stroke-linejoin="round"/>')
    # 中位
    if median is not None:
        my = yy(median)
        parts.append(f'<line x1="{pad_l}" y1="{my:.1f}" x2="{w - pad_r}" y2="{my:.1f}" '
                     f'stroke="#8b93a1" stroke-width="1.2" stroke-dasharray="5 4"/>')
        parts.append(f'<text x="{w - pad_r - 4}" y="{my - 6:.1f}" text-anchor="end" '
                     f'font-size="10.5" fill="#8b93a1">中位 {median:.1f}{esc(unit)}</text>')
    # 当前值：竖线 + 圆点 + 标签
    cx, cy = pts[-1]
    parts.append(f'<line x1="{cx:.1f}" y1="{pad_t}" x2="{cx:.1f}" y2="{base:.1f}" '
                 f'stroke="{color}" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>')
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#fff" stroke="{color}" stroke-width="2.6"/>')
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.2" fill="{color}"/>')
    label = f"当前 {points[-1][1]:g}{unit}"
    lx = min(cx, w - pad_r - 52)
    ly = cy - 14 if cy - 14 > pad_t + 8 else cy + 22
    parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="end" font-size="12" '
                 f'font-weight="700" fill="{color}">{esc(label)}</text>')
    # 横轴：每年取一个刻度（年份），末端补当前日期；挤在一起的就丢掉
    ticks, kind, seen = [], {}, set()
    for i, (d, _) in enumerate(points):
        y = d[:4]
        if y not in seen:
            seen.add(y)
            ticks.append(i)
            kind[i] = "year"
    if n - 1 not in kind:
        ticks.append(n - 1)
        kind[n - 1] = "last"
    spaced = []
    for i in ticks:
        if spaced and xx(i) - xx(spaced[-1]) < 48:
            if kind.get(i) == "last":
                spaced[-1] = i
                kind[i] = "last"
            continue
        spaced.append(i)
    for i in spaced:
        d = points[i][0]
        tick = d[:4] if kind.get(i) == "year" else d[2:7].replace("-", "/")
        parts.append(f'<text x="{xx(i):.1f}" y="{base + 20:.1f}" text-anchor="middle" '
                     f'font-size="10.5" fill="#8b93a1">{esc(tick)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def sec_valuation(v: dict) -> str:
    """七、企业估值：当前 PE/PB/PS 的历史走势与分位。"""
    if not v or not (v.get("metrics") or []):
        return ""
    title = v.get("title") or "七、企业估值"
    out = [f"<section><h2>{esc(title)}</h2>"]
    if v.get("lead"):
        out.append(f"<p class='lead'>{_rich(v['lead'])}</p>")

    for m in v.get("metrics") or []:
        unit = m.get("unit") or "x"
        pts = _points(m.get("series") or [])
        cur = m.get("current")
        vals = [x for _, x in pts]
        if len(vals) < 5 or not isinstance(cur, (int, float)):
            continue
        stat = _stats(vals)
        pct = 100 * sum(1 for x in vals if x < cur) / len(vals)
        tone = m.get("tone") or ("ok" if pct <= 20 else ("high" if pct >= 80 else "mid"))
        cls = {"ok": "lv-ok", "high": "lv-high", "mid": "lv-mid", "na": "lv-na"}.get(tone, "lv-mid")
        badge = m.get("badge") or (
            f"历史 {pct:.0f}% 分位"
            + ("（历史低位）" if pct <= 20 else ("（历史高位）" if pct >= 80 else ""))
        )
        out.append("<div class='val-item'>")
        out.append(
            f"<div class='val-head'><span class='val-name'>{esc(m.get('name'))}</span>"
            f"<span class='val-cur'>{cur:g}{esc(unit)}</span>"
            f"<span class='lv {cls}'>{esc(badge)}</span>"
            f"<span class='val-sub'>中位 {stat['median']:.1f}{esc(unit)}　·　"
            f"区间 {stat['min']:.1f}–{stat['max']:.1f}{esc(unit)}　·　样本 {stat['n']} 个　·　"
            f"{esc(pts[0][0][:7])} 起</span></div>"
        )
        svg = svg_series(pts, unit, tone=tone, median=stat["median"])
        if svg:
            out.append(f'<div class="chart-box" style="border:none;background:none;padding:0">{svg}</div>')
        if m.get("note"):
            out.append(f"<p class='val-note'>{_rich(m['note'])}</p>")
        out.append("</div>")

    if v.get("comment"):
        out.append(f"<blockquote>{_rich(v['comment'])}</blockquote>")
    if v.get("note"):
        out.append(f"<p class='chart-note'>{_rich(v['note'])}</p>")
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
            "<div class='tbl-scroll'><table><thead><tr><th>业务板块</th><th>营收占比</th>"
            "<th>毛利率</th><th>点评</th></tr></thead><tbody>"
        )
        for s in segs:
            out.append(
                f"<tr><td>{esc(s.get('name'))}</td>"
                f"<td class='num'>{esc(s.get('rev_pct'))}</td>"
                f"<td class='num'>{esc(s.get('margin'))}</td>"
                f"<td>{esc(s.get('comment'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
    if b.get("moat"):
        out.append(_moat_block(b["moat"]))
    for key, title in (("policy", "行业与政策"),
                       ("upstream", "上游"), ("downstream", "下游")):
        if b.get(key):
            out.append(f"<h3>{title}</h3><p>{esc(b[key])}</p>")
    if b.get("comment"):
        out.append(f"<blockquote>{esc(b['comment'])}</blockquote>")
    out.append("</section>")
    return "".join(out)


def _matrix_table(headers: list, series: list, first_col: str = "指标",
                  colorize: bool = True) -> str:
    """通用「首列 + 若干期」矩阵表。series 每项 {name, values[], note?}。"""
    if not headers or not series:
        return ""
    out = [
        "<div class='tbl-scroll'><table><thead><tr>"
        f"<th>{esc(first_col)}</th>"
    ]
    out += [f"<th class='center'>{esc(h)}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for s in series:
        out.append(f"<tr><td class='rowhead'>{esc(s.get('name'))}</td>")
        for v in s.get("values") or []:
            cls = cls_num(v) if colorize else ""
            out.append(f"<td class='num center {cls}'>{esc(v)}</td>")
        # 补齐列数，避免表格错位
        missing = len(headers) - len(s.get("values") or [])
        out += ["<td class='num center'>—</td>"] * max(missing, 0)
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def sec_financials(f: dict) -> str:
    """财务全景与跨年趋势研判（合并原「多年趋势 + 最新财报 + 资产负债」三块）。"""
    if not f:
        return ""
    out = [f"<section><h2>{esc(f.get('title') or '财务全景与跨年趋势研判')}</h2>"]
    if f.get("lead"):
        out.append(f"<p class='lead'>{esc(f['lead'])}</p>")

    # --- 1. 季度主表 ---
    periods = f.get("periods") or []
    qt = f.get("quarterly") or []
    if periods and qt:
        out.append(f"<h3>{esc(f.get('quarterly_title') or '① 季度主表（单季口径）')}</h3>")
        out.append(_matrix_table(periods, qt))
        if f.get("quarterly_note"):
            out.append(f"<p class='muted' style='margin-top:8px'>{esc(f['quarterly_note'])}</p>")

    # --- 2. 趋势图 ---
    charts = f.get("charts") or []
    for idx, ch in enumerate(charts):
        labels = ch.get("labels") or periods
        svg = svg_multi(labels, ch.get("series") or [],
                        ch.get("unit_l", ""), ch.get("unit_r", ""),
                        int(ch.get("height", 300)))
        if not svg:
            print(f"[warn] 趋势图「{ch.get('title') or f'趋势图 {idx + 1}'}」没有可绘制的数值，"
                  f"已跳过；检查 series[].values 是否全为数字（带 % 或 亿 的字符串画不出来）。",
                  file=sys.stderr)
            continue
        out.append(f"<h3>{esc(ch.get('title') or f'趋势图 {idx + 1}')}</h3>")
        out.append(f'<div class="chart-box">{svg}</div>')
        if ch.get("note"):
            out.append(f"<p class='chart-note'>{esc(ch['note'])}</p>")

    # --- 3. 同季同比 ---
    yoy = f.get("yoy") or {}
    if yoy.get("headers"):
        out.append(f"<h3>{esc(yoy.get('title') or '② 同季同比对照')}</h3>")
        out.append(_matrix_table(yoy["headers"], yoy.get("series") or [],
                                 yoy.get("first_col", "对照项")))
        if yoy.get("note"):
            out.append(f"<p class='muted' style='margin-top:8px'>{esc(yoy['note'])}</p>")

    # --- 4. 累计口径（年报/中报） ---
    cum = f.get("cumulative") or {}
    if cum.get("headers") and cum.get("series"):
        out.append(f"<h3>{esc(cum.get('title') or '③ 累计口径（年报 / 中报）')}</h3>")
        out.append(_matrix_table(cum["headers"], cum["series"], cum.get("first_col", "指标")))
        if cum.get("note"):
            out.append(f"<p class='muted' style='margin-top:8px'>{esc(cum['note'])}</p>")

    # --- 5. 最新一期财报 ---
    lat = f.get("latest") or {}
    if lat:
        out.append(
            f"<h3>{esc(lat.get('title') or '④ 最新一期财报')}"
            f"（{esc(lat.get('period'))}）</h3>"
            if lat.get("period") else
            f"<h3>{esc(lat.get('title') or '④ 最新一期财报')}</h3>"
        )
        if lat.get("comment"):
            out.append(f"<p>{esc(lat['comment'])}</p>")
        items = lat.get("items") or []
        if items:
            out.append(
                "<div class='tbl-scroll'><table><thead><tr><th>项目</th>"
                "<th class='center'>数值</th><th class='center'>同比</th>"
                "<th>说明</th></tr></thead><tbody>"
            )
            for it in items:
                out.append(
                    f"<tr><td>{esc(it.get('label'))}</td>"
                    f"<td class='num center'>{esc(it.get('value'))}</td>"
                    f"<td class='num center {cls_num(it.get('yoy'))}'>{esc(it.get('yoy'))}</td>"
                    f"<td>{esc(it.get('note'))}</td></tr>"
                )
            out.append("</tbody></table></div>")
        sigs = lat.get("signals") or []
        if sigs:
            out.append("<h4>三项改善信号判定</h4>")
            for s in sigs:
                st = str(s.get("state", "na")).lower()
                out.append(
                    f'<div class="signal {st}">'
                    f'<div class="s-name">{esc(s.get("name"))}</div>'
                    f'<div class="s-body">{esc(s.get("result"))}'
                    f'<div class="s-reason">{esc(s.get("reason"))}</div></div>'
                    "</div>"
                )

    # --- 6. 资产负债表 + 安全指标 ---
    bs = f.get("balance") or {}
    if bs:
        out.append(f"<h3>{esc(bs.get('title') or '⑤ 资产负债与安全边际')}</h3>")
        if bs.get("comment"):
            out.append(f"<p>{esc(bs['comment'])}</p>")
        items = bs.get("items") or []
        if items:
            out.append(
                "<div class='tbl-scroll'><table><thead><tr><th>科目</th>"
                "<th class='center'>金额</th><th>说明</th></tr></thead><tbody>"
            )
            for it in items:
                out.append(
                    f"<tr><td>{esc(it.get('label'))}</td>"
                    f"<td class='num center'>{esc(it.get('value'))}</td>"
                    f"<td>{esc(it.get('note'))}</td></tr>"
                )
            out.append("</tbody></table></div>")
        risks = bs.get("risks") or []
        if risks:
            out.append("<h4>四项安全判定</h4>")
            out.append(
                "<div class='tbl-scroll'><table><thead><tr><th>指标</th>"
                "<th class='center'>数值</th><th class='center'>判定</th>"
                "<th>阈值与说明</th></tr></thead><tbody>"
            )
            lv_map = {"高危": "lv-high", "危险": "lv-high", "关注": "lv-mid",
                      "紧张": "lv-mid", "正常": "lv-ok", "健康": "lv-ok",
                      "优秀": "lv-ok", "良好": "lv-ok", "无数据": "lv-na"}
            for r in risks:
                lv = str(r.get("level", "无数据"))
                cls = next((v for k, v in lv_map.items() if lv.startswith(k)), "lv-na")
                out.append(
                    f"<tr><td>{esc(r.get('name'))}</td>"
                    f"<td class='num center'>{esc(r.get('value'))}</td>"
                    f"<td class='center'><span class='lv {cls}'>{esc(lv)}</span></td>"
                    f"<td>{esc(r.get('threshold'))}</td></tr>"
                )
            out.append("</tbody></table></div>")

    # --- 7. 趋势归纳 ---
    ins = f.get("insights") or []
    if ins:
        out.append(f"<h3>{esc(f.get('insights_title') or '⑥ 跨年趋势归纳')}</h3>")
        out.append('<div class="insights">')
        for it in ins:
            kind = it.get("kind", "")
            tag = it.get("tag") or it.get("dim") or ""
            out.append(
                f'<div class="insight {kind}">'
                f'<div class="i-head"><span class="i-tag">{esc(tag)}</span>'
                f'{esc(it.get("title"))}</div><ul class="i-list">'
            )
            for p in it.get("points") or []:
                out.append(f"<li>{esc(p)}</li>")
            out.append("</ul></div>")
        out.append("</div>")

    out.append("</section>")
    return "".join(out)


def sec_trends(t: dict) -> str:
    """多年财务趋势表（旧版独立区块，保留兼容）。"""
    if not t or not (t.get("series") and t.get("years")):
        return ""
    years = t["years"]
    out = [
        f"<section><h2>{esc(t.get('title', '多年财务趋势'))}</h2>",
        "<div class='tbl-scroll'><table><thead><tr><th>指标</th>",
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
    out.append("</tbody></table></div>")
    if t.get("comment"):
        out.append(f"<p style='margin-top:12px'>{esc(t['comment'])}</p>")
    out.append("</section>")
    return "".join(out)


def sec_latest(l: dict) -> str:
    """最新一期财报解读（旧版独立区块，保留兼容）。"""
    if not l:
        return ""
    out = [f"<section><h2>四、最新财报解读（{esc(l.get('period'))}）</h2>"]
    if l.get("comment"):
        out.append(f"<p>{esc(l['comment'])}</p>")
    items = l.get("items") or []
    if items:
        out.append(
            "<div class='tbl-scroll'><table><thead><tr><th>项目</th>"
            "<th class='center'>数值</th><th class='center'>同比</th>"
            "<th>说明</th></tr></thead><tbody>"
        )
        for it in items:
            out.append(
                f"<tr><td>{esc(it.get('label'))}</td>"
                f"<td class='num center'>{esc(it.get('value'))}</td>"
                f"<td class='num center {cls_num(it.get('yoy'))}'>{esc(it.get('yoy'))}</td>"
                f"<td>{esc(it.get('note'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
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
    """资产负债表明细 + 安全指标（旧版独立区块，保留兼容）。"""
    if not bs:
        return ""
    out = ["<section><h2>五、资产负债与安全边际</h2>"]
    if bs.get("comment"):
        out.append(f"<p>{esc(bs['comment'])}</p>")
    items = bs.get("items") or []
    if items:
        out.append(
            "<div class='tbl-scroll'><table><thead><tr><th>科目</th>"
            "<th class='center'>金额</th><th>说明</th></tr></thead><tbody>"
        )
        for it in items:
            out.append(
                f"<tr><td>{esc(it.get('label'))}</td>"
                f"<td class='num center'>{esc(it.get('value'))}</td>"
                f"<td>{esc(it.get('note'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
    risks = bs.get("risks") or []
    if risks:
        out.append("<h3>四项安全指标</h3>")
        out.append(
            "<div class='tbl-scroll'><table><thead><tr><th>指标</th>"
            "<th class='center'>数值</th><th class='center'>判定</th>"
            "<th>阈值与说明</th></tr></thead><tbody>"
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
        out.append("</tbody></table></div>")
    out.append("</section>")
    return "".join(out)


REDFLAG_TOTAL = 25


def redflag_head(title: str, items: list[dict]) -> str:
    """排雷区块标题。

    分母固定为清单条数（25），不再拿「传进来的条数」当分母——
    否则只列命中项时会显示成「命中 4 / 4 项」，看着像全中。
    """
    hits = [r for r in items if r.get("hit")]
    ids = [str(r.get("id")) for r in hits if r.get("id") is not None]
    if ids:
        tail = "、".join("#" + i for i in ids)
        return f"{title}（命中 {len(hits)} / {REDFLAG_TOTAL} 条：{tail}）"
    if len(items) > len(hits):
        return f"{title}（命中 {len(hits)} / {len(items)} 条）"
    return f"{title}（命中 {len(hits)} 条）"


def sec_redflags(items: list[dict], title: str = "排雷扫描") -> str:
    if not items:
        return ""
    hits = [r for r in items if r.get("hit")]
    out = [
        f"<section><h2>{esc(redflag_head(title, items))}</h2>",
    ]
    if not hits:
        out.append("<p>暂未命中已知的高危组合信号。</p>")
    else:
        out.append(
            "<div class='tbl-scroll'><table><thead><tr><th class='center'>等级</th>"
            "<th>信号</th><th>依据</th></tr></thead><tbody>"
        )
        lv_map = {"高危": "lv-high", "危险": "lv-high", "关注": "lv-mid",
                  "警告": "lv-mid", "留意": "lv-mid"}
        for r in hits:
            lv = str(r.get("level", "关注"))
            cls = next((v for k, v in lv_map.items() if lv.startswith(k)), "lv-mid")
            out.append(
                f"<tr><td class='center'><span class='lv {cls}'>{esc(lv)}</span></td>"
                f"<td>{('<span class=\'muted\'>#' + esc(r['id']) + '</span> ') if r.get('id') is not None else ''}{esc(r.get('text'))}</td>"
                f"<td class='muted'>{esc(r.get('evidence'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
    out.append("</section>")
    return "".join(out)


def sec_scorecard(sc: dict, title: str = "七步研判") -> str:
    """七步研判结论 + 加权评分条。"""
    if not sc:
        return ""
    out = [f"<section><h2>{esc(title)}</h2>"]
    steps = sc.get("steps") or []
    if steps:
        out.append(
            "<div class='tbl-scroll'><table><thead><tr><th class='center'>步</th>"
            "<th>维度</th><th class='center'>结论</th><th>要点</th></tr></thead><tbody>"
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
        out.append("</tbody></table></div>")
    items = sc.get("items") or []
    if items:
        out.append("<h3>加权评分</h3>")
        # value=None 表示该项不可评（数据缺口）：不计分、不进分母，条子画成灰底
        scored = [i for i in items if i.get("value") is not None]
        max_abs = max((abs(float(i["value"])) for i in scored), default=1) or 1
        for i in items:
            if i.get("value") is None:
                out.append(
                    f'<div class="bar-row na"><div class="bar-name">{esc(i.get("dim"))}</div>'
                    f'<div class="bar-track"><div class="bar-fill na" style="width:100%"></div></div>'
                    f'<div class="bar-val muted">不可评 ×{esc(i.get("weight"))}</div></div>'
                )
                continue
            val = float(i["value"])
            w = int(100 * abs(val) / max_abs)
            neg = "neg" if val < 0 else ""
            out.append(
                f'<div class="bar-row"><div class="bar-name">{esc(i.get("dim"))}</div>'
                f'<div class="bar-track"><div class="bar-fill {neg}" style="width:{w}%">'
                f"</div></div>"
                f'<div class="bar-val">{val:+.0f} ×{esc(i.get("weight"))}</div></div>'
            )
        if len(scored) < len(items):
            w_all = sum(float(i.get("weight") or 0) for i in items)
            w_ok = sum(float(i.get("weight") or 0) for i in scored)
            pts = sum(float(i["value"]) * float(i.get("weight") or 0) for i in scored)
            full = 2 * w_ok
            rate = (pts / full * 100) if full else 0
            out.append(
                f'<p class="muted" style="margin-top:10px">可评 {len(scored)} / {len(items)} 项'
                f'（权重 {w_ok:g} / {w_all:g}）；按可评项归一化：'
                f'{pts:+.0f} / {full:g} = {rate:.1f}%</p>'
            )
        if sc.get("total") is not None:
            out.append(
                f'<p style="margin-top:12px"><strong>加权总分：{esc(sc["total"])}</strong>'
                f'<span class="muted">　{esc(sc.get("total_note"))}</span></p>'
            )
    out.append("</section>")
    return "".join(out)


def sec_conclusion(c: dict, title: str = "综合研判") -> str:
    if not c:
        return ""
    out = [f"<section class='concl'><h2>{esc(title)}</h2>"]
    for p in c.get("paragraphs") or []:
        out.append(f"<p>{_rich(p)}</p>")
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


def sec_gaps(items: list, title: str = "数据缺口与口径风险") -> str:
    """把拿不到的指标显式列出来，而不是让整个区块悄悄消失。"""
    if not items:
        return ""
    out = [f"<section><h2>{esc(title)}</h2><ul class='watch'>"]
    for g in items:
        out.append(f"<li>{esc(g)}</li>")
    out.append("</ul></section>")
    return "".join(out)


def sec_sources(items: list, title: str = "数据来源与口径") -> str:
    if not items:
        return ""
    out = [f"<section><h2>{esc(title)}</h2><div class='src'>"]
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
    has_new = bool(data.get("financials"))
    has_val = bool((data.get("valuation") or {}).get("metrics"))
    sv = data.get("schema_version", m.get("schema_version"))
    if str(sv) != "2":
        print(f"[warn] schema_version={sv!r}，脚本按 v2 结构渲染；"
              f"v1 旧样例会整块丢掉「财务全景」章节，请对照 scripts/sample.json。",
              file=sys.stderr)
    body = "".join([
        build_hero(m),
        sec_verdict(data.get("verdict") or {}),
        # 顺序与编号、与笔记范式一致：先看股价位置，再看估值，再看生意，最后看财务
        sec_price(data.get("price") or {}),
        sec_metrics("二、主要指标初步研判", data.get("core_metrics") or []),
        sec_business(data.get("business") or {}),
        # 新版：财务全景（合并多年趋势 / 最新财报 / 资产负债）
        sec_financials(data.get("financials") or {}),
        # 旧版三块：仅在未提供 financials 时输出
        *(([] if has_new else [
            sec_trends(data.get("trends") or {}),
            sec_latest(data.get("latest") or {}),
            sec_balance(data.get("balance") or {}),
        ])),
        # v1 结构多出「趋势 / 最新 / 资产负债」三块，后续编号整体后移一位
        sec_redflags(data.get("redflags") or [],
                     data.get("redflags_title") or ("五、排雷扫描" if has_new else "六、排雷扫描")),
        sec_scorecard(data.get("scorecard") or {},
                      data.get("scorecard_title") or ("六、七步研判" if has_new else "七、七步研判")),
        sec_valuation(data.get("valuation") or {}),
        sec_conclusion(data.get("conclusion") or {},
                       data.get("conclusion_title")
                       or (("八" if has_val else "七") + "、综合研判"
                           if has_new else "九、综合研判")),
        sec_gaps(data.get("data_gaps") or []),
        sec_sources(data.get("sources") or []),
    ])
    date_line = ""
    if m.get("report_date"):
        date_line = f'<footer>{esc(m["report_date"])} 生成　·　' \
                    f'本 报 告 基于公开数据整理，仅供参考，不构成投资建议</footer>'
    if m.get("price_at") and date_line:
        date_line = date_line.replace("生成　·　",
                                      f"生成　·　行情时点 {esc(m['price_at'])}　·　", 1)
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
