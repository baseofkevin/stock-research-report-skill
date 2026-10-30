#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码自检：扫描技能文件与**已生成的报告**里的可疑串（孤立拉丁词、残缺占位符、重复标点）。

用法:
    python3 lint_encoding.py                      # 默认扫当前目录（递归）
    python3 lint_encoding.py SKILL.md references/  # 文件或目录都可以，混着传也行
    python3 lint_encoding.py 报告.html 报告.md     # 交付前把产物也扫一遍

支持 .md / .html / .json。HTML 先剥标签、JSON 只抽含中文的字符串值，
避免把源码和属性名当成乱码。

**两级判定**（这个脚本抓的不是真 mojibake，而是「中文里混进无法解释的拉丁串」）：

- `[error]` 全小写/怪拼的拉丁串 —— 大概率是乱码或编码截断，必须改。
- `[warn]`  CamelCase / 首字母大写单词 —— 大概率是品牌名、产品代号、字段名，
  人工看一眼即可；`ALLOW` 与 `allow_words.txt` 里的词直接放过。

**白名单分三处，都不需要改代码**：
1. 代码里的 `BUILTIN_ALLOW`：JSON 键、工具名、协议词、CSS 属性等结构性词汇；
2. `scripts/allow_words.txt`：公司/行业专名（一行一词，`#` 后是注释）——
   每换一家公司只需往这个文件加词；
3. 行内豁免：`<!-- lint-allow: SmartVitals, OmniScan -->`（只对该行生效），
   或 `<!-- lint-allow-file: 飞利浦 -->`（对整个文件生效）。

