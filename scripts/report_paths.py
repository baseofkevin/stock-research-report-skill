#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_paths.py —— 报告输出目录与三件套文件名解析（env 配置）。

这个模块是「json / html / md 存到哪里、叫什么名字」的唯一真源：
`render_report.py`、`render_md.py`、`save_report.py` 都调用它，
保证三个文件**同一目录、同一主文件名、只差后缀**。

配置文件：skill 根目录下的 `env`（UTF-8）。格式见文件内注释：

    REPORT_OUTPUT_DIR=~/企业研究报告
    REPORT_BASENAME_TEMPLATE={name}-企业信息解读-{date}

规则：
- 值支持 `~`、`$HOME` / `${HOME}`、单双引号；行尾 `#` 注释可用；
- 相对路径以 **skill 根目录** 为基准（不是当前 shell 目录）；
- 中文、空格、全角字符原样保留；
- 文件名里的 Windows 非法字符（`\\ / : * ? " < > |`）替换为 `-`。

命令行（用于脚本/agent 先问「会存到哪」）：

    python3 scripts/report_paths.py --data data.json
    python3 scripts/report_paths.py --data data.json --out-dir /tmp/测试
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / "env"

ENV_KEY = "REPORT_OUTPUT_DIR"
TEMPLATE_KEY = "REPORT_BASENAME_TEMPLATE"
DEFAULT_OUTPUT_DIR = "~/企业研究报告"
DEFAULT_BASENAME_TEMPLATE = "{name}-企业信息解读-{date}"

INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
EXTENSIONS = ("json", "html", "md")


def _strip_inline_comment(value: str) -> str:
    """去掉引号外的行尾注释；保留 `#` 作为普通字符的情况。"""
    out: list[str] = []
    quote = ""
    for i, ch in enumerate(value):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            continue
        if ch == "#" and (i == 0 or value[i - 1].isspace()):
            break
        out.append(ch)
    return "".join(out).strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env(env_file: str | Path | None = None) -> dict[str, str]:
    """读取 env 文件为字典；文件不存在时返回空字典。"""
    path = Path(env_file).expanduser() if env_file else ENV_FILE
    if not path.exists():
        return {}
    # utf-8-sig：用户用 Windows 记事本保存时可能带 BOM
    text = path.read_text(encoding="utf-8-sig")
    env: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path} 第 {lineno} 行不是 KEY=VALUE：{raw!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path} 第 {lineno} 行缺少 KEY：{raw!r}")
        env[key] = _unquote(_strip_inline_comment(value.strip()))
    return env


def resolve_output_dir(raw: str | None) -> Path:
    """把 env 里的路径解析成绝对路径：支持 ~ / 环境变量 / 相对 skill 目录。"""
    value = (raw or "").strip()
    if not value:
        value = DEFAULT_OUTPUT_DIR
    value = os.path.expandvars(os.path.expanduser(value))
    path = Path(value)
    if not path.is_absolute():
        path = SKILL_DIR / path
    return path.resolve()


def load_config(env_file: str | Path | None = None) -> dict[str, Any]:
    """返回输出配置：目录、主文件名模板、env 文件位置。"""
    path = Path(env_file).expanduser() if env_file else ENV_FILE
    env = load_env(path)
    raw_dir = env.get(ENV_KEY, "").strip() or DEFAULT_OUTPUT_DIR
    template = env.get(TEMPLATE_KEY, "").strip() or DEFAULT_BASENAME_TEMPLATE
    return {
        "env_file": path,
        "exists": path.exists(),
        "output_dir": resolve_output_dir(raw_dir),
        "output_dir_raw": raw_dir,
        "basename_template": template,
    }


def safe_component(value: Any, fallback: str = "未命名") -> str:
    """清掉不能进文件名的字符，保留中文与空格；不产生空名。"""
    text = str(value or "").strip()
    text = INVALID_FILENAME.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".")
    return text or fallback


def date_token(meta: dict) -> str:
    """报告日期：优先 report_date，其次 price_at，最后当天；统一成 YYYYMMDD。"""
    for key in ("report_date", "price_at"):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(meta.get(key) or ""))
        if m:
            return "".join(m.groups())
    return datetime.now().strftime("%Y%m%d")


def make_basename(data: dict, template: str | None = None) -> str:
    """按 meta + 模板生成三件套共用的主文件名（不含后缀）。"""
    meta = data.get("meta") or {}
    name = safe_component(meta.get("name"), fallback="个股")
    code = safe_component(meta.get("code"), fallback="")
    date = date_token(meta)
    tpl = (template or DEFAULT_BASENAME_TEMPLATE).strip() or DEFAULT_BASENAME_TEMPLATE
    try:
        base = tpl.format(name=name, code=code, date=date)
    except (KeyError, IndexError, ValueError) as e:
        raise ValueError(
            f"REPORT_BASENAME_TEMPLATE 写法有误：{tpl!r}（{e}）；"
            f"可用占位符只有 {{name}} / {{code}} / {{date}}"
        ) from e
    base = safe_component(base, fallback=f"{name}-企业信息解读-{date}")
    # 极端长文件名在部分文件系统上会失败；给主名留出后缀与路径余量
    return base[:160].rstrip(" .-") or f"{name}-企业信息解读-{date}"


def output_paths(data: dict, *, out_dir: str | Path | None = None,
                 basename: str | None = None,
                 env_file: str | Path | None = None) -> dict[str, Any]:
    """解析出 {dir, basename, json, html, md} 六个值。不创建目录。"""
    if out_dir:
        directory = Path(out_dir).expanduser()
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        directory = directory.resolve()
    else:
        directory = load_config(env_file)["output_dir"]

    base = safe_component(basename) if basename else make_basename(
        data, load_config(env_file)["basename_template"])
    paths: dict[str, Any] = {"dir": directory, "basename": base}
    for ext in EXTENSIONS:
        paths[ext] = directory / f"{base}.{ext}"
    return paths


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="解析报告三件套的保存路径（读 env 配置）")
    ap.add_argument("--data", help="报告数据 JSON（用来取股票名称/代码/日期）")
    ap.add_argument("--out-dir", help="临时覆盖输出目录（相对当前目录）")
    ap.add_argument("--basename", help="临时覆盖主文件名")
    ap.add_argument("--env-file", help="临时指定 env 文件（默认 skill 根目录/env）")
    args = ap.parse_args()

    data: dict = {}
    if args.data:
        p = Path(args.data).expanduser()
        if not p.exists():
            print(f"错误：找不到 {p}", file=sys.stderr)
            return 1
        data = json.loads(p.read_text(encoding="utf-8"))

    try:
        cfg = load_config(args.env_file)
        paths = output_paths(data, out_dir=args.out_dir, basename=args.basename,
                             env_file=args.env_file)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    print(f"env 文件        {cfg['env_file']}（{'存在' if cfg['exists'] else '不存在，使用默认值'}）")
    print(f"输出目录        {paths['dir']}")
    print(f"主文件名        {paths['basename']}")
    for ext in EXTENSIONS:
        print(f"  {ext.upper():<4}          {paths[ext]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
