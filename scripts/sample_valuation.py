#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sample_valuation.py —— 月末估值采样，只补缺失月份。

第七节的 PE/PB/PS 历史分位靠 `data_quote(date=YYYY-MM-DD)` 的月末采样。
手工循环容易犯三个错：把超时当成「那天没数据」、把空返回记成 0、重复采已有月份。
本脚本只做一件事：读取 raw-v1 采集包里已有的 `data_quote(date=...)`，按月补齐，
每次成功立即落盘；超时 / 限频分开退避，空返回回退到前一个交易日。

用法：
    python3 scripts/sample_valuation.py --code sz000629 \
        --raw .raw/sz000629-raw.json --years 5

    # 指定区间 / 先看会采哪些月份
    python3 scripts/sample_valuation.py --code sz000629 --raw .raw/sz000629-raw.json \
        --start 2021-11-01 --end 2026-10-31 --dry-run

采集包必须先 `collect_raw.py init`；本脚本不会静默新建空包。
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raw_bundle  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
CLIENT = SCRIPTS / "westock_client.js"
CODE_RE = re.compile(r"^(sh|sz|bj)?(\d{6})$")


def normalize_code(value: str) -> str:
    s = str(value or "").strip().lower()
    m = CODE_RE.search(s)
    return (m.group(1) or "") + m.group(2) if m else s


def parse_day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"日期要写成 YYYY-MM-DD：{value!r}")


def month_ends(start: date, end: date) -> list[date]:
    """[start, end] 内每个月的最后一天。"""
    out: list[date] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = date(y, m, calendar.monthrange(y, m)[1])
        if start <= last <= end:
            out.append(last)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def prev_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def existing_months(bundle: dict, code: str) -> set[tuple[int, int]]:
    """采集包里已经有的月份（按 data_quote 的 params.date 判断）。"""
    want = normalize_code(code)
    months: set[tuple[int, int]] = set()
    for call in bundle.get("calls") or []:
        params = call.get("params") or {}
        if call.get("tool") != "data_quote" or call.get("ok") is False:
            continue
        response = call.get("response") or {}
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict) or not any(bool(v) for v in data.values()):
            continue
        got = normalize_code(params.get("code", ""))
        if got and want and got != want:
            continue
        raw = str(params.get("date") or "")
        try:
            d = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        months.add((d.year, d.month))
    return months


def classify_text(text: str) -> str:
    t = (text or "").strip()
    low = t.lower()
    if "服务限频" in t or "rate limit" in low:
        return "rate_limit"
    if "请求超时" in t or "timeout" in low or "timed out" in low:
        return "timeout"
    if any(k in t for k in ("未找到", "暂无", "无数据", "没有数据")):
        return "no_data"
    return "error"


def call_quote(code: str, day: date, timeout_ms: int) -> tuple[int, str]:
    cmd = [
        "node", str(CLIENT), "call", "data_quote",
        json.dumps({"code": code, "date": day.isoformat()}, ensure_ascii=False),
        "--timeout", str(timeout_ms),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=max(30, timeout_ms / 1000 + 30),
        )
    except subprocess.TimeoutExpired:
        return 124, f"请求超时 {timeout_ms // 1000}s（本地进程超时）"
    raw = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, (raw or err)