退出码: 0 = 无 error（warn 不算失败），1 = 有 error。
"""
import html as _html
import json
import re
import sys
from pathlib import Path

EXTS = {".md", ".html", ".json"}
ALLOW_FILE = Path(__file__).resolve().parent / "allow_words.txt"

# 结构性词汇：JSON 键、工具名、协议词、CSS 属性、枚举值。
# 行业/品牌/公司专名**不要**加在这里，放 allow_words.txt。
BUILTIN_ALLOW = {
    "pe", "pb", "ps", "peg", "roe", "roa", "roic", "wacc", "eps", "ev", "ebit",
    "ma", "macd", "kdj", "rsi", "boll", "ttm", "fcf", "ocf", "np", "gm", "rev",
    "a", "b", "e", "g", "k", "gg", "html", "css", "json", "api", "url", "svg",
    "mcp", "python", "skill", "readme", "note", "size", "level", "text",
    "true", "false", "null", "name", "value", "label", "yoy", "id", "code",
    "income", "balance", "cashflow", "financials", "scorecard", "watchlist",
    "valuation", "moat", "business", "infopubldate", "enddate", "series",
    "westock", "websearch", "webfetch", "variables", "charset", "utf", "lang", "type", "meta", "data",
    "points", "paths", "polygon", "polyline", "rect", "circle", "span", "div",
    "none", "solid", "flex", "grid", "rgb", "rgba", "px", "em", "rem", "pt",
    "sans", "serif", "linear", "gradient", "box", "shadow", "margin", "stroke",
    "fill", "width", "height", "color", "gap", "border", "radius", "padding",
    "message", "consensus", "rating", "stance", "redflags", "verdict", "latest",
    "trends", "sources", "price", "items", "flag", "period", "dim",
    "weight", "total", "records", "chart", "segments", "years", "charts",
    "signals", "result", "reason", "state", "evidence", "kind", "threshold",
    "triggers", "paragraphs", "tags", "headline", "summary", "intro",
    "policy", "upstream", "downstream", "comment", "chart_data", "chart_title",
    "unit", "range", "rev_pct", "margin", "pct", "data_search", "data_quote",
    "data_kline", "data_profile", "data_finance", "data_notice", "data_news",
    "data_sector", "data_risk", "data_score", "data_rating", "data_report",
    "data_dividend", "data_shareholder", "data_consensus", "data_disclosure",
    "data_finsearch", "sample", "report", "redflags_note", "current",
    "ocf_ttm", "np_ttm", "pe_ttm", "pe_lyr", "pe_fwd",
    "markdown", "core", "fields", "num", "query", "limit", "fq", "qfq",
    "connector", "schema", "version", "validate", "strict", "evals", "golden",
    "gross", "net", "op", "cagr", "ipo", "ai", "ar", "vr", "odm", "oem",
    "sku", "spu", "cpi", "ppi", "gdp", "sec", "csi", "hq", "cn", "us", "hk",
    "rmb", "dt", "php", "js", "ts", "py", "sh", "sz", "bj",
    # 数据源 / 接口术语
    "rpt", "f10", "finance", "lico", "valueanalysis", "qyresearch", "ebitda",
    "streamable", "http", "https", "oauth", "jsonrpc", "sse", "bearer",
    "workbuddy", "token", "agent", "hkdf", "sha256",
    "aes", "gcm", "base64", "node", "ide", "dsh", "git", "cli",
    # 运行时技术名词（CHANGELOG 里会提到，不能算乱码）
    "undici", "llhttp", "wasm", "exit", "exitcode", "camelcase", "titlecase",
    # 文档里描述脚本行为时必然出现的词
    "else", "periods", "stderr", "stdout", "pass", "warn", "fail", "lint",
    "cases", "expect", "validation", "labels", "state_text",
    "data_gaps", "price_at", "schema_version", "v1", "v2", "md",
    # 接口字段名（出现在数据口径说明里）
    "grossincomeratio", "shareholdernum", "interestbeardebt", "institutioncnt",
}

# 行内 / 文件级豁免标记：<!-- lint-allow: A, B --> / <!-- lint-allow-file: C -->
MARK_LINE = re.compile(r"lint-allow\s*:\s*([^>\n]*)")
MARK_FILE = re.compile(r"lint-allow-file\s*:\s*([^>\n]*)")
# 整条注释（含 <!-- -->）：判乱码前要先把标记本身抹掉，否则 "allow" 会被当可疑串
MARK_COMMENT = re.compile(r"<!--\s*lint-allow(?:-file)?\s*:[^>]*?-->")
SPLIT_WORDS = re.compile(r"[,，、;；\s]+")

# 首字母大写 + 内部大写（SmartVitals / OmniScan / iPhone）
CAMEL = re.compile(r"[A-Z][A-Za-z0-9]*(?:[A-Z][a-z0-9]+)+")
# 单个首字母大写的词（Sephora / Philips）
TITLECASE = re.compile(r"[A-Z][a-z]{2,}")

BAD_CN = re.compile(r"[一-鿿]{2,}")
LATIN = re.compile(r"[A-Za-z][A-Za-z_]*(?:_[A-Za-z]+)*")
TAG = re.compile(r"<[^>]+>")


def load_allow_words() -> set[str]:
    """读 allow_words.txt：一行一词，`#` 之后是注释。"""
    try:
        raw = ALLOW_FILE.read_text(encoding="utf-8")
    except OSError:
        return set()
    out = set()
    for line in raw.splitlines():
        w = line.split("#", 1)[0].strip().lower()
        if w:
            out.add(w)
    return out


ALLOW = BUILTIN_ALLOW | load_allow_words()


def _lines(path: Path):
    """把文件变成 (行号, 待检查文本, 原始行) 序列，按格式做预处理。

    原始行用来读行内豁免标记（HTML 剥标签会把注释一起剥掉）。
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    if ext == ".json":
        try:
            data = json.loads(raw)
        except Exception:                                     # noqa: BLE001
            return [(1, raw, raw)]                            # 解析失败就整篇扫
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
        return [(i + 1, s, s) for i, s in enumerate(out)]

    if ext == ".html":
        # 先去掉 <style>/<script>（CSS 注释与 JS 会被当成重复字符/乱码），
        # 再还原实体、剥标签
        stripped = re.sub(r"<(style|script)\b.*?</\1>", "", raw, flags=re.S | re.I)
        stripped = TAG.sub(" ", _html.unescape(stripped))
        raw_lines = raw.splitlines()
        lines = stripped.splitlines()
        if len(raw_lines) != len(lines):
            raw_lines = []          # 行号对不上就放弃豁免标记，宁严不宽
        return [((i, line, raw_lines[i - 1] if raw_lines else line))
                for i, line in enumerate(lines, 1)]
    lines = raw.splitlines()
    return [(i, line, line) for i, line in enumerate(lines, 1)]


