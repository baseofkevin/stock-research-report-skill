#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_cache.py —— 查输出目录里有没有研究过的公司（增量更新的入口）。

`env` 的 `REPORT_OUTPUT_DIR` 里每份报告是一个同名 JSON（v2.8.0 起）。再次研究同一家公司时，
先按 `meta.code`（优先）或 `meta.name` 找到旧 JSON，复用其中的 `raw_data` 和计算结果，
**不重新跑 16 次接口 + 40~85 次月末采样**；只有没研究过的公司才走完整取数。

也识别 v2.8.0 之前的旧产物：只有 `.html` / `.md`、没有 JSON 时，
按文件名和首行标题（`# 名称（szXXXXXX）企业信息解读`）识别公司，提示「需完整取数一次补 JSON」。

用法：
    python3 scripts/report_cache.py lookup --code sz301101
    python3 scripts/report_cache.py lookup --name 明月镜片 --json
    python3 scripts/report_cache.py lookup --code 301101 --json --fail-if-missing

退出码：找到（JSON 或旧 HTML/MD）返回 0；什么都没找到返回 3（便于脚本分支）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_paths  # noqa: E402

LEGACY_NAME = re.compile(r"^(?P<name>.+?)-企业信息解读-(?P<date>\d{8})$")
MD_TITLE = re.compile(r"^#\s*(?P<name>[^（(\n]+?)\s*[（(]\s*(?P<code>(?:sh|sz|bj)\d{6})\s*[）)]",
                      re.MULTILINE)
RAW_CODE = re.compile(r"(?:sh|sz|bj)\d{6}")
CODE_SPLIT = re.compile(r"^(sh|sz|bj)?(\d{6})$")


def normalize_code(value: Any) -> str:
    s = str(value or "").strip().lower()
    m = CODE_SPLIT.search(s)
    if m:
        return (m.group(1) or "") + m.group(2)
    return s


def _code_matches(want: str, got: str) -> bool:
    want, got = normalize_code(want), normalize_code(got)
    if not want or not got:
        return False
    if want == got:
        return True
    # 一边带 sh/sz/bj、一边只给 6 位数字时按 6 位比；两边都带前缀则必须前缀一致
    pw = want[:-6] if len(want) > 6 else ""
    pg = got[:-6] if len(got) > 6 else ""
    if pw and pg and pw != pg:
        return False
    return want[-6:] == got[-6:]


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