def has_data(response: dict) -> bool:
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        return False
    # data 可能是 {"sz000629": {...}}，也可能是 {"sz000629": {}}；后者仍是空
    return any(bool(v) for v in data.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="月末估值采样：只补缺失月份")
    ap.add_argument("--code", required=True, help="股票代码，支持 sh/sz/bj 前缀或 6 位数字")
    ap.add_argument("--raw", required=True, help="raw-v1 采集包路径（必须先 init）")
    ap.add_argument("--years", type=int, default=5, help="默认回看年数（默认 5）")
    ap.add_argument("--start", type=parse_day, help="起始日 YYYY-MM-DD（覆盖 --years）")
    ap.add_argument("--end", type=parse_day, help="结束日 YYYY-MM-DD（默认今天）")
    ap.add_argument("--timeout", type=int, default=20000, help="单次客户端超时毫秒（默认 20000）")
    ap.add_argument("--retries", type=int, default=3, help="超时/限频重试次数（默认 3）")
    ap.add_argument("--sleep", type=float, default=0.5, help="每次请求后的额外间隔秒（默认 0.5）")
    ap.add_argument("--dry-run", action="store_true", help="只打印待补月份，不发请求")
    args = ap.parse_args()

    code = normalize_code(args.code)
    if not code:
        print("错误：--code 不合法", file=sys.stderr)
        return 2
    path = Path(args.raw).expanduser()
    if not path.exists():
        print(f"错误：找不到采集包 {path}；请先 collect_raw.py init。", file=sys.stderr)
        return 2
    try:
        bundle = raw_bundle.load(path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"错误：读取采集包失败：{e}", file=sys.stderr)
        return 1

    end = args.end or date.today()
    start = args.start or date(end.year - max(args.years, 1), end.month, 1)
    if start > end:
        print("错误：--start 不能晚于 --end", file=sys.stderr)
        return 2
    targets = month_ends(start, end)
    have = existing_months(bundle, code)
    todo = [d for d in targets if (d.year, d.month) not in have]

    print(f"采集包        {path}")
    print(f"股票          {code}　区间 {start} ~ {end}")
    print(f"目标月份      {len(targets)}　已有 {len(have)}　待补 {len(todo)}")
    if args.dry_run:
        for d in todo:
            print(f"  待补 {d.isoformat()}（月末）")
        return 0
    if not todo:
        print("无需补采。")
        return 0

    ok = skipped = failed = 0
    for idx, month_end in enumerate(todo, 1):
        candidates = [month_end]
        for _ in range(3):
            candidates.append(prev_weekday(candidates[-1]))
        seen: set[date] = set()
        candidates = [d for d in candidates
                      if not (d in seen or seen.add(d)) and d.month == month_end.month]
        month_ok = month_failed = False
        for day in candidates:
            attempts = 0
            day_done = False
            while True:
                attempts += 1
                rc, text = call_quote(code, day, args.timeout)
                status = ""
                response = None
                if rc == 0:
                    try:
                        response = json.loads(text)
                    except json.JSONDecodeError:
                        status = "error"
                    else:
                        if has_data(response):
                            raw_bundle.append(
                                bundle, source="westock", tool="data_quote",
                                params={"code": code, "date": day.isoformat()},
                                response=response,
                                note="sample_valuation 月末采样",
                            )
                            raw_bundle.save(bundle, path)
                            print(f"[{idx}/{len(todo)}] {day} OK")
                            month_ok = day_done = True
                            break
                        if isinstance(response, dict) and response.get("ok") is False:
                            status = classify_text(str(response.get("message") or ""))
                        else:
                            status = "no_data"
                else:
                    status = classify_text(text)
                if status == "no_data":
                    break                       # 合法空返回：换前一个交易日，不重试
                if status in ("timeout", "rate_limit") and attempts <= args.retries:
                    wait = 60 if status == "rate_limit" else 5 * (3 ** (attempts - 1))
                    print(f"[{idx}/{len(todo)}] {day} {status}，{wait}s 后重试 "
                          f"({attempts}/{args.retries})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                # 其他错误：原样留证，跳过这一天
                raw_bundle.append(
                    bundle, source="westock", tool="data_quote",
                    params={"code": code, "date": day.isoformat()},
                    raw_text=text,
                    error=f"sample_valuation {status}（尝试 {attempts} 次）",
                    note="sample_valuation 月末采样失败",
                )
                raw_bundle.save(bundle, path)
                print(f"[{idx}/{len(todo)}] {day} FAILED {status}", file=sys.stderr)
                month_failed = day_done = True
                break
            if day_done:
                break
            if args.sleep:
                time.sleep(args.sleep)
        if month_ok:
            ok += 1
        elif month_failed:
            failed += 1
        else:
            skipped += 1
            print(f"[{idx}/{len(todo)}] {month_end:%Y-%m} 无数据，已跳过", file=sys.stderr)
        if args.sleep:
            time.sleep(args.sleep)

    covered = existing_months(bundle, code)
    hit = len({(d.year, d.month) for d in targets} & covered)
    print(f"完成：成功 {ok}　跳过 {skipped}　失败 {failed}")
    print(f"覆盖：{hit}/{len(targets)} 个月（{hit / len(targets) * 100:.1f}%）")
    return 0 if ok or skipped else 1


if __name__ == "__main__":
    sys.exit(main())
