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

import contextlib
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:                      # POSIX
    import fcntl
except ImportError:       # Windows
    fcntl = None
    import msvcrt

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
            fh.flush()
            os.fsync(fh.fileno())        # 断电也不留半截文件
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


@contextlib.contextmanager
def locked(path: str | Path, timeout: float = 60.0):
    """采集包的跨进程互斥锁（`<包>.lock`）。

    为什么需要：`sample_valuation` 采样期间，人用 `collect_raw add` 补一条，
    两边都是「读整包 → 改 → 写整包」，后写的会把先写的覆盖掉，而且不报错
    （2026-10-31 复盘 P0：终端说「已记录 #56」，文件里没有）。
    `atomic_write_text` 只保证不写坏文件，不解决这个 lost update。
    """
    p = Path(path).expanduser()
    lock_path = Path(str(p) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as fh:
        deadline = time.time() + timeout
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:                          # Windows：锁第 1 个字节
                    fh.seek(0)
                    if fh.read(1) == "":
                        fh.write("\0")
                        fh.flush()
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except (BlockingIOError, OSError):
                if time.time() > deadline:
                    raise TimeoutError(
                        f"等采集包锁超过 {timeout:g}s：{lock_path} 仍被另一个进程占用"
                        f"（采样脚本还在跑？等它结束再 add）")
                time.sleep(0.2)
        try:
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                else:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass


def update(path: str | Path, _extra: dict | None = None, **kwargs) -> dict:
    """锁内「重读 → 追加 → 写回 → 回读校验」，返回写完后的整包。

    所有写采集包的入口都必须走这里：调用方不能拿着启动时读的旧副本整包写回。
    `_extra` 是追加到这条 call 上的附加标记（如 `{"no_data": true}`），
    也必须在锁内写入——否则又变成一次锁外的整包写回。
    """
    p = Path(path).expanduser()
    with locked(p):
        bundle = load(p)
        call = append(bundle, **kwargs)
        if _extra:
            call.update(_extra)
        save(bundle, p)
        after = load(p)
    if not any(c.get("tool") == call.get("tool") and c.get("at") == call.get("at")
               and c.get("seq") == call["seq"] for c in (after.get("calls") or [])):
        raise RuntimeError(f"写入后回读不到 #{call['seq']} {call.get('tool')}：{p}")
    return after


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
    """记录一条调用；seq = 已有最大序号 + 1（包内顺序编号，重号会被后面重编）。"""
    call = make_call(**kwargs)
    calls = bundle.setdefault("calls", [])
    seqs = [c.get("seq") for c in calls if isinstance(c.get("seq"), int)]
    call["seq"] = (max(seqs) + 1) if seqs else len(calls) + 1
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
    seqs = [c.get("seq") for c in merged if isinstance(c.get("seq"), int)]
    if len(seqs) != len(set(seqs)):            # 采集包被并发写坏过：重编，别交出重号证据
        for i, call in enumerate(merged, 1):
            call["seq"] = i
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
