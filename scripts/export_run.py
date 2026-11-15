"""Export a document test run with its grades, so every grade can be checked against the answer.

The full run reports in logs/ are not committed (they hold traces and page transcriptions). This
script keeps, for each case, the question, the expected answer, the answer as given and the grade
with its reason, and writes them to one Markdown file under evals/.

Usage:
    python scripts/export_run.py logs/documents_runs/run_<stamp>_fast.md \
        --grades evals/documents/runs/run42_grades.toml --out evals/documents/runs/run42.md

The grades file holds one line per case:  TA1 = ["✅", "reason"]
"""

from __future__ import annotations

import argparse
import re
import tomllib
from collections import Counter
from pathlib import Path

GRADES = ("✅", "⚠️", "❌", "pass", "fail")


def parse_report(text: str) -> tuple[list[str], dict[str, dict]]:
    """Header lines and, per case id, question, expected answer and answer."""
    header = [line for line in text.split("\n## ", 1)[0].splitlines()[1:6] if line.strip()]
    cases: dict[str, dict] = {}
    for block in text.split("\n## ")[1:]:
        title = block.splitlines()[0]
        ident = title.split(" — ")[0].strip()
        question = re.search(r"\*\*Question:\*\* (.*)", block)
        expected = re.search(r"\*\*Expected:\*\* (.*)", block)
        answer = re.search(r"### Answer\n\n(.*?)(?:\n### Trace|\Z)", block, re.S)
        cases[ident] = {
            "file": title.split(" — ")[1].strip() if " — " in title else "",
            "question": question.group(1).strip() if question else "",
            "expected": expected.group(1).strip() if expected else "",
            "answer": answer.group(1).strip() if answer else "",
        }
    return header, cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report")
    parser.add_argument("--grades", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="")
    args = parser.parse_args()

    header, cases = parse_report(Path(args.report).read_text(encoding="utf-8"))
    grades = tomllib.loads(Path(args.grades).read_text(encoding="utf-8"))
    missing = [c for c in cases if c not in grades]
    if missing:
        raise SystemExit(f"no grade for: {', '.join(missing)}")
    counts = Counter(grades[c][0] for c in cases)
    title = args.title or Path(args.out).stem
    lines = [f"# {title}", ""] + [line for line in header] + [
        "",
        "Grades: " + ", ".join(f"{g} {counts[g]}" for g in GRADES if counts[g]),
        "",
        "Each answer is printed below as the agent gave it, with the expected answer from the case file and the grade.",
        "",
        "| Case | Grade | Reason |",
        "|---|---|---|",
    ]
    for ident in cases:
        grade, reason = grades[ident]
        lines.append(f"| {ident} | {grade} | {reason.replace('|', '/')} |")
    for ident, case in cases.items():
        grade, reason = grades[ident]
        lines += ["", f"## {ident} — {grade}", "", f"**File:** {case['file']}  ", f"**Question:** {case['question']}  ",
                  f"**Expected:** {case['expected']}  ", f"**Grade:** {grade} {reason}", "", "**Answer:**", ""]
        lines += ["> " + line if line.strip() else ">" for line in case["answer"].splitlines()]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(cases)} cases -> {args.out}")


if __name__ == "__main__":
    main()
