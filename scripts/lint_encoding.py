#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""乱码自检：扫描技能文件与**已生成的报告**里可疑的串（孤立拉丁词、残缺占位符、重复标点）。

用法:
    python3 lint_encoding.py                      # 默认扫当前目录（递归）
    python3 lint_encoding.py SKILL.md references/  # 文件或目录都可以，混着传也行
    python3 lint_encoding.py 报告.html 报告.md     # 交付前把产物也扫一遍

支持 .md / .html / .json。HTML 先剥标签、JSON 只抽含中文的字符串值，
避免把源码和属性名当成乱码。
"""
import html as _html
import json
import re
import sys
from pathlib import Path

EXTS = {".md", ".html", ".json"}

# 允许出现的英文技术词/缩写
ALLOW = {
    "pe", "pb", "ps", "peg", "roe", "roa", "roic", "wacc", "eps", "ev", "ebit",
    "ma", "macd", "kdj", "rsi", "boll", "ttm", "fcf", "ocf", "np", "gm", "rev",
    "a", "b", "e", "g", "k", "gg", "html", "css", "json", "api", "url", "svg",
    "mcp", "python", "skill", "readme", "note", "size", "level", "text",
    "true", "false", "null", "name", "value", "label", "yoy", "id", "code",
    "income", "balance", "cashflow", "financials", "scorecard", "watchlist",
    "westock", "variables", "charset", "utf", "lang", "type", "meta", "data",
    "points", "paths", "polygon", "polyline", "rect", "circle", "span", "div",
    "none", "solid", "flex", "grid", "rgb", "rgba", "px", "em", "rem", "pt",
    "sans", "serif", "linear", "gradient", "box", "shadow", "margin", "stroke",
    "fill", "width", "height", "color", "gap", "border", "radius", "padding",
    "message", "consensus", "rating", "stance", "redflags", "verdict", "latest",
    "business", "trends", "sources", "price", "items", "flag", "period", "dim",
    "weight", "total", "records", "chart", "segments", "series", "years",
    "signals", "result", "reason", "state", "evidence", "kind", "threshold",
    "triggers", "paragraphs", "tags", "headline", "summary", "intro", "moat",
    "policy", "upstream", "downstream", "comment", "chart_data", "chart_title",
    "unit", "range", "rev_pct", "margin", "pct", "data_search", "data_quote",
    "data_kline", "data_profile", "data_finance", "data_notice", "data_news",
    "data_sector", "data_risk", "data_score", "data_rating", "data_report",
    "data_dividend", "data_shareholder", "data_consensus", "sample", "report",
    "markdown", "core", "fields", "num", "query", "limit", "fq", "qfq",
    "connector", "schema", "version", "validate", "strict", "evals", "golden",
    "gross", "net", "op", "cagr", "ipo", "ai", "ar", "vr", "odm", "oem",
    "sku", "spu", "cpi", "ppi", "gdp", "sec", "csi", "hq", "cn", "us", "hk",
    "rmb", "dt", "php", "js", "ts", "py", "sh", "sz", "bj",
    # 报告正文里合法出现的外部名词 / 接口名（避免误报）
    "charts", "rpt", "f10", "finance", "lico", "valueanalysis", "qyresearch",
    "frost", "sullivan", "euromonitor", "gfk", "ipsos", "bloomberg",
    # 文档里描述脚本行为时必然出现的词
    "else", "periods", "stderr", "stdout", "pass", "warn", "fail", "lint",
    "cases", "expect", "validation", "label", "labels", "state_text",
    "data_gaps", "price_at", "schema_version", "v1", "v2", "html", "md",
}

BAD_CN = re.compile(r"[一-鿿]{2,}")
LATIN = re.compile(r"[A-Za-z]{2,}")
TAG = re.compile(r"<[^>]+>")


def _lines(path: Path):
    """把文件变成 (行号, 待检查文本) 序列，按格式做预处理。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    if ext == ".json":
        try:
            data = json.loads(raw)
        except Exception:                                     # noqa: BLE001
            return [(1, raw)]                                # 解析失败就整篇扫
        out = []

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, str) and BAD_CN.search(node):
                out.append(node)
        walk(data)
        return [(i + 1, s) for i, s in enumerate(out)]

    if ext == ".html":
        # 先去掉 <style>/<script>（CSS 注释与 JS 会被当成重复字符/乱码），
        # 再还原实体、剥标签
        raw = re.sub(r"<(style|script)\b.*?</\1>", "", raw, flags=re.S | re.I)
        raw = TAG.sub("", _html.unescape(raw))
    lines = raw.splitlines()
    return list(enumerate(lines, 1))


def suspicious(path: Path):
    issues = []
    in_fence = False
    in_frontmatter = False
    fm_seen = 0
    for i, line in _lines(path):
        # 跳过 YAML frontmatter（文件开头的 --- 到 ---）
        if i <= 6 and line.strip() == "---":
            fm_seen += 1
            in_frontmatter = fm_seen == 1
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            continue
        # 跳过代码块，避免把源码本身当成问题
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # 跳过表格行与纯英文名单行
        if line.lstrip().startswith("|") or line.lstrip().startswith("ALLOW"):
            continue
        # 1. 中文行里夹着孤立的拉丁串（>=4 字母且不在白名单）
        #    先剔掉反引号内的代码片段，避免把工具名误判为乱码
        probe = re.sub(r"`[^`]*`", "", line)
        if BAD_CN.search(probe):
            for m in LATIN.finditer(probe):
                w = m.group()
                if len(w) >= 4 and w.lower() not in ALLOW:
                    issues.append((i, f"可疑拉丁串 {w!r}", line.strip()[:60]))
        # 2. 占位符没填完
        for pat in (r"XXXX", r"\{\{", r"TODO"):
            if re.search(pat, line):
                issues.append((i, f"未完成的占位符 {pat}", line.strip()[:60]))
        # 3. 连续重复的非空白、非字母数字字符（>=4 次），如「！！！！」
        for m in re.finditer(r"([^\w\s])\1{3,}", line):
            issues.append((i, f"重复字符 {m.group()!r}", line.strip()[:60]))
    return issues


def collect(args: list) -> list:
    files = []
    for a in args or ["."]:
        p = Path(a).expanduser()
        if not p.exists():
            print(f"[warn] 路径不存在：{p}", file=sys.stderr)
            continue
        if p.is_file():
            if p.suffix.lower() in EXTS:
                files.append(p)
            else:
                print(f"[warn] 跳过不支持的扩展名：{p.name}", file=sys.stderr)
        else:
            files += [q for q in sorted(p.rglob("*")) if q.suffix.lower() in EXTS]
    return files


def main() -> int:
    files = collect(sys.argv[1:])
    total = 0
    for p in files:
        iss = suspicious(p)
        if iss:
            print(f"\n=== {p}")
            for i, msg, snippet in iss:
                print(f"  L{i}: {msg}  <- {snippet}")
            total += len(iss)
    print(f"\n检查了 {len(files)} 个文件（.md/.html/.json），发现 {total} 处可疑。")
    if not files:
        print("提示：没有匹配到文件——确认传的是目录或 .md/.html/.json 文件。", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
