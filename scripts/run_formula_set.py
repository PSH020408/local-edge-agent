"""Run the formula reading set and grade every reading by code.

Two methods are compared on the same numbered equations:
    page   the whole page goes to the vision model once, asked for equation (n) (the Stage 4 way)
    crop2  the equation is located by its number, read from two crops, and the readings compared

Each final reading is graded against the reference transcription in evals/formulas/cases.toml:
exact (equal after normalisation), close (token similarity >= 0.9) or wrong. For crop2 the report
also shows whether the agreement status (confirmed / close / disagree) predicted the grade.

Usage:
    python scripts/run_formula_set.py                 # both methods
    python scripts/run_formula_set.py --method crop2  # one method
    python scripts/run_formula_set.py --only F07,F16  # selected cases

Reports go to logs/formula_runs/ (not committed).
"""

from __future__ import annotations

import argparse
import sys
import time
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agent.document_tools import load_document, page_image  # noqa: E402
from agent.formula_tools import (  # noqa: E402
    check_structure,
    compare_latex,
    extract_latex,
    find_equation,
    read_equation,
)
from main import build_session, load_config, resolve_profile, select_model  # noqa: E402
from run_eval_set import git_commit  # noqa: E402

PAGE_PROMPT = """This image is a page of a document. Transcribe the equation numbered ({number}) into LaTeX.
Write only that equation between $$ and $$: no equation number, no explanation, no other equation.
Copy every symbol, subscript, superscript, exponent, bar, hat and bold letter exactly as printed."""

GRADE = {"same": "exact", "close": "close", "different": "wrong"}


def grade(latex: str, expected: str) -> tuple[str, float]:
    if not latex.strip():
        return "wrong", 0.0
    verdict, ratio, _ = compare_latex(latex, expected)
    return GRADE[verdict], ratio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--method", choices=["page", "crop2", "both"], default="both")
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--cases", default="evals/formulas/cases.toml")
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    profile = resolve_profile(cfg, "fast")

    class Args:  # select_model reads these attributes
        model, fast = None, True

    model = select_model(cfg, Args(), profile)
    _, _, registry, workspace, vision_config, _ = build_session(
        cfg, model, None, use_planner=False, on_tool_call=lambda *a: None, on_event=lambda m: None,
        interactive=False, profile=profile,
    )
    vision = getattr(registry, "vision", None)
    if vision is None:
        sys.exit("The vision model is not enabled in config.toml.")
    cases = tomllib.loads((ROOT / args.cases).read_text(encoding="utf-8"))["case"]
    if args.only:
        wanted = {c.strip().upper() for c in args.only.split(",")}
        cases = [c for c in cases if c["id"].upper() in wanted]
    methods = ["page", "crop2"] if args.method == "both" else [args.method]
    cache = workspace / "logs" / "cache" / "formulas"
    files = ROOT / "evals" / "documents" / "files"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Vision: {vision_config.model} | Code: {git_commit()} | {len(cases)} formulas | methods: {', '.join(methods)}\n")

    rows: list[dict] = []
    start_all = time.time()
    for n, case in enumerate(cases, 1):
        document = load_document(files / case["file"])
        for method in methods:
            started = time.time()
            row = {"id": case["id"], "method": method, "file": case["file"], "number": case["number"],
                   "lines": case.get("lines", 1), "expected": case["expected"], "status": "", "differences": [], "readings": []}
            if method == "page":
                spot = find_equation(document, case["number"])
                if spot is None:
                    row.update(latex="", status="not_found")
                else:
                    image = page_image(document, spot.page, cache)
                    relative = str(image.resolve().relative_to(workspace.resolve()))
                    result = vision.describe(relative, PAGE_PROMPT.format(number=case["number"]))
                    row["latex"] = extract_latex(result.get("answer", "")) if result.get("status") == "ok" else ""
                    row["status"] = "one reading"
                    row["readings"] = [row["latex"]]
            else:
                reading = read_equation(vision, workspace, document, case["number"], cache)
                row.update(latex=reading.latex, status=reading.status, differences=reading.differences,
                           readings=reading.readings, check=reading.check)
            row["grade"], row["ratio"] = grade(row["latex"], case["expected"])
            row["problems"] = check_structure(row["latex"]) if row["latex"] else ["empty"]
            row["seconds"] = round(time.time() - started, 1)
            rows.append(row)
            print(f"[{n}/{len(cases)}] {case['id']} ({case['number']}) {method:5s} {row['grade']:5s} "
                  f"{row['ratio']:.2f}  {row['status']:12s} {row['seconds']:5.1f} s")
    total = round((time.time() - start_all) / 60, 1)

    out_dir = workspace / "logs" / "formula_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"run_{stamp}.md"
    lines = [f"# Formula set run {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Vision: {vision_config.model} | Code: {git_commit()} | {len(cases)} formulas | {total} min", "",
             "| Method | Exact | Close | Wrong | Mean seconds |", "|---|---|---|---|---|"]
    for method in methods:
        mine = [r for r in rows if r["method"] == method]
        counts = Counter(r["grade"] for r in mine)
        mean = sum(r["seconds"] for r in mine) / max(1, len(mine))
        lines.append(f"| {method} | {counts['exact']} | {counts['close']} | {counts['wrong']} | {mean:.1f} |")
    if "crop2" in methods:
        lines += ["", "Agreement status against the grade (crop2):", "",
                  "| Status | Exact | Close | Wrong |", "|---|---|---|---|"]
        mine = [r for r in rows if r["method"] == "crop2"]
        for status in ("confirmed", "close", "disagree", "check_failed", "unreadable", "not_found"):
            subset = [r for r in mine if r["status"] == status]
            if subset:
                c = Counter(r["grade"] for r in subset)
                lines.append(f"| {status} | {c['exact']} | {c['close']} | {c['wrong']} |")
    lines += ["", "| Case | Eq. | Lines | Method | Grade | Similarity | Status | Seconds |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | ({r['number']}) | {r['lines']} | {r['method']} | {r['grade']} | {r['ratio']:.2f} | {r['status']} | {r['seconds']} |")
    for r in rows:
        lines += ["", f"## {r['id']} ({r['number']}) — {r['method']} — {r['grade']}", "",
                  f"File: {r['file']}", "", "Expected:", "", f"    {r['expected']}", "", "Final:", "", f"    {r['latex']}"]
        if r["method"] == "crop2":
            for i, reading in enumerate(r["readings"], 1):
                lines += ["", f"Reading {i}:", "", f"    {reading}"]
            if r["differences"]:
                lines += ["", "Differences between the readings: " + "; ".join(r["differences"])]
            if r.get("check"):
                lines += ["", "Check against the image: " + r["check"].replace("\n", " ")]
        if r["problems"] and r["problems"] != ["empty"]:
            lines += ["", "Structure problems: " + ", ".join(r["problems"])]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDone: {len(rows)} readings in {total} min\nReport: {report.relative_to(workspace)}")


if __name__ == "__main__":
    main()
