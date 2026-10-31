#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw_bundle.py —— 远程原始数据的采集包（raw-v1）读写与合并。

一次解读会调 16 类接口 + 40~85 次月末采样 + 东财 F10 补数。**所有原始返回
都要原样进同一个采集包**，最后并入交付 JSON 的 `raw_data` 字段：

    {
      "schema": "raw-v1",
      "code": "sz301101",
      "created_at": "2026-10-31 14:20:00",
      "updated_at": "2026-10-31 14:28:00",
      "calls": [
        {
          "seq": 1,
          "source": "westock",          # westock / eastmoney / web / file
          "tool": "data_quote",         # 或 RPT_F10_FINANCE_GCASHFLOW
          "params": {"code": "sz301101"},
          "at": "2026-10-31 14:20:03",
          "ok": true,
          "response": {"ok": true, "data": {...}}   # 原样，不做裁剪
        }
      ]
    }

`raw_data` 与报告计算结果同存一个 JSON；根节点的报告字段是计算/研判结果。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "raw-v1"
VALID_SOURCES = {"westock", "eastmoney", "web", "file", "manual"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def atomic_write_text(path: Path, text: str) -> None:
    """先写同目录临时文件再替换，避免半截 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".raw-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def new_bundle(code: str = "") -> dict:
    stamp = now()
    return {
        "schema": SCHEMA,
        "code": code,
        "created_at": stamp,
        "updated_at": stamp,
        "calls": [],
    }


def load(path: str | Path) -> dict:
    p = Path(path).expanduser()
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"{p} 顶层必须是对象（采集包或单次返回）")
    if obj.get("schema") == SCHEMA and isinstance(obj.get("calls"), list):
        return obj
    # 也接受「一个裸返回文件」当采集包用：包成一条 call
    return bundle_from_any(obj, path=p)


def save(bundle: dict, path: str | Path) -> Path:
    p = Path(path).expanduser()
    bundle["schema"] = SCHEMA
    bundle["updated_at"] = now()
    bundle.setdefault("calls", [])
    atomic_write_text(p, json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    return p


def _looks_like_tool_response(obj: Any) -> bool:
    return isinstance(obj, dict) and ("ok" in obj or "data" in obj or "message" in obj)


def make_call(*, source: str = "westock", tool: str = "", params: dict | None = None,
              response: Any = None, raw_text: str | None = None,
              error: str = "", url: str = "", note: str = "",
              at: str | None = None) -> dict:
    source = source if source in VALID_SOURCES else "manual"
    call: dict[str, Any] = {
        "source": source,
        "tool": tool or "unknown",
        "params": params or {},
        "at": at or now(),
    }
    if url:
        call["url"] = url
    if response is not None:
        call["response"] = response
        if _looks_like_tool_response(response) and response.get("ok") is False:
            call["ok"] = False
        else:
            call["ok"] = True
    if raw_text is not None:
        call["raw_text"] = raw_text
        call["ok"] = False
    if error:
        call["error"] = error
        call["ok"] = False
    call.setdefault("ok", True)
    if note:
        call["note"] = note
    return call


def add_call(bundle: dict, call: dict) -> dict:
    bundle.setdefault("calls", []).append(call)
    code = (call.get("params") or {}).get("code")
    if code and not bundle.get("code"):
        bundle["code"] = str(code)
    return call


def append(bundle: dict, **kwargs) -> dict:
    """记录一条调用；seq 按包内顺序自动编号。"""
    call = make_call(**kwargs)
    call["seq"] = len(bundle.setdefault("calls", [])) + 1
    return add_call(bundle, call)


def bundle_from_any(obj: Any, path: Path | None = None) -> dict:
    """把任意 JSON（单次返回 / 列表）包装成采集包。"""
    bundle = new_bundle()
    name = path.stem if path else "raw"
    if isinstance(obj, list):
        for item in obj:
            append(bundle, source="file", tool=name, response=item)
    else:
        append(bundle, source="file", tool=name, response=obj)
    return bundle


def calls_from(obj: Any, path: Path | None = None) -> list[dict]:
    """从采集包 / 单次返回 / 列表里抽出 calls 列表。"""
    if isinstance(obj, dict) and obj.get("schema") == SCHEMA and isinstance(obj.get("calls"), list):
        return list(obj["calls"])
    if isinstance(obj, list):
        name = path.stem if path else "raw"
        return [make_call(source="file", tool=name, response=item) for item in obj]
    name = path.stem if path else "raw"
    return [make_call(source="file", tool=name, response=obj)]


def load_calls_from_paths(paths: list[str | Path]) -> list[dict]:
    """读取文件或目录（目录下 *.json 按文件名排序）里的所有原始调用。"""
    calls: list[dict] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"找不到原始数据：{p}")
        if p.is_dir():
            files = sorted(p.glob("*.json"))
            if not files:
                raise ValueError(f"目录 {p} 下没有 *.json")
            for f in files:
                calls.extend(calls_from(json.loads(f.read_text(encoding="utf-8")), f))
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 记录失败返回（限频原文等），不能把非 JSON 当数据
            calls.append(make_call(source="file", tool=p.stem, raw_text=p.read_text(
                encoding="utf-8", errors="replace"), note="文件不是 JSON，按原始文本保留"))
            continue
        calls.extend(calls_from(obj, p))
    return calls


def make_raw_data(data: dict, calls: list[dict]) -> dict:
    """生成最终的 raw_data 区块：保留每条原始返回 + 一眼可见的统计。"""
    meta = data.get("meta") or {}
    existing = data.get("raw_data")
    merged: list[dict] = []
    if isinstance(existing, dict):
        merged.extend(existing.get("calls") or [])
    merged.extend(calls)
    for i, call in enumerate(merged, 1):
        call.setdefault("seq", i)
    tools = sorted({str(c.get("tool")) for c in merged if c.get("tool")})
    source_counts: dict[str, int] = {}
    for c in merged:
        src = str(c.get("source") or "manual")
        source_counts[src] = source_counts.get(src, 0) + 1
    return {
        "schema": SCHEMA,
        "code": str(meta.get("code") or ""),
        "generated_at": now(),
        "call_count": len(merged),
        "ok_count": sum(1 for c in merged if c.get("ok") is not False),
        "failed_count": sum(1 for c in merged if c.get("ok") is False),
        "sources": source_counts,
        "tools": tools,
        "calls": merged,
    }


def summarize(raw_data: dict) -> str:
    return (f"{raw_data.get('call_count', 0)} 条原始返回"
            f"（成功 {raw_data.get('ok_count', 0)} / 失败 {raw_data.get('failed_count', 0)}），"
            f"来源 {raw_data.get('sources') or {}}，工具 {len(raw_data.get('tools') or [])} 个")


def validate_raw_data(raw_data: Any) -> list[str]:
    """给 validate.py 用的结构检查，返回错误列表。"""
    errs: list[str] = []
    if not isinstance(raw_data, dict):
        return ["raw_data 必须是对象"]
    if raw_data.get("schema") != SCHEMA:
        errs.append(f"raw_data.schema 应为 {SCHEMA!r}（当前 {raw_data.get('schema')!r}）")
    calls = raw_data.get("calls")
    if not isinstance(calls, list) or not calls:
        errs.append("raw_data.calls 必须是非空数组（远程原始返回一条都不能少）")
        return errs
    for i, call in enumerate(calls, 1):
        if not isinstance(call, dict):
            errs.append(f"raw_data.calls[{i}] 必须是对象")
            continue
        if not call.get("tool"):
            errs.append(f"raw_data.calls[{i}] 缺 tool（接口名或数据源名称）")
        if call.get("source") not in VALID_SOURCES:
            errs.append(f"raw_data.calls[{i}].source={call.get('source')!r} 不在 {sorted(VALID_SOURCES)}")
        if "response" not in call and "raw_text" not in call and not call.get("error"):
            errs.append(f"raw_data.calls[{i}] 既没有 response / raw_text，也没有 error")
    return errs


if __name__ == "__main__":
    print("这个模块由 collect_raw.py / save_report.py 调用；"
          "直接运行请用 collect_raw.py 或 save_report.py。")
