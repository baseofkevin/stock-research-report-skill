#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_raw.py —— 把每一次远程原始返回收进同一个采集包。

背景：报告既要「可复算」，又只能交付一个数据 JSON。做法是先记采集包，
最后由 `save_report.py` 把采集包并入交付 JSON 的 `raw_data`。

用法（在 skill 目录下）：

    # 1. 开一个采集包
    RAW="$PWD/.raw/sz301101-raw.json"
    mkdir -p "$(dirname "$RAW")"
    python3 scripts/collect_raw.py init "$RAW" --code sz301101

    # 2. 走脚本取数：run 会调用 westock_client.js，并把完整返回写进采集包
    python3 scripts/collect_raw.py run "$RAW" \
        --tool data_quote --params '{"code":"sz301101"}'

    # 3. 走 data_* connector 工具时：把工具返回原样存成文件，再 add
    python3 scripts/collect_raw.py add "$RAW" \
        --tool data_finance --params '{"code":"sz301101","fields":"all","num":16}' \
        --response-file /tmp/finance.json

    # 4. 东财 F10 / 网页补数同样要留痕
    python3 scripts/collect_raw.py add "$RAW" \
        --source eastmoney --tool RPT_F10_FINANCE_GCASHFLOW \
        --url 'https://datacenter.eastmoney.com/...' --response-file /tmp/f10.json

    python3 scripts/collect_raw.py status "$RAW"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raw_bundle  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
CLIENT = SCRIPTS / "westock_client.js"
NO_DATA_MARKERS = ("未找到", "暂无", "无数据", "没有数据")


def _load_json_arg(value: str | None) -> Any:
    if not value:
        return {}
    if value == "-":
        return json.loads(sys.stdin.read())
    if value.startswith("@"):
        return json.loads(Path(value[1:]).expanduser().read_text(encoding="utf-8"))
    return json.loads(value)


def _is_no_data_text(text: str) -> bool:
    return any(k in (text or "") for k in NO_DATA_MARKERS)


def _read_response(args: argparse.Namespace) -> tuple[Any, str | None]:
    """返回 (response, raw_text)。失败返回 / 非 JSON 原文走 raw_text。"""
    if args.response:
        return _load_json_arg(args.response), None
    if args.response_file:
        p = Path(args.response_file).expanduser()
        text = sys.stdin.read() if str(p) == "-" else p.read_text(encoding="utf-8")
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            return None, text
    if args.text is not None:
        return None, args.text
    raise SystemExit("add 需要 --response / --response-file / --text 之一")


