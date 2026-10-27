#!/usr/bin/env python3
"""乱码自检：扫描技能文件里可疑的串（孤立拉丁词、残缺占位符、重复标点）。
用法: python3 lint_encoding.py [目录]
"""
import re
import sys
from pathlib import Path

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
    "message", "false", "true", "consensus", "rating", "stance", "watchlist",
    "scorecard", "redflags", "verdict", "balance", "latest", "business",
    "trends", "sources", "price", "meta", "items", "label", "value", "note",
    "flag", "period", "dim", "weight", "total", "records", "chart", "segments",
    "series", "years", "signals", "name", "result", "reason", "state",
    "evidence", "text", "kind", "level", "threshold", "triggers", "paragraphs",
    "tags", "headline", "summary", "intro", "moat", "policy", "upstream",
    "downstream", "comment", "chart_data", "chart_title", "unit", "range",
    "rev_pct", "margin", "yoy", "pct", "data_search", "data_quote", "data_kline",
    "data_profile", "data_finance", "data_notice", "data_news", "data_sector",
    "data_risk", "data_score", "data_rating", "data_report", "data_dividend",
    "data_shareholder", "data_consensus", "sample", "json", "report",
    "core", "fields", "code", "num", "query", "limit", "fq", "qfq", "period",
    "connector",
}

BAD_CN = re.compile(r"[一-鿿]{2,}")
LATIN = re.compile(r"[A-Za-z]{2,}")


def suspicious(path: Path):
    issues = []
    text = path.read_text(encoding="utf-8")
    in_fence = False
    in_frontmatter = False
    fm_seen = 0
    for i, line in enumerate(text.splitlines(), 1):
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


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    files = [p for p in root.rglob("*.md")]
    total = 0
    for p in sorted(files):
        iss = suspicious(p)
        if iss:
            print(f"\n=== {p}")
            for i, msg, snippet in iss:
                print(f"  L{i}: {msg}  <- {snippet}")
            total += len(iss)
    print(f"\n检查了 {len(files)} 个文件，发现 {total} 处问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
