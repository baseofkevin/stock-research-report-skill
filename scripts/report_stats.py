#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_stats.py —— 估值分位的统一算法（校验器与渲染器共用同一份实现）。

为什么单独成文件：分位是**能改结论方向**的统计量，过去 validate.py 和
render_report.py 各算一遍，改一处忘一处就会出现「校验说 47.9%、图上写 52%」。
这里只放纯函数，不依赖任何 IO。

口径（与 `references/指标体系.md` §3.5 对齐）：

- `percentile`：低于当前值的样本数 ÷ 有效样本数 × 100（不含等于）；
- `trimmed_percentile`：**先剔除极端点、必要时再 5%/95% 缩尾**后算分位。
  极端点指 `v > min(100, 3 × 中位)`（即「> 100 倍」或「> 3 倍中位」任一成立），
  对应「利润塌陷期把 PE 推到 300 倍」那类样本；把这类点留在全样本里，
  分位会被压平、结论甚至反向（正海磁材：全样本 47.9% vs 剔除后 62.2%）。
- `is_outlier_sample`：样本里确实存在这类极端点时返回真——报告必须同时给两个口径。
"""
from __future__ import annotations

TRIM_PCT = 0.05          # 缩尾比例：两端各 5%
OUTLIER_PE = 100.0       # 估值倍数的绝对异常线（PE/PS 都适用，宁严勿松）
OUTLIER_RATIO = 3.0      # 相对异常线：max > 中位数 × 3


def clean(values) -> list[float]:
    """只要正数样本（负 PE 不进样本，见 §3.5）。"""
    return [float(v) for v in values if isinstance(v, (int, float)) and v > 0]


def median(values) -> float:
    xs = sorted(clean(values))
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def percentile(values, current: float) -> float:
    xs = clean(values)
    if not xs:
        return 0.0
    return 100.0 * sum(1 for x in xs if x < current) / len(xs)


def winsorize(values, pct: float = TRIM_PCT) -> list[float]:
    """两端各掐掉 pct 的样本；掐完不足 5 个就退回原样本（样本太少时缩尾没意义）。"""
    xs = sorted(clean(values))
    k = int(len(xs) * pct)
    return xs[k:len(xs) - k] if k and len(xs) - 2 * k >= 5 else xs


def outlier_cut(values) -> float:
    """极端点上界：`min(100 倍, 3 × 中位)`。返回 inf 表示没有可剔除的点。"""
    xs = clean(values)
    if not xs:
        return float("inf")
    return min(OUTLIER_PE, OUTLIER_RATIO * median(xs))


def trimmed_percentile(values, current: float) -> float:
    """剔除极端点后的分位；没有极端点时退回 5%/95% 缩尾（对分布尾部更稳健）。"""
    xs = clean(values)
    cut = outlier_cut(xs)
    kept = [v for v in xs if v <= cut]
    if len(kept) == len(xs):
        kept = winsorize(xs)
    return percentile(kept, current)


def is_outlier_sample(values) -> bool:
    xs = clean(values)
    if not xs:
        return False
    top = max(xs)
    return top > OUTLIER_PE or top > OUTLIER_RATIO * median(xs)


def trim_bounds(values) -> tuple[float, float] | None:
    """[最小正常值, 极端点上界]；落在区间外的点由渲染器画成空心圈。"""
    xs = sorted(clean(values))
    cut = outlier_cut(xs)
    if not xs or cut >= xs[-1]:
        return None
    return xs[0], cut