def record_from_json(path: Path) -> dict | None:
    """读取一个 JSON，抽成缓存记录；不是报告文件就返回 None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    meta = data.get("meta") or {}
    code = str(meta.get("code") or "").strip()
    name = str(meta.get("name") or "").strip()
    if not code and not name:
        return None
    raw = data.get("raw_data") or {}
    calls = raw.get("calls") if isinstance(raw, dict) else None
    return {
        "kind": "json",
        "has_data": True,
        "json": str(path),
        "html": str(path.with_suffix(".html")),
        "md": str(path.with_suffix(".md")),
        "has_html": path.with_suffix(".html").exists(),
        "has_md": path.with_suffix(".md").exists(),
        "basename": path.stem,
        "code": code,
        "name": name,
        "report_date": str(meta.get("report_date") or ""),
        "price_at": str(meta.get("price_at") or ""),
        "price": meta.get("price"),
        "raw_call_count": raw.get("call_count") if isinstance(raw, dict) else 0,
        "raw_calls": len(calls) if isinstance(calls, list) else 0,
        "has_raw": bool(calls),
        "mtime": _mtime(path),
    }


def record_from_legacy(stem: Path) -> dict | None:
    """旧产物（只有 html/md、没有同名 JSON）按文件名 + 首行标题识别。"""
    m = LEGACY_NAME.match(stem.name)
    if not m:
        return None
    name = m.group("name").strip()
    date_raw = m.group("date")
    report_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
    md = stem.with_suffix(".md")
    html = stem.with_suffix(".html")
    code = ""
    probe = md if md.exists() else (html if html.exists() else None)
    if probe:
        try:
            text = probe.read_text(encoding="utf-8", errors="replace")[:200_000]
        except OSError:
            text = ""
        title = MD_TITLE.search(text)
        if title:
            name = title.group("name").strip() or name
            code = title.group("code")
        elif html.exists():
            found = RAW_CODE.search(text)
            if found:
                code = found.group(0)
    return {
        "kind": "legacy",
        "has_data": False,
        "json": "",
        "html": str(html) if html.exists() else "",
        "md": str(md) if md.exists() else "",
        "has_html": html.exists(),
        "has_md": md.exists(),
        "basename": stem.name,
        "code": code,
        "name": name,
        "report_date": report_date,
        "price_at": "",
        "price": None,
        "raw_call_count": 0,
        "raw_calls": 0,
        "has_raw": False,
        "mtime": _mtime(probe or html if html.exists() else md),
    }


def _dir(out_dir: str | Path | None, env_file: str | Path | None) -> Path:
    return (Path(out_dir).expanduser() if out_dir
            else report_paths.load_config(env_file)["output_dir"])


def scan_reports(*, out_dir: str | Path | None = None,
                 env_file: str | Path | None = None) -> list[dict]:
    """扫描输出目录顶层所有带 JSON 的报告。"""
    directory = _dir(out_dir, env_file)
    if not directory.exists():
        return []
    records = [r for p in sorted(directory.glob("*.json")) if (r := record_from_json(p))]
    records.sort(key=lambda r: (r.get("report_date") or "", r.get("mtime") or ""),
                 reverse=True)
    return records


def scan_legacy_reports(*, out_dir: str | Path | None = None,
                        env_file: str | Path | None = None) -> list[dict]:
    """扫描没有同名 JSON 的旧 HTML/MD（v2.8.0 之前的历史报告）。"""
    directory = _dir(out_dir, env_file)
    if not directory.exists():
        return []
    seen: set[str] = set()
    records: list[dict] = []
    for pattern in ("*.html", "*.md"):
        for p in sorted(directory.glob(pattern)):
            stem = p.with_suffix("")
            if stem.name in seen or p.with_suffix(".json").exists():
                continue
            seen.add(stem.name)
            rec = record_from_legacy(stem)
            if rec:
                records.append(rec)
    records.sort(key=lambda r: (r.get("report_date") or "", r.get("mtime") or ""),
                 reverse=True)
    return records


def _filter(records: list[dict], code: str | None, name: str | None) -> list[dict]:
    if code:
        records = [r for r in records if _code_matches(code, r.get("code", ""))]
    if name:
        needle = str(name).strip()
        exact = [r for r in records if r.get("name") == needle]
        if exact:
            records = exact
        else:
            records = [r for r in records
                       if needle and (needle in r.get("name", "")
                                      or needle in r.get("basename", ""))]
    return records


def find_reports(*, code: str | None = None, name: str | None = None,
                 out_dir: str | Path | None = None,
                 env_file: str | Path | None = None) -> list[dict]:
    """按代码/名称筛所有报告（JSON 优先，旧 HTML/MD 也返回）。"""
    records = _filter(scan_reports(out_dir=out_dir, env_file=env_file), code, name)
    legacy = _filter(scan_legacy_reports(out_dir=out_dir, env_file=env_file), code, name)
    combined = records + legacy
    combined.sort(key=lambda r: (r.get("has_data", False),
                                r.get("report_date") or "", r.get("mtime") or ""),
                  reverse=True)
    return combined


def latest_report(**kwargs) -> dict | None:
    records = find_reports(**kwargs)
    return records[0] if records else None


def latest_data_report(**kwargs) -> dict | None:
    """只返回带 JSON 的旧报告；--reuse 必须用它，不能拿旧 HTML/MD 冒充数据。"""
    records = _filter(scan_reports(out_dir=kwargs.get("out_dir"),
                                   env_file=kwargs.get("env_file")),
                      kwargs.get("code"), kwargs.get("name"))
    return records[0] if records else None


def latest_legacy_report(**kwargs) -> dict | None:
    records = _filter(scan_legacy_reports(out_dir=kwargs.get("out_dir"),
                                          env_file=kwargs.get("env_file")),
                      kwargs.get("code"), kwargs.get("name"))
    return records[0] if records else None


def payload(records: list[dict], *, code: str | None = None,
            name: str | None = None, env_file: str | Path | None = None,
            out_dir: str | Path | None = None) -> dict:
    directory = _dir(out_dir, env_file)
    data_reports = [r for r in records if r.get("has_data")]
    legacy_reports = [r for r in records if not r.get("has_data")]
    latest = data_reports[0] if data_reports else (legacy_reports[0] if legacy_reports else None)
    if data_reports:
        hint = "已研究过：默认用 save_report.py --reuse 更新三件套，不要重跑完整取数。"
    elif legacy_reports:
        hint = ("找到旧 HTML/MD，但没有数据 JSON：先完整取数一次补齐 JSON，"
                "之后才能用 save_report.py --reuse 只更新三件套。")
    else:
        hint = "未研究过：走完整取数流程（16 类接口 + 月末采样 + 跨源补数）。"
    return {
        "cached": bool(records),
        "has_data": bool(data_reports),
        "legacy_only": bool(legacy_reports and not data_reports),
        "count": len(records),
        "query": {"code": code or "", "name": name or ""},
        "output_dir": str(directory),
        "latest": latest,
        "reports": records,
        "data_reports": data_reports,
        "legacy_reports": legacy_reports,
        "hint": hint,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="查输出目录里是否已有某公司的研究报告")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lookup", help="按代码/名称查缓存")
    p.add_argument("--code", help="股票代码，支持 sh/sz/bj 前缀或 6 位数字")
    p.add_argument("--name", help="股票名称")
    p.add_argument("--out-dir", help="临时覆盖输出目录")
    p.add_argument("--env-file", help="临时指定 env 文件")
    p.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    p.add_argument("--fail-if-missing", action="store_true", help="没找到时 exit 3")
    p.add_argument("--quiet", action="store_true", help="只打印最新文件路径")

    args = ap.parse_args()
    if not args.code and not args.name:
        print("错误：至少给 --code 或 --name", file=sys.stderr)
        return 2

    try:
        records = find_reports(code=args.code, name=args.name,
                               out_dir=args.out_dir, env_file=args.env_file)
        data = payload(records, code=args.code, name=args.name,
                       env_file=args.env_file, out_dir=args.out_dir)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    if args.quiet and data["latest"]:
        r = data["latest"]
        print(r.get("json") or r.get("html") or r.get("md") or "")
    elif args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif data["cached"]:
        r = data["latest"]
        if r.get("has_data"):
            print(f"已研究过：{r['name']}（{r['code']}）")
            print(f"  最新 JSON   {r['json']}")
            print(f"  报告日      {r['report_date'] or '—'}　行情时点 {r['price_at'] or '—'}")
            print(f"  原始返回    {r['raw_call_count']} 条"
                  f"{'' if r['has_raw'] else '（旧报告没有 raw_data，建议补齐）'}")
            print(f"  HTML / MD   {'有' if r['has_html'] else '缺'} / "
                  f"{'有' if r['has_md'] else '缺'}")
        else:
            print(f"发现旧报告（无数据 JSON）：{r['name']}（{r['code'] or '代码未识别'}）")
            print(f"  HTML / MD   {r['html'] or '缺'}")
            print(f"              {r['md'] or '缺'}")
            print(f"  报告日      {r['report_date'] or '—'}")
            if data["legacy_reports"]:
                print(f"  同类旧报告 {len(data['legacy_reports'])} 份（按报告日/修改时间取最新）")
        if data["count"] > 1:
            print(f"  共匹配 {data['count']} 份；最新即以上这份，其余：")
            for x in data["reports"][1:]:
                print(f"    - {x['basename']}（{x['report_date'] or '—'}，"
                      f"{'JSON' if x.get('has_data') else '旧 HTML/MD'}）")
        print(f"  → {data['hint']}")
    else:
        print(f"未研究过：{args.name or args.code}（{data['output_dir']} 下没有匹配报告）")
        print(f"  → {data['hint']}")

    if not data["cached"] and args.fail_if_missing:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
