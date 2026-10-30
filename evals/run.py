#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：对 evals/cases/ 下每个样例跑 validate + 两个渲染器，按 cases.json 断言；
最后再跑一遍 scripts/check_docs.py（文档里的数字/工具名/字段名/章节号与代码对账）。

用法:
    python3 evals/run.py            # 全跑
    python3 evals/run.py -v         # 打印每个用例的渲染耗时与告警

改完脚本先跑这个，全绿再提交——它覆盖的正是「静默降级」那类不报错但产出错的毛病。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent
SCRIPTS = SKILL / "scripts"


def run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    verbose = "-v" in sys.argv
    man = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    failed = 0
    for case in man["cases"]:
        path = ROOT / case["file"]
        name = path.name
        problems: list[str] = []

        rc, out, err = run([sys.executable, str(SCRIPTS / "validate.py"), str(path)])
        if case.get("expect_valid"):
            if rc != 0:
                problems.append(f"validate 应通过，实际退出码 {rc}")
        else:
            if rc == 0:
                problems.append("validate 应失败，实际通过")
        for needle in case.get("expect_error_contains") or []:
            if needle not in out:
                problems.append(f"校验输出缺少关键信息：{needle!r}")
        if case.get("allow_only_warns") and "[错误]" in out:
            problems.append("v1 用例只应产生警告，不应有错误")

        with tempfile.TemporaryDirectory() as td:
            html = Path(td) / "r.html"
            md = Path(td) / "r.md"
            rc1, o1, e1 = run([sys.executable, str(SCRIPTS / "render_report.py"), str(path), "-o", str(html)])
            rc2, o2, e2 = run([sys.executable, str(SCRIPTS / "render_md.py"), str(path), "-o", str(md)])
            if rc1 != 0 or not html.exists():
                problems.append(f"HTML 渲染失败 rc={rc1} {e1[:200]}")
            if rc2 != 0 or not md.exists():
                problems.append(f"MD 渲染失败 rc={rc2} {e2[:200]}")
            body_md = md.read_text(encoding="utf-8") if md.exists() else ""
            body_html = html.read_text(encoding="utf-8") if html.exists() else ""
            for needle in case.get("must_contain") or []:
                if needle not in body_md or needle not in body_html:
                    where = []
                    if needle not in body_md:
                        where.append("md")
                    if needle not in body_html:
                        where.append("html")
                    problems.append(f"产物缺少关键串 {needle!r}（{'+'.join(where)}）")
            if case.get("expect_stance"):
                if case["expect_stance"] not in body_html:
                    problems.append(f"HTML 未渲染出 stance {case['expect_stance']!r}")
            # 节编号必须从「一」开始连续，不能跳号/重号
            seq = re.findall(r"<h2>([一二三四五六七八九十])、", body_html)
            expected = list("一二三四五六七八九十")[:len(seq)]
            if seq != expected:
                problems.append(f"HTML 节编号不连续：{''.join(seq)}（应为 {''.join(expected)}）")
            # 编码/乱码检查也要进 CI；golden sample 不能自己过不了 lint
            if html.exists() and md.exists():
                rcl, ol, el = run([sys.executable, str(SCRIPTS / "lint_encoding.py"),
                                   str(html), str(md)])
                if rcl != 0:
                    problems.append(f"lint_encoding 未通过：{(ol + el).strip()[-300:]}")
            if verbose:
                if e1.strip() or e2.strip():
                    print(f"  · {name} 渲染告警：{(e1 + e2).strip()[:300]}")

        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {name} — {case['desc']}")
        for p in problems:
            print(f"        ! {p}")
        failed += bool(problems)

    print(f"\n{len(man['cases']) - failed}/{len(man['cases'])} 个用例通过")

    # ---- 文档交叉引用检查（改文档忘了改代码，是这类 skill 最常见的错） ----
    rc, out, err = run([sys.executable, str(SCRIPTS / "check_docs.py")])
    tail = [l for l in (out or "").splitlines() if l.strip()][-1:] or [err[:200]]
    print(f"[{'PASS' if rc == 0 else 'FAIL'}] 文档交叉引用 — {tail[0]}")
    if rc != 0:
        for line in out.splitlines():
            if line.startswith("[错误]"):
                print(f"        ! {line[len('[错误] '):]}")
        failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