def _strip_code(line: str, in_code: bool):
    """剔除行内代码片段；代码块可能跨行（`metrics[...]` 折到下一行），要带状态。"""
    out, i = [], 0
    while i < len(line):
        if line[i] == "`":
            j = line.find("`", i + 1)
            if j < 0:
                in_code = not in_code
                break
            i = j + 1
            continue
        if not in_code:
            out.append(line[i])
        i += 1
    return "".join(out), in_code


def _allow_from(text: str) -> set[str]:
    return {w.strip().lower() for w in SPLIT_WORDS.split(text or "") if w.strip()}


def _classify(word: str, allow: set[str]) -> str | None:
    """None = 放过；'warn' = 可能是品牌/产品名；'error' = 可疑串。"""
    low = word.lower()
    if low in allow:
        return None
    if CAMEL.fullmatch(word) or TITLECASE.fullmatch(word):
        return "warn"
    return "error"


def suspicious(path: Path):
    """返回 [(行号, 'error'|'warn', 说明, 片段)]。"""
    issues = []
    in_fence = False
    in_code = False
    in_frontmatter = False
    fm_seen = 0
    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw_text = ""
    mfile = MARK_FILE.search(raw_text)
    file_allow = _allow_from(mfile.group(1)) if mfile else set()
    for i, line, raw_line in _lines(path):
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
        is_table = line.lstrip().startswith("|")
        # 行内豁免：<!-- lint-allow: A, B -->（只对本行生效）
        marker = MARK_LINE.search(raw_line or "")
        line_allow = _allow_from(marker.group(1)) if marker else set()
        allow = ALLOW | file_allow | line_allow
        line = MARK_COMMENT.sub(" ", line)      # 标记本身不参与判乱码
        # 跳过纯英文名单行；表格行仍查占位符/重复字符，但不做「中文夹拉丁串」判断
        # （表格里 name/tagline/values 这类 JSON 键是正常内容，不是乱码）。
        # 1. 中文行里夹着孤立的拉丁串（>=4 字母且不在白名单）
        #    先剔掉反引号内的代码片段，避免把工具名误判为乱码
        probe, in_code = _strip_code(line, in_code)
        if BAD_CN.search(probe) and not is_table:
            for m in LATIN.finditer(probe):
                w = m.group()
                # 全大写 + 下划线的接口名/枚举（RPT_F10_FINANCE_G）不是乱码，跳过
                if w.isupper() and len(w) >= 3:
                    continue
                # snake_case 标识符（fcf_margin / schema_version）是代码不是乱码
                if "_" in w and re.fullmatch(r"[a-z0-9_]+", w):
                    continue
                if len(w) >= 4:
                    level = _classify(w, allow)
                    if level:
                        issues.append((i, level, f"可疑拉丁串 {w!r}", line.strip()[:60]))
        # 2. 占位符没填完
        for pat in (r"XXXX", r"\{\{", r"TODO"):
            if re.search(pat, line):
                issues.append((i, "error", f"未完成的占位符 {pat}", line.strip()[:60]))
        # 3. 连续重复的非空白、非字母数字字符（>=4 次），如「！！！！」
        #    行首的 markdown 标题井号不算（#### 是合法语法）
        body = re.sub(r"^#{1,6}\s", "", line)
        for m in re.finditer(r"([^\w\s])\1{3,}", body):
            issues.append((i, "error", f"重复字符 {m.group()!r}", line.strip()[:60]))
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
    n_err = n_warn = 0
    for p in files:
        iss = suspicious(p)
        if not iss:
            continue
        print(f"\n=== {p}")
        for i, level, msg, snippet in iss:
            print(f"  L{i}: [{level}] {msg}  <- {snippet}")
            if level == "error":
                n_err += 1
            else:
                n_warn += 1
    print(f"\n检查了 {len(files)} 个文件（.md/.html/.json），"
          f"{n_err} 个错误、{n_warn} 个提醒。")
    if n_err:
        print("提示：品牌名/产品代号可写进 `scripts/allow_words.txt`，"
              "或在该行加 `<!-- lint-allow: 词 -->` 豁免。", file=sys.stderr)
    if not files:
        print("提示：没有匹配到文件——确认传的是目录或 .md/.html/.json 文件。", file=sys.stderr)
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
