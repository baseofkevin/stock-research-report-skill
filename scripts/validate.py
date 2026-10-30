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
from pathlib import Path

LEVELS = {"正常", "健康", "偏弱", "关注", "留意", "警告", "较差", "高危", "危险", "无数据"}
STATES = {"pass", "fail", "warn", "na"}
REDFLAG_TOTAL = 25
WEIGHT_SUM = 33          # 16 项打分卡权重合计（每项满分 +2 → 满分 66）
EXPECTED_STEPS = 7
MIN_PERIODS = 10


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
        for item in series:
            val = item.get("v") if isinstance(item, dict) else item
            if _num(val) and float(val) > 0:
                good.append(float(val))
        if len(good) < 20:
            rep.warn(f"估值指标「{name}」只有 {len(good)} 个历史样本（建议 ≥20，否则分位不可信）")
        if not good:
            continue
        calc = 100 * sum(1 for x in good if x < float(cur)) / len(good)
        declared = m.get("percentile")
        if declared is not None and _num(declared):
            if abs(float(declared) - calc) > 3:
                rep.err(f"估值指标「{name}」percentile={declared} 与按 series 重算的 "
                        f"{calc:.1f}% 相差超过 3pct——分位数字和图画的对不上")
        if float(cur) > max(good) * 1.0001 or float(cur) < min(good) * 0.9999:
            rep.warn(f"估值指标「{name}」当前值 {cur} 落在历史区间 "
                     f"{min(good):.2f}~{max(good):.2f} 之外，确认是否口径不同")
    if not v.get("lead"):
        rep.warn("valuation.lead 为空：这一节要有一句话结论")
    if not v.get("note"):
        rep.warn("valuation.note 为空：样本区间与口径要写清楚")


MOAT_STRENGTHS = {"wide", "narrow", "none"}
MOAT_SRC_STRENGTHS = {"strong", "mid", "weak", "none"}
MOAT_CORE_ROWS = {"fcf", "net_margin", "roe"}
MOAT_OPT_ROWS = {"fcf_margin", "roa"}


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
    rows = mt.get("rows") or []
    if not years:
        rep.err("business.moat.years 为空：五指标必须按年铺开")
    elif len(years) < 5:
        rep.warn(f"business.moat.years 只有 {len(years)} 年，判断护城河至少要 5 年")
    if not rows:
        rep.err("business.moat.metrics.rows 为空：缺少 FCF / 净利率 / ROE 等指标行")

    keys = {str(r.get("key")) for r in rows}
    missing = MOAT_CORE_ROWS - keys
    if missing:
        rep.err(f"business.moat.metrics.rows 缺少核心指标 {sorted(missing)}（FCF / 净利率 / ROE 必填）")
    lack_opt = MOAT_OPT_ROWS - keys
    if lack_opt:
        rep.warn(f"business.moat.metrics.rows 缺 {sorted(lack_opt)}（建议补齐五个指标）")

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


def check(path: Path, rep: Report) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:                                    # noqa: BLE001
        rep.err(f"JSON 解析失败：{e}")
        return
    if not isinstance(data, dict):
        rep.err("根节点必须是对象")
        return

    # ---------- schema / meta ----------
    if str(data.get("schema_version")) != "2":
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
    if not m.get("price_at"):
        rep.warn("meta.price_at 缺失——盘中价出报告时必须写清行情时点，否则估值不可复现")
    elif m.get("chg_note") and m["price_at"] not in str(m["chg_note"]):
        rep.warn("meta.price_at 与 meta.chg_note 不一致（两处都写了时点，容易自相矛盾）")

    # ---------- 估值口径自查 ----------
    cm = data.get("core_metrics") or []
    if len(cm) < 8:
        rep.warn(f"core_metrics 只有 {len(cm)} 项，建议 ≥10（含静态/滚动/动态 PE、PB、经营性 PB、股息率、ROE/ROA/ROIC）")
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

        charts = f.get("charts") or []
        if not charts:
            rep.warn("financials.charts 为空，财务全景会没有图")
        for ci, ch in enumerate(charts, 1):
            ctitle = ch.get("title") or f"图 {ci}"
            lv = ch.get("labels") or periods
            if not ch.get("labels"):
                rep.warn(f"图「{ctitle}」未给 labels，已回退到 periods（文档曾写“必须给”，实际可选）")
            if len(lv) != len(periods):
                rep.warn(f"图「{ctitle}」labels {len(lv)} 个 ≠ periods {len(periods)} 个")
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

        _check_moat(data, rep)
        _check_valuation(data, rep)

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

    # ---------- 排雷 ----------
    rf = data.get("redflags") or []
    if not rf:
        rep.warn("没有 redflags 区块（按规矩要逐条过 25 条，至少留下命中项）")
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
    if items and len(items) != 16:
        rep.warn(f"打分卡 {len(items)} 项，指标体系定义为 16 项；"
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
    declared = sc.get("total")
    if declared and items:
        try:
            dv = int(str(declared).strip().lstrip("+").split("/")[0].strip())
        except (TypeError, ValueError):
            rep.warn(f"scorecard.total 格式无法解析：{declared!r}")
        else:
            if abs(dv - total) > 0.5:
                rep.err(f"scorecard.total 标注 {dv:+d}，但按 items 实算 {total:+.0f}（对不上）")

    # ---------- 结论与跟踪 ----------
    c = data.get("conclusion") or {}
    if len(c.get("paragraphs") or []) < 3:
        rep.warn("conclusion.paragraphs 少于 3 段")
    if len(c.get("watchlist") or []) < 3:
        rep.warn("conclusion.watchlist 少于 3 条")
    for w in c.get("watchlist") or []:
        if any(k in str(w) for k in ("关注行业", "持续跟踪", "保持关注")):
            rep.err(f"watchlist 出现空话：{w}")
    if not c.get("triggers"):
        rep.warn("conclusion.triggers 为空（缺“判断修正的触发条件”）")

    # ---------- 数据缺口 ----------
    gaps = data.get("data_gaps")
    if not gaps:
        rep.warn("没有 data_gaps 清单——拿不到的指标应显式列出，而不是让区块消失")
    elif not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
        rep.err("data_gaps 必须是字符串数组（传字符串会被渲染成一串单字列表）")
    if not data.get("sources"):
        rep.err("sources 为空：每个数字都要有出处")


def main() -> int:
    ap = argparse.ArgumentParser(description="报告数据 JSON 自检（v2）")
    ap.add_argument("json_path")
    ap.add_argument("--strict", action="store_true", help="把警告也算作失败")
    args = ap.parse_args()
    p = Path(args.json_path).expanduser()
    if not p.exists():
        print(f"错误：找不到 {p}", file=sys.stderr)
        return 1

    rep = Report()
    check(p, rep)
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
