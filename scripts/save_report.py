#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""save_report.py —— 一次写出「同名三件套」：数据 JSON + HTML + Markdown。

做四件事：
1. 把 `collect_raw.py` 采集到的远程原始返回并入报告 JSON 的 `raw_data`；
2. 按 skill 根目录 `env` 配置的 `REPORT_OUTPUT_DIR` 决定保存目录；
3. 用 `meta.name/code/report_date` 生成三个文件共用的主文件名；
4. 校验通过后，写 `{basename}.json`、`{basename}.html`、`{basename}.md`。

用法：
    python3 scripts/save_report.py data.json --raw .raw/sz301101-raw.json
    python3 scripts/save_report.py data.json --raw .raw/              # 目录也可
    python3 scripts/save_report.py data.json                         # data 里已有 raw_data 时

可选覆盖（排障/测试用，不写进 env）：
    --out-dir /tmp/测试输出   --basename 贵州茅台-企业信息解读-20261031
    --env-file /path/env      --skip-raw   --skip-validate   --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import raw_bundle  # noqa: E402
import report_cache  # noqa: E402
import report_paths  # noqa: E402
import validate as validator  # noqa: E402
from render_md import render_md  # noqa: E402
from render_report import render  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="合并原始数据并按 env 配置输出同名 JSON/HTML/MD")
    ap.add_argument("json_path", nargs="?",
                    help="报告计算数据 JSON；配合 --reuse --code 时可省略（直接从旧报告续写）")
    ap.add_argument("--reuse", action="store_true",
                    help="复用输出目录里同一公司的最新报告：无 raw 时补旧 raw_data，不重拉全量数据")
    ap.add_argument("--code", help="--reuse 时按代码查找旧报告（支持 sh/sz/bj 前缀或 6 位数字）")
    ap.add_argument("--name", help="--reuse 时按名称查找旧报告")
    ap.add_argument("--raw", action="append", default=[],
                    help="新增的原始采集包文件或目录，可给多次；会与复用到的旧 raw_data 合并")
    ap.add_argument("--out-dir", help="临时覆盖输出目录（不改 env）")
    ap.add_argument("--basename", help="临时覆盖三件套主文件名（不改 env）")
    ap.add_argument("--env-file", help="临时指定 env 文件（默认 skill 根目录/env）")
    ap.add_argument("--skip-raw", action="store_true",
                    help="允许没有 raw_data（只用于旧数据排障，正常交付不要用）")
    ap.add_argument("--skip-validate", action="store_true", help="跳过 validate.py 自检")
    ap.add_argument("--strict", action="store_true", help="把 validate 的警告也算失败")
    args = ap.parse_args()

    if not args.json_path and not (args.reuse and (args.code or args.name)):
        print("错误：要么给报告 JSON，要么用 --reuse --code/--name 从旧报告更新。",
              file=sys.stderr)
        return 2

    # ---------- 0. 先找旧报告（已研究过的公司只更新三件套） ----------
    cached = None
    if args.reuse and (args.code or args.name):
        cached = report_cache.latest_data_report(
            code=args.code, name=args.name, out_dir=args.out_dir, env_file=args.env_file)
        if not cached:
            legacy = report_cache.latest_legacy_report(
                code=args.code, name=args.name, out_dir=args.out_dir, env_file=args.env_file)
            if legacy:
                print(f"错误：只找到 {legacy['name']}（{legacy['code'] or '代码未识别'}）的旧 HTML/MD，"
                      "没有数据 JSON；请先完整取数一次补齐 JSON，之后才能 --reuse。",
                      file=sys.stderr)
                return 5
            print(f"错误：输出目录里没有 {args.code or args.name or ''} 的旧报告；"
                  "这是第一次研究，请走完整取数。", file=sys.stderr)
            return 4
        print(f"复用旧报告      {cached['json']}（{cached['name']} / {cached['code']}）")

    if args.json_path:
        src = Path(args.json_path).expanduser()
        if not src.exists():
            print(f"错误：找不到 {src}", file=sys.stderr)
            return 1
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"错误：JSON 解析失败 {e}", file=sys.stderr)
            return 1
        if not isinstance(data, dict):
            print("错误：报告 JSON 顶层必须是对象", file=sys.stderr)
            return 1
    else:
        # 没有给新 JSON：直接把旧 JSON 当作数据源，重写三件套（只更新输出）
        try:
            data = json.loads(Path(cached["json"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"错误：读取旧报告失败：{e}", file=sys.stderr)
            return 1

    # ---------- 1. 合并原始数据 ----------
    if args.reuse and cached is None:
        meta = data.get("meta") or {}
        cached = report_cache.latest_data_report(
            code=meta.get("code"), name=meta.get("name"),
            out_dir=args.out_dir, env_file=args.env_file)
        if not cached:
            legacy = report_cache.latest_legacy_report(
                code=meta.get("code"), name=meta.get("name"),
                out_dir=args.out_dir, env_file=args.env_file)
            if legacy:
                print(f"错误：只找到 {legacy['name']}（{legacy['code'] or '代码未识别'}）的旧 HTML/MD，"
                      "没有数据 JSON；请先完整取数一次补齐 JSON，之后才能 --reuse。",
                      file=sys.stderr)
                return 5
            print(f"错误：输出目录里没有 {meta.get('code') or meta.get('name') or ''} 的旧报告；"
                  "这是第一次研究，请走完整取数。", file=sys.stderr)
            return 4
        print(f"复用旧报告      {cached['json']}（{cached['name']} / {cached['code']}）")
    if args.reuse and not isinstance(data.get("raw_data"), dict):
        if cached:
            try:
                old = json.loads(Path(cached["json"]).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(f"错误：读取旧报告失败：{e}", file=sys.stderr)
                return 1
            if isinstance(old.get("raw_data"), dict):
                data["raw_data"] = old["raw_data"]
                print(f"复用原始数据    {raw_bundle.summarize(data['raw_data'])}")
            else:
                print("警告：旧报告没有 raw_data，本次又没有 --raw；这份 JSON 不可复算。",
                      file=sys.stderr)

    if args.raw:
        try:
            calls = raw_bundle.load_calls_from_paths(args.raw)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"错误：读取原始数据失败：{e}", file=sys.stderr)
            return 1
        data["raw_data"] = raw_bundle.make_raw_data(data, calls)
        print(f"原始数据        {raw_bundle.summarize(data['raw_data'])}")
    elif not isinstance(data.get("raw_data"), dict):
        if args.skip_raw:
            print("警告：没有 raw_data，且使用了 --skip-raw；这份 JSON 不可复算。", file=sys.stderr)
        else:
            print("错误：没有远程原始数据。请用 --raw 指定 collect_raw.py 的采集包"
                  "（或目录）；已研究过的公司可加 --reuse 复用旧 raw_data。", file=sys.stderr)
            return 2

    # ---------- 2. 解析保存路径（env） ----------
    try:
        paths = report_paths.output_paths(
            data, out_dir=args.out_dir, basename=args.basename, env_file=args.env_file)
        cfg = report_paths.load_config(args.env_file)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    base = paths["basename"]
    data["_data_package"] = {
        "schema": "combined-v1",
        "saved_at": raw_bundle.now(),
        "basename": base,
        "output_dir": str(paths["dir"]),
        "computed_data": "根节点（raw_data / _data_package 之外的全部报告字段）",
        "raw_data": "raw_data",
        "raw_call_count": (data.get("raw_data") or {}).get("call_count", 0),
        "note": "同一个 JSON 同时保存远程原始返回与 skill 计算结果；文件名与 html / md 一致。",
    }

    # ---------- 3. 校验（含 raw_data 闸门） ----------
    if not args.skip_validate:
        rep = validator.Report()
        validator.check_data(data, rep, require_raw=not args.skip_raw)
        print(f"数据自检        {len(rep.errors)} 个错误，{len(rep.warns)} 个警告")
        for e in rep.errors:
            print(f"  [错误] {e}")
        for w in rep.warns:
            print(f"  [警告] {w}")
        if rep.errors:
            print("校验未通过：三个文件都没有写入。先改数据，再重跑。", file=sys.stderr)
            return 1
        if args.strict and rep.warns:
            print("--strict：警告也算失败，三个文件都没有写入。", file=sys.stderr)
            return 1

    # ---------- 4. 写出同名三件套 ----------
    paths["dir"].mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    raw_bundle.atomic_write_text(paths["json"], json_text)

    try:
        html = render(data)
        md = render_md(data)
    except Exception as e:  # noqa: BLE001  渲染失败不能留下「只有 JSON」的假成功
        print(f"错误：渲染失败，HTML/MD 未写入：{e}", file=sys.stderr)
        return 1
    raw_bundle.atomic_write_text(paths["html"], html)
    raw_bundle.atomic_write_text(paths["md"], md)

    print("已生成同名三件套：")
    for ext in ("json", "html", "md"):
        p: Path = paths[ext]
        print(f"  {ext.upper():<4}  {p}  （{p.stat().st_size / 1024:.1f} KB）")
    print(f"输出目录        {paths['dir']}"
          f"{'' if cfg['exists'] else '（env 不存在，使用默认目录）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
