#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate.py —— 报告数据 JSON 的交付前自检（v2 schema）。

用法:
    python3 validate.py data.json            # 有问题时非零退出
    python3 validate.py data.json --strict   # 警告也算失败

设计原则：**只检查能机器判定的东西**（算得对的算术、对得上的长度、合法的枚举），
文风、逻辑、结论是否成立不归它管。渲染器的静默降级（图表整块消失、七步表整列空白）
都靠这里兜住。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_stats as rs  # noqa: E402

LEVELS = {"正常", "健康", "偏弱", "关注", "留意", "警告", "较差", "高危", "危险", "无数据"}
STATES = {"pass", "fail", "warn", "na"}
REDFLAG_TOTAL = 25
WEIGHT_SUM = 33          # 16 项打分卡权重合计（每项满分 +2 → 满分 66）
EXPECTED_STEPS = 7
EXPECTED_ITEMS = 16
MIN_PERIODS = 10
MIN_CORE_METRICS = 10

# v2 八节骨架：缺任何一节都不允许静默出报告。
REQUIRED_V2 = {
    "price": "一、股价位置",
    "core_metrics": "二、主要指标初步研判",
    "business": "三、生意本身",
    "financials": "四、财务全景与跨年趋势研判",
    "redflags_checked": "五、排雷扫描（零命中也要有 25 条已过标记）",
    "scorecard": "六、七步研判与打分卡",
    "valuation": "七、企业估值",
    "conclusion": "八、综合研判与跟踪清单",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _report_date(data: dict) -> str:
    """报告日（YYYY-MM-DD）：优先 meta.price_at（带时分的行情时点），其次 meta.report_date。"""
    meta = data.get("meta") or {}
    for key in ("price_at", "report_date"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(meta.get(key) or "").strip())
        if m:
            return m.group(1)
    return ""


def _day_gap(earlier: str, later: str) -> int | None:
    """`later - earlier` 的天数；任一侧不是 YYYY-MM-DD 就返回 None（不猜）。"""
    try:
        a = [int(x) for x in earlier.split("-")[:3]]
        b = [int(x) for x in later.split("-")[:3]]
        return (date(*b) - date(*a)).days
    except (ValueError, TypeError):
        return None


VAL_KEYS = {"pe", "pb", "ps"}


def _check_valuation(data: dict, rep: Report) -> None:
    """企业估值块：当前值在历史分布里的分位。"""
    v = data.get("valuation")
    if not v:
        rep.warn("valuation 缺失：七、企业估值 一节不会出现（PE/PB/PS 历史分位图）")
        return
    metrics = v.get("metrics") or []
    if not metrics:
        rep.err("valuation.metrics 为空")
        return
    keys = {str(m.get("key")) for m in metrics}
    lack = VAL_KEYS - keys
    if lack:
        rep.warn(f"valuation.metrics 缺 {sorted(lack)}：PE / PB / PS 三个都要给图")
    for m in metrics:
        name = m.get("name") or m.get("key")
        cur = m.get("current")
        series = m.get("series") or []
        if not _num(cur) or float(cur) <= 0:
            rep.err(f"估值指标「{name}」current={cur!r} 必须是正数")
            continue
        good = []          # 兼容 [{d,v}] 与 [v] 两种写法
        last = None
        last_date = ""
        for item in series:
            if isinstance(item, dict):
                val, d = item.get("v"), str(item.get("d") or "").strip()
            else:
                val, d = item, ""
            if _num(val) and float(val) > 0:
                good.append(float(val))
                last = float(val)
                if d:
                    last_date = d
        if len(good) < 20:
            rep.warn(f"估值指标「{name}」只有 {len(good)} 个历史样本（建议 ≥20，否则分位不可信）")
        if not good:
            continue
        # 末端点 vs current：同一时点两个数（日期 ≥ 报告日）必须一致；
        # 月末采样允许末端缺口，但那时只提醒，并把「note 要写清采样频率」一起抛出来。
        if last is not None:
            gap = abs(float(cur) - last) / last
            asof = _report_date(data)
            stale = _day_gap(last_date, asof) if (last_date and asof) else None
            if gap > 0.05:
                if stale is not None and stale > 0:
                    rep.warn(
                        f"估值指标「{name}」current={cur} 与 series 末点 {last:g}（{last_date}）"
                        f"相差 {gap * 100:.1f}%，末点比报告日 {asof} 早 {stale} 天——"
                        f"月末采样允许末端有缺口，但 valuation.note 要写清采样频率")
                else:
                    rep.err(f"估值指标「{name}」current={cur} 与 series 最后一点 {last:g} 相差 "
                            f"{gap * 100:.1f}%——同一时点不能两个数，当前值必须对齐曲线末端")
            elif stale is not None and stale > 45:
                rep.warn(f"估值指标「{name}」series 末点 {last_date} 比报告日 {asof} 早 "
                         f"{stale} 天：月末采样可以接受，但 valuation.note 要写明采样频率与样本区间")
        calc = rs.percentile(good, float(cur))
        declared = m.get("percentile")
        if declared is not None and _num(declared):
            if abs(float(declared) - calc) > 3:
                rep.err(f"估值指标「{name}」percentile={declared} 与按 series 重算的 "
                        f"{calc:.1f}% 相差超过 3pct——分位数字和图画的对不上")
        # 缩尾口径：样本被极端值（利润塌陷期的高 PE）压平时，必须同时给出缩尾后分位。
        tcalc = rs.trimmed_percentile(good, float(cur))
        tdeclared = m.get("percentile_trimmed")
        if tdeclared is not None and _num(tdeclared):
            if abs(float(tdeclared) - tcalc) > 3:
                rep.err(f"估值指标「{name}」percentile_trimmed={tdeclared} 与按 series 重算的 "
                        f"{tcalc:.1f}% 相差超过 3pct——缩尾分位和图上口径对不上")
        elif rs.is_outlier_sample(good):
            rep.warn(f"估值指标「{name}」的 series 含极端样本（最高 {max(good):.0f} 倍、"
                     f"中位 {rs.median(good):.1f} 倍）：请补 percentile_trimmed（缩尾后 {tcalc:.1f}%），"
                     f"否则分位会被压平、结论可能反向（见 §3.5）")
        elif abs(tcalc - calc) >= 10 and tdeclared is None:
            rep.warn(f"估值指标「{name}」全样本分位 {calc:.1f}% 与缩尾后 {tcalc:.1f}% 相差 "
                     f"{abs(tcalc - calc):.1f}pct——两个口径都要写进报告")
        if float(cur) > max(good) * 1.0001 or float(cur) < min(good) * 0.9999:
            rep.warn(f"估值指标「{name}」当前值 {cur} 落在历史区间 "
                     f"{min(good):.2f}~{max(good):.2f} 之外，确认是否口径不同")
    if not v.get("lead"):
        rep.warn("valuation.lead 为空：这一节要有一句话结论")
    if not v.get("note"):
        rep.warn("valuation.note 为空：样本区间与口径要写清楚")


MOAT_STRENGTHS = {"wide", "narrow", "none"}
MOAT_SRC_STRENGTHS = {"strong", "mid", "weak", "none"}
# 文档（SKILL.md 字段表 / 指标体系 §9.4）说「五个必须有」，代码就必须一律报错，
# 不能只对 fcf/net_margin/roe 报错、对 fcf_margin/roa 放水（2026-10-31 审核 N2）。
MOAT_ROWS = {"fcf", "fcf_margin", "net_margin", "roe", "roa"}


def _check_moat(data: dict, rep: Report) -> None:
    """护城河块：五指标矩阵 + 趋势图 + ROIC/WACC + 来源论证。"""
    b = data.get("business") or {}
    m = b.get("moat")
    if not m:
        rep.warn("business.moat 缺失：三、生意本身 会没有护城河一节")
        return
    if not isinstance(m, dict):
        rep.warn("business.moat 是纯字符串（旧格式）：缺五指标表、趋势图和 ROIC/WACC，"
                 "按新规范应改成对象")
        return

    if str(m.get("strength", "")) not in MOAT_STRENGTHS:
        rep.err(f"business.moat.strength={m.get('strength')!r}，只能是 wide / narrow / none")

    years = m.get("years") or []
    mt = m.get("metrics") or {}
    judge = mt.get("judge")
    if judge is not None and not isinstance(judge, dict):
        (rep.err if str(data.get("schema_version")) == "2" else rep.warn)(
            "business.moat.metrics.judge 必须是对象 {fcf|fcf_margin|net_margin|roe|roa: 判定句}；"
            "写成字符串会按字符拆成多条（渲染器已做单条兼容，但仍应改成对象）")
    rows = mt.get("rows") or []
    if not years:
        rep.err("business.moat.years 为空：五指标必须按年铺开")
    elif len(years) < 5:
        rep.warn(f"business.moat.years 只有 {len(years)} 年，判断护城河至少要 5 年")
    if not rows:
        rep.err("business.moat.metrics.rows 为空：缺少 FCF / 净利率 / ROE 等指标行")

    keys = {str(r.get("key")) for r in rows}
    missing = MOAT_ROWS - keys
    if missing:
        rep.err(f"business.moat.metrics.rows 缺 {sorted(missing)}："
                f"FCF / FCF 营收比 / 净利率 / ROE / ROA 五个都要有"
                f"（缺行会让三节护城河表少一行、趋势图少一条线）")

    for r in rows:
        vals = r.get("values") or []
        if years and len(vals) != len(years):
            rep.err(f"护城河指标「{r.get('name')}」有 {len(vals)} 个值，但 years 有 {len(years)} 个")
        bad = [v for v in vals if v not in (None, "-", "—") and not _num(v)]
        if bad:
            rep.err(f"护城河指标「{r.get('name')}」含非数字 {bad[:3]}；"
                    f"表格渲染不出来（要写纯数字，单位放 name 或 unit）")

    charts = m.get("charts") or []
    if not charts:
        rep.warn("business.moat.charts 为空：按新规范护城河要配趋势图")
    for ci, ch in enumerate(charts, 1):
        ctitle = ch.get("title") or f"护城河图 {ci}"
        lv = ch.get("labels") or years
        for srow in (ch.get("series") or []):
            sv = srow.get("values") or []
            if len(sv) != len(lv):
                rep.err(f"「{ctitle}」序列「{srow.get('name')}」{len(sv)} 个值 ≠ labels {len(lv)} 个")
            bad = [v for v in sv if not _num(v)]
            if bad:
                rep.err(f"「{ctitle}」序列「{srow.get('name')}」含非数字 {bad[:3]}，图会整块消失")

    ro = m.get("roic") or {}
    if not ro:
        rep.warn("business.moat.roic 缺失：缺 ROIC vs WACC 这一步")
    else:
        v, w = ro.get("value"), ro.get("wacc")
        if not _num(v) or not _num(w):
            rep.err(f"business.moat.roic 的 value/wacc 必须是数字（当前 {v!r} / {w!r}）")
        elif ro.get("spread") is not None and _num(ro.get("spread")):
            gap = abs(float(ro["spread"]) - (float(v) - float(w)))
            if gap > 0.5:
                rep.err(f"roic.spread={ro.get('spread')} 与 value-wacc={float(v) - float(w):.1f} 对不上")

    src = m.get("sources") or []
    if not src:
        rep.warn("business.moat.sources 为空：须回答“凭什么把对手挡在门外”")
    for it in src:
        if str(it.get("strength", "")) not in MOAT_SRC_STRENGTHS:
            rep.err(f"护城河来源「{it.get('type')}」strength={it.get('strength')!r}，"
                    f"只能是 strong / mid / weak / none")
        if not it.get("evidence"):
            rep.err(f"护城河来源「{it.get('type')}」没有 evidence：不能只有结论没有证据")

    if not m.get("verdict"):
        rep.warn("business.moat.verdict 为空：护城河要有明确结论")


def check(path: Path, rep: Report, require_raw: bool = False) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:                                    # noqa: BLE001
        rep.err(f"JSON 解析失败：{e}")
        return
    if not isinstance(data, dict):
        rep.err("根节点必须是对象")
        return
    check_data(data, rep, require_raw=require_raw)


def _check_raw_data(data: dict, rep: Report, require_raw: bool) -> None:
    """交付 JSON 里的 raw_data：远程原始返回必须原样同存。

    `--require-raw` 由 save_report.py 打开；普通结构校验默认不强制，
    以免历史样例（没有 raw_data）全部变红。
    """
    raw = data.get("raw_data")
    if raw is None:
        if require_raw:
            rep.err("缺少 raw_data：远程原始返回必须与计算结果同存一个 JSON"
                    "（用 collect_raw.py 采集、save_report.py 合并）")
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from raw_bundle import validate_raw_data            # noqa: PLC0415
    except Exception as e:                                  # noqa: BLE001
        rep.warn(f"raw_data 结构未能检查：{e}")
        return
    for msg in validate_raw_data(raw):
        (rep.err if require_raw else rep.warn)(f"raw_data：{msg}")


def check_data(data: dict, rep: Report, require_raw: bool = False) -> None:
    """直接在内存里校验报告数据（save_report.py 用）。"""
    _check_raw_data(data, rep, require_raw)

    # ---------- schema / meta ----------
    is_v2 = str(data.get("schema_version")) == "2"
    if not is_v2:
        msg = (f"schema_version 不是 \"2\"（当前 {data.get('schema_version')!r}）")
        if data.get("financials"):
            rep.err(msg + "：有 financials 却缺版本号，说明字段结构可能已漂移")
        else:
            rep.warn(msg + "：走 v1 旧结构，报告会缺「财务全景」章节（渲染器仍兼容）")
    m = data.get("meta") or {}
    for k in ("name", "code", "price", "report_date"):
        if not m.get(k):
            rep.err(f"meta.{k} 缺失")
    code = str(m.get("code") or "")
    if code and not re.match(r"^(sh|sz|bj)\d{6}$", code):
        rep.err(f"meta.code={code!r} 不是 A 股代码（应为 sh/sz/bj + 6 位数字）；"
                f"本 skill 不覆盖港股（hk）/美股（us）")
    cap, cap_note = str(m.get("market_cap") or ""), str(m.get("cap_note") or "")
    if "亿" in cap and "亿元" in cap_note:
        rep.err(f"meta 市值单位重复：market_cap={cap!r} 已带单位，"
                f"cap_note 不要再写「亿元」（否则渲染成「{cap}　亿元」）")
    if not m.get("price_at"):
        rep.warn("meta.price_at 缺失——盘中价出报告时必须写清行情时点，否则估值不可复现")
    elif m.get("chg_note") and m["price_at"] not in str(m["chg_note"]):
        rep.warn("meta.price_at 与 meta.chg_note 不一致（两处都写了时点，容易自相矛盾）")

    if is_v2:
        for key, label in REQUIRED_V2.items():
            if data.get(key) in (None, "", [], {}):
                rep.err(f"v2 缺少必需区块「{key}」：{label} 整节不会出现")

    # ---------- 结论卡 ----------
    vv = data.get("verdict") or {}
    if not str(vv.get("stance") or "").strip():
        rep.err("verdict.stance 为空：报告没有明确结论，不能只靠分数")
    if is_v2 and not str(data.get("core_summary") or "").strip():
        rep.err("core_summary 为空：二、主要指标初步研判 必须以一句初步判断收尾")
    elif data.get("core_summary") and len(str(data.get("core_summary")).strip()) < 8:
        rep.err("core_summary 太短：至少写出一句可读的初步判断")

    # ---------- 股价表与图 ----------
    for i, r in enumerate((data.get("price") or {}).get("records") or [], 1):
        if not str(r.get("name") or "").strip() or not str(r.get("range") or "").strip():
            (rep.err if is_v2 else rep.warn)(
                f"price.records 第 {i} 行必须用 name/range/note（不是 label/value）；"
                f"缺 name 或 range 会渲染成「—」")
    for c in (data.get("price") or {}).get("chart_data") or []:
        if c.get("value") is not None and not _num(c.get("value")):
            rep.err(f"price.chart_data 的 value={c.get('value')!r} 不是数字；"
                    f"渲染器会 float() 崩溃（写成 12.5，不要写 12.5元）")

    # ---------- 估值口径自查 ----------
    cm = data.get("core_metrics") or []
    if len(cm) < MIN_CORE_METRICS:
        (rep.err if is_v2 else rep.warn)(
            f"core_metrics 只有 {len(cm)} 项，至少 {MIN_CORE_METRICS} 项"
            f"（含静态/滚动/动态 PE、PB、经营性 PB、股息率、ROE/ROA/ROIC）")
    for it in cm:
        if it.get("flag") not in (None, "", "ok", "warn", "bad"):
            rep.err(f"core_metrics「{it.get('label')}」flag={it.get('flag')!r}，"
                    f"只能是 ok / warn / bad（错值会静默套默认灰样式）")
    v = data.get("verdict") or {}
    if v.get("level") not in (None, "", "good", "mid", "bad", "watch"):
        rep.err(f"verdict.level={v.get('level')!r}，只能是 good / mid / bad / watch")
    labels = " ".join(str(x.get("label", "")) for x in cm)
    for need in ("静态 PE", "滚动 PE", "动态 PE", "PB"):
        if need not in labels:
            rep.warn(f"core_metrics 缺少「{need}」——三种 PE 必须一起报")

    # ---------- 财务全景 ----------
    f = data.get("financials") or {}
    periods = f.get("periods") or []
    qt = f.get("quarterly") or []
    if not f:
        rep.warn("没有 financials 区块，报告会走 v1 旧结构（缺 5 张图与单季主表）")
    else:
        if len(periods) < MIN_PERIODS:
            rep.err(f"financials.periods 只有 {len(periods)} 期，至少 {MIN_PERIODS} 期（覆盖近 2 年全部季报）")
        elif len(periods) < 12:
            rep.warn(f"financials.periods 只有 {len(periods)} 期：够最低门槛"
                     f"（≥{MIN_PERIODS} 期），但建议拉满接口的 16 期"
                     f"（单季倒挤 + 同季同比 + TTM 都要用）；若接口就这么多，报告里要说明")
        for row in qt:
            name = row.get("name", "?")
            vals = row.get("values") or []
            if len(vals) != len(periods):
                rep.err(f"单季主表「{name}」有 {len(vals)} 个值，但 periods 有 {len(periods)} 期（会错列）")
        if not (16 <= len(qt) <= 20):
            rep.warn(f"单季主表 {len(qt)} 行，建议 16~20 行")

        for key, label in (("yoy", "同季同比"), ("cumulative", "累计口径")):
            block = f.get(key) or {}
            headers = block.get("headers") or []
            if not headers:
                continue
            rows2 = block.get("series") or []
            if not rows2:
                rep.warn(f"financials.{key}（{label}）给了 headers 但 series 为空")
            for row in rows2:
                vals = row.get("values") or []
                if len(vals) != len(headers):
                    rep.err(f"financials.{key}.series「{row.get('name', '?')}」有 "
                            f"{len(vals)} 个值，但 headers 有 {len(headers)} 列（表格会错列）；"
                            f"headers 只放数据列，首列用 first_col")

        charts = f.get("charts") or []
        if not charts:
            rep.warn("financials.charts 为空，财务全景会没有图")
        for ci, ch in enumerate(charts, 1):
            ctitle = ch.get("title") or f"图 {ci}"
            lv = ch.get("labels") or periods
            # labels 可以是更短的年度子集（如 7 年 vs 17 期）；只要求
            # series[].values 与本图 labels 等长，不跨图跟 periods 比。
            ser = ch.get("series") or []
            if not ser:
                rep.err(f"图「{ctitle}」没有 series")
            for srow in ser:
                sv = srow.get("values") or []
                sname = srow.get("name", "?")
                if len(sv) != len(lv):
                    rep.err(f"图「{ctitle}」序列「{sname}」{len(sv)} 个值 ≠ labels {len(lv)} 个")
                bad = [v for v in sv if not _num(v)]
                if bad:
                    rep.err(f"图「{ctitle}」序列「{sname}」含非数字 {bad[:3]}——"
                            f"带 % / 亿 / 括号 的字符串画不出来，图会整块消失")
                if srow.get("type") not in ("bar", "line", None):
                    rep.err(f"图「{ctitle}」序列「{sname}」type 只能是 bar/line")

        lat = f.get("latest") or {}
        if f and not lat.get("items"):
            rep.warn("financials.latest.items 为空")
        for it in lat.get("items") or []:
            if not it.get("yoy"):
                rep.warn(f"最新一期「{it.get('label')}」没有同比列")

        bs = f.get("balance") or {}
        for r in bs.get("risks") or []:
            if str(r.get("level")) not in LEVELS:
                rep.err(f"安全判定「{r.get('name')}」level={r.get('level')!r} 不在 {sorted(LEVELS)}")
            if not r.get("threshold"):
                rep.warn(f"安全判定「{r.get('name')}」缺 threshold（阈值与说明）")

    # 护城河与估值不依赖 financials：v2 即使没有财务块也要检查，不能跳过。
    _check_moat(data, rep)
    _check_valuation(data, rep)

    # ---------- 排雷 ----------
    rf = data.get("redflags") or []
    if is_v2 and data.get("redflags_checked") != REDFLAG_TOTAL:
        rep.err(f"v2 必须给 redflags_checked={REDFLAG_TOTAL}（零命中也要声明 25 条逐条过）")
    if not rf and data.get("redflags_checked") != REDFLAG_TOTAL:
        rep.warn("没有命中项，且未声明 redflags_checked=25：无法证明 25 条逐条过")
    ids: list[int] = []
    for r in rf:
        if r.get("hit"):
            rid = r.get("id")
            if rid is None:
                rep.warn(f"命中项缺少 id（清单编号 1~25）：「{str(r.get('text'))[:20]}」")
            else:
                try:
                    rid = int(rid)
                except (TypeError, ValueError):
                    rep.err(f"redflags.id 必须是 1~25 的整数，当前 {r.get('id')!r}")
                else:
                    if not 1 <= rid <= REDFLAG_TOTAL:
                        rep.err(f"redflags.id={rid} 越界（1~{REDFLAG_TOTAL}）")
                    ids.append(rid)
            if not str(r.get("evidence") or "").strip():
                rep.err(f"命中项「{str(r.get('text'))[:20]}」没有 evidence（数字证据）")
            if str(r.get("level")) not in LEVELS:
                rep.err(f"命中项 level={r.get('level')!r} 不在 {sorted(LEVELS)}")
    if len(ids) != len(set(ids)):
        rep.err("redflags.id 有重复")

    # 零命中时，必须有一段「为什么一条都没中」的说明（redflags_note）。
    # 否则读者分不清「查过了」和「没查」——301087 那份报告就是靠这段补的。
    note = str(data.get("redflags_note") or "").strip()
    if not rf:
        if len(note) < 10:
            (rep.err if is_v2 else rep.warn)(
                "零命中时 redflags_note 必须写：说明为什么一条都没中、"
                "并点名最接近命中的三条（现金流 / 商誉 / 应收）")
    elif not note:
        rep.warn("有命中项但 redflags_note 为空：命中项之外的「沾边未中」观察会丢失")

    # ---------- 打分卡 ----------
    sc = data.get("scorecard") or {}
    steps = sc.get("steps") or []
    if len(steps) != EXPECTED_STEPS:
        rep.err(f"scorecard.steps 应为 {EXPECTED_STEPS} 步，当前 {len(steps)}")
    for st in steps:
        raw = str(st.get("state", "")).lower()
        if raw not in STATES:
            rep.err(f"第 {st.get('no')} 步 state={raw!r} 不在 {sorted(STATES)}")
        if not st.get("state_text"):
            rep.warn(f"第 {st.get('no')} 步缺 state_text（MD 版七步表会靠兜底映射，HTML 版正常）")
    items = sc.get("items") or []
    if is_v2 and len(items) != EXPECTED_ITEMS:
        rep.err(f"打分卡 {len(items)} 项，指标体系定义为 {EXPECTED_ITEMS} 项；"
                f"拿不到数据的项请保留并写 value: null（不可评），不要直接删行")
    elif items and len(items) != EXPECTED_ITEMS:
        rep.warn(f"打分卡 {len(items)} 项，指标体系定义为 {EXPECTED_ITEMS} 项；"
                 f"拿不到数据的项请保留并写 value: null（不可评），不要直接删行")
    wsum = 0.0
    total = 0.0
    w_eval = 0.0
    n_eval = 0
    for it in items:
        v, w = it.get("value"), it.get("weight")
        if v is None:                      # 不可评：权重仍计入 33，但不进分母
            if not _num(w):
                rep.err(f"打分卡「{it.get('dim')}」缺 weight")
            else:
                wsum += float(w)
            continue
        if not _num(v) or not _num(w):
            rep.err(f"打分卡「{it.get('dim')}」value 必须是 -2/-1/0/+1/+2 或 null（不可评）")
            continue
        if v not in (-2, -1, 0, 1, 2):
            rep.err(f"打分卡「{it.get('dim')}」分值 {v} 只能是 -2/-1/0/+1/+2")
        wsum += float(w)
        w_eval += float(w)
        total += float(v) * float(w)
        n_eval += 1
    if items:
        if n_eval < 8:
            rep.warn(f"可评项只有 {n_eval} 项（< 8），按 §13 应判「谨慎观望」并单列数据缺口")
        if n_eval < len(items):
            full = 2 * w_eval
            rate = (total / full * 100) if full else 0
            print(f"   · 可评 {n_eval} / {len(items)} 项，归一化得分率 {rate:.1f}%")
    if items and abs(wsum - WEIGHT_SUM) > 1e-6:
        (rep.err if len(items) == 16 else rep.warn)(
            f"打分卡权重合计 {wsum:g}，指标体系定义为 {WEIGHT_SUM}"
            + ("" if len(items) == 16 else f"（当前只有 {len(items)} 项，故仅告警）"))
    note_sc = str(sc.get("total_note") or "")
    if items and "成长" not in note_sc:
        rep.warn("scorecard.total_note 没提「成长」：本卡 16 项不含成长维度（§5 整章未进卡），"
                 "必须在说明里点明「本卡只评质地不评成长」，否则强改善型公司会被静默判低")
    declared = sc.get("total")
    if declared and items and is_v2:
        text = str(declared).strip()
        m_total = re.match(r"^([+\-]?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text)
        if not m_total:
            rep.err(f"scorecard.total 格式无法解析：{declared!r}（应形如 47 / 66（得分率 71.2%））")
        else:
            dv, dmax = float(m_total.group(1)), float(m_total.group(2))
            full = 2 * w_eval
            if abs(dv - total) > 0.5:
                rep.err(f"scorecard.total 标注 {dv:+.0f}，但按 items 实算 {total:+.0f}（对不上）")
            if abs(dmax - full) > 0.5:
                rep.err(f"scorecard.total 分母 {dmax:g}，但可评项满分应为 {full:g}（对不上）")
            m_rate = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
            if m_rate and full:
                calc_rate = total / full * 100
                if abs(float(m_rate.group(1)) - calc_rate) > 0.2:
                    rep.err(f"scorecard.total 得分率 {m_rate.group(1)}%，但实算 "
                            f"{calc_rate:.1f}%（括号里的百分比与分数对不上）")
            elif full:
                rep.warn("scorecard.total 建议在括号里写得分率，便于人工核对")

    # ---------- 结论与跟踪 ----------
    c = data.get("conclusion") or {}
    if is_v2 and len(c.get("paragraphs") or []) < 3:
        rep.err("conclusion.paragraphs 少于 3 段：八、综合研判必须有完整论证")
    elif len(c.get("paragraphs") or []) < 3:
        rep.warn("conclusion.paragraphs 少于 3 段")
    for key, label in (("watchlist", "跟踪清单"), ("triggers", "触发条件"),
                       ("paragraphs", "论证段落")):
        vals = c.get(key) or []
        if not isinstance(vals, list):
            rep.err(f"conclusion.{key} 必须是字符串数组（当前 {type(vals).__name__}）")
            continue
        for i, item in enumerate(vals, 1):
            if not isinstance(item, str) or not item.strip():
                rep.err(f"conclusion.{key}[{i}]={item!r} 必须是字符串；"
                        f"写成 dict 会被渲染成 Python 字面量（如 {{'item': …}}）")
    if len(c.get("watchlist") or []) < 3:
        rep.warn("conclusion.watchlist 少于 3 条")
    for w in c.get("watchlist") or []:
        if any(k in str(w) for k in ("关注行业", "持续跟踪", "保持关注")):
            rep.err(f"watchlist 出现空话：{w}")
    if not c.get("triggers"):
        rep.warn("conclusion.triggers 为空（缺“判断修正的触发条件”）")

    # ---------- PEG 的机构覆盖交叉核对 ----------
    # data_rating.ratingCnt 是「评级记录条数」，不是覆盖机构数；只覆盖 1~2 家时
    # PEG 的分母（预测净利）可靠性低，不能单独作为估值档位的主依据（2026-10-31 审核 #9）。
    cover = None
    for call in ((data.get("raw_data") or {}).get("calls") or []):
        if str(call.get("tool")) != "data_rating":
            continue
        resp = call.get("response") if isinstance(call.get("response"), dict) else {}
        body = resp.get("data") if isinstance(resp.get("data"), dict) else resp
        # 取各口径里的最大值当「最乐观覆盖数」：institutionCnt=0 表示「没统计到」，
        # 不能直接当 0 家（否则有 8 家评级、只是没统计的公司会被误报）。
        for k in ("forecastInstitutions", "institutionCnt", "ratingCnt"):
            v = body.get(k) if isinstance(body, dict) else None
            if _num(v):
                cover = int(v) if cover is None else max(cover, int(v))
    metric_labels = " ".join(str(x.get("label", "")) for x in cm)
    if cover is not None and cover < 3 and "PEG" in metric_labels:
        hedge = " ".join([str(data.get("redflags_note") or ""),
                          str(sc_note := (data.get("scorecard") or {}).get("total_note") or ""),
                          str((data.get("valuation") or {}).get("note") or ""),
                          " ".join(str(g) for g in (data.get("data_gaps") or []))])
        if not any(k in hedge for k in ("覆盖", "1 家", "一家", "弱证据", "机构数")):
            rep.warn(f"PEG 建立在 {cover} 家机构的预测上（data_rating/consensus 口径），"
                     f"但 total_note / valuation.note / data_gaps 都没提覆盖不足——"
                     f"按 §13 第 3 轴，覆盖 <3 家时 PEG 不得单独定档")

    # ---------- 数据缺口 ----------
    gaps = data.get("data_gaps")
    if not gaps:
        rep.warn("没有 data_gaps 清单——拿不到的指标应显式列出，而不是让区块消失")
    elif not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
        rep.err("data_gaps 必须是字符串数组（传字符串会被渲染成一串单字列表）")
    if not data.get("sources"):
        rep.err("sources 为空：每个数字都要有出处")
    elif not isinstance(data["sources"], list):
        rep.err("sources 必须是数组（传字符串会被渲染成逐字列表）")


def main() -> int:
    ap = argparse.ArgumentParser(description="报告数据 JSON 自检（v2）")
    ap.add_argument("json_path")
    ap.add_argument("--strict", action="store_true", help="把警告也算作失败")
    ap.add_argument("--require-raw", action="store_true",
                    help="要求 raw_data 存在且结构完整（交付时用；save_report.py 默认打开）")
    args = ap.parse_args()
    p = Path(args.json_path).expanduser()
    if not p.exists():
        print(f"错误：找不到 {p}", file=sys.stderr)
        return 1

    rep = Report()
    check(p, rep, require_raw=args.require_raw)
    print(f"== {p.name}: {len(rep.errors)} 个错误, {len(rep.warns)} 个警告")
    for e in rep.errors:
        print(f"  [错误] {e}")
    for w in rep.warns:
        print(f"  [警告] {w}")
    if rep.errors or (args.strict and rep.warns):
        return 1
    print("  通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