def _load_bundle(path: Path, code: str, create: bool) -> dict | None:
    """读取已有采集包；不存在时默认拒绝，只有显式 --create 才新建。"""
    if path.exists():
        return raw_bundle.load(path)
    if not create:
        print(f"错误：找不到采集包 {path}；请先 init（确实要新建空包就加 --create）。",
              file=sys.stderr)
        return None
    print(f"提示：{path} 不存在，按 --create 新建空采集包；"
          "如果是想续写旧包，请检查路径是否跨命令持久。", file=sys.stderr)
    return raw_bundle.new_bundle(code or "")


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if path.exists() and not args.force:
        print(f"错误：{path} 已存在；要重来请加 --force（会清空旧采集包）", file=sys.stderr)
        return 1
    bundle = raw_bundle.new_bundle(args.code or "")
    raw_bundle.save(bundle, path)
    print(f"已创建采集包：{path}" + (f"（{args.code}）" if args.code else ""))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    bundle = _load_bundle(path, args.code, args.create)
    if bundle is None:
        return 2
    response, raw_text = _read_response(args)
    params = _load_json_arg(args.params)
    if not isinstance(params, dict):
        print("错误：--params 必须是 JSON 对象", file=sys.stderr)
        return 2
    call = raw_bundle.append(
        bundle,
        source=args.source,
        tool=args.tool,
        params=params,
        response=response,
        raw_text=raw_text,
        error=args.error or "",
        url=args.url or "",
        note=args.note or "",
        at=args.at,
    )
    if call.get("ok") is False and _is_no_data_text(raw_text or ""):
        call["no_data"] = True
    raw_bundle.save(bundle, path)
    if call.get("no_data"):
        print(f"已记录 #{call['seq']} {args.tool} [NO DATA] → {path}")
        return 0
    mark = "ok" if call.get("ok") is not False else "FAILED"
    print(f"已记录 #{call['seq']} {args.tool} [{mark}] → {path}")
    if call.get("ok") is False:
        print("警告：这是一条失败/非 JSON 返回，已原样保留；不要把它当成「那天没数据」。",
              file=sys.stderr)
        return 3
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    bundle = _load_bundle(path, args.code, args.create)
    if bundle is None:
        return 2
    params = _load_json_arg(args.params)
    if not isinstance(params, dict):
        print("错误：--params 必须是 JSON 对象", file=sys.stderr)
        return 2
    client = Path(args.client).expanduser() if args.client else CLIENT
    if not client.exists():
        print(f"错误：找不到客户端 {client}", file=sys.stderr)
        return 1
    cmd = ["node", str(client), "call", args.tool, json.dumps(params, ensure_ascii=False)]
    print(f"$ {' '.join(cmd[:4])} …", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    if proc.returncode == 0:
        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError:
            call = raw_bundle.append(
                bundle, source=args.source, tool=args.tool, params=params,
                raw_text=proc.stdout, error="客户端退出 0 但 stdout 不是 JSON",
                note=args.note or "")
        else:
            call = raw_bundle.append(
                bundle, source=args.source, tool=args.tool, params=params,
                response=response, note=args.note or "")
    else:
        # exit 3 = 工具返回纯文本；原文必须保留。
        # 但「未找到 / 暂无 / 无数据」是业务无数据，不是参数错，单独标记，方便不重试。
        no_data = _is_no_data_text(proc.stdout)
        error_text = "" if no_data else (proc.stderr or f"客户端退出码 {proc.returncode}").strip()[:1000]
        call = raw_bundle.append(
            bundle, source=args.source, tool=args.tool, params=params,
            raw_text=proc.stdout,
            error=error_text or ("" if no_data else "unknown"),
            note=args.note or "")
        if no_data:
            call["no_data"] = True
    raw_bundle.save(bundle, path)
    if call.get("no_data"):
        print(f"已记录 #{call['seq']} {args.tool} [NO DATA] → {path}")
        print(f"  业务无数据：{(proc.stdout or '').strip()[:160]}", file=sys.stderr)
        return 0
    if call.get("ok") is False:
        detail = (call.get("error") or "").strip().splitlines()
        raw = (call.get("raw_text") or "").strip().splitlines()
        first = (detail[0] if detail else (raw[0] if raw else "unknown"))[:120]
        print(f"已记录 #{call['seq']} {args.tool} [FAILED] {first} → {path}")
        if raw and (not detail or raw[0] != detail[0]):
            print(f"  原文：{raw[0][:160]}", file=sys.stderr)
        return proc.returncode or 3
    print(f"已记录 #{call['seq']} {args.tool} [ok] → {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"错误：找不到采集包 {path}；请先 init。", file=sys.stderr)
        return 1
    try:
        bundle = raw_bundle.load(path)
    except (OSError, ValueError) as e:
        print(f"错误：读取采集包失败：{e}", file=sys.stderr)
        return 1
    calls = bundle.get("calls") or []
    print(f"采集包          {path}")
    print(f"股票代码        {bundle.get('code') or '—'}")
    print(f"调用条数        {len(calls)}")
    print(f"成功 / 失败     {sum(1 for c in calls if c.get('ok') is not False)} / "
          f"{sum(1 for c in calls if c.get('ok') is False)}")
    if calls:
        print("工具            " + "、".join(sorted({str(c.get('tool')) for c in calls})))
        print(f"时间范围        {calls[0].get('at')} → {calls[-1].get('at')}")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    data_path = Path(args.data).expanduser()
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        calls = raw_bundle.load_calls_from_paths([args.path])
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"错误：合并失败：{e}", file=sys.stderr)
        return 1
    data["raw_data"] = raw_bundle.make_raw_data(data, calls)
    out = Path(args.out).expanduser() if args.out else data_path.with_name(
        data_path.stem + "-combined.json")
    raw_bundle.atomic_write_text(out, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"已合并 {len(calls)} 条原始返回 → {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="远程原始返回采集包（raw-v1）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="新建采集包")
    p_init.add_argument("path")
    p_init.add_argument("--code", default="")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_add = sub.add_parser("add", help="追加一条已经拿到的原始返回")
    p_add.add_argument("path")
    p_add.add_argument("--tool", required=True, help="接口名，如 data_quote / RPT_F10_FN_MAINOP")
    p_add.add_argument("--source", default="westock",
                       choices=sorted(raw_bundle.VALID_SOURCES))
    p_add.add_argument("--params", default="{}", help="请求参数 JSON，或 @file.json")
    p_add.add_argument("--response", help="返回 JSON 字符串")
    p_add.add_argument("--response-file", help="返回原文件；非 JSON 会自动按 raw_text 保存")
    p_add.add_argument("--text", help="非 JSON 原文（限频、报错信息等）")
    p_add.add_argument("--url", default="")
    p_add.add_argument("--note", default="")
    p_add.add_argument("--error", default="")
    p_add.add_argument("--at", default=None, help="采集时间，默认当前时间")
    p_add.add_argument("--code", default="")
    p_add.add_argument("--create", action="store_true",
                       help="采集包不存在时新建空包（默认拒绝，防静默丢证据）")
    p_add.set_defaults(func=cmd_add)

    p_run = sub.add_parser("run", help="调 westock_client.js 取数并记录（推荐）")
    p_run.add_argument("path")
    p_run.add_argument("--tool", required=True)
    p_run.add_argument("--params", default="{}")
    p_run.add_argument("--source", default="westock",
                       choices=sorted(raw_bundle.VALID_SOURCES))
    p_run.add_argument("--client", default="")
    p_run.add_argument("--timeout", type=int, default=120)
    p_run.add_argument("--note", default="")
    p_run.add_argument("--code", default="")
    p_run.add_argument("--create", action="store_true",
                       help="采集包不存在时新建空包（默认拒绝，防静默丢证据）")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="查看采集包概况")
    p_status.add_argument("path")
    p_status.set_defaults(func=cmd_status)

    p_merge = sub.add_parser("merge", help="把采集包并入报告数据 JSON")
    p_merge.add_argument("path")
    p_merge.add_argument("--data", required=True)
    p_merge.add_argument("-o", "--out")
    p_merge.set_defaults(func=cmd_merge)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
