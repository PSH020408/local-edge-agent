"""Experiment Q1: the model chosen per question against each model alone, on general questions with known answers.

    python scripts/run_model_choice.py                     # light, heavy, auto (about 15-25 minutes)
    python scripts/run_model_choice.py --modes auto        # one mode
    python scripts/run_model_choice.py --only H5,K2

Modes: light = qwen3:8b for every question, heavy = qwen3:14b for every question, auto = agent/model_choice.py
(light, heavy when the question looks hard or the light model did not finish). Each answer is graded by code
against evals/general/cases.toml; the report gives right answers and time per mode, and for auto which model
answered and how often it escalated. Report: evals/general/runs/q1_<time>.md.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.model_choice import assess  # noqa: E402
from main import build_chooser, build_session, load_config  # noqa: E402

NUM = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[float]:
    out = []
    for m in NUM.findall(text):
        try:
            out.append(float(m.replace(",", "").replace("−", "-")))
        except ValueError:
            pass
    return out


def grade(answer: str, case: dict) -> bool:
    found = numbers(answer)
    for e in case.get("expected", []):
        tol = max(0.05, 0.01 * abs(e))
        if not any(abs(x - e) <= tol for x in found):
            return False
    if case.get("contains") and not any(s.lower() in answer.lower() for s in case["contains"]):
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--cases", default=str(ROOT / "evals" / "general" / "cases.toml"))
    ap.add_argument("--modes", default="light,heavy,auto")
    ap.add_argument("--only", help="case ids, e.g. H5,K2")
    args = ap.parse_args()
    cfg = load_config(Path(args.config))
    cases = tomllib.loads(Path(args.cases).read_text(encoding="utf-8"))["case"]
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    light, heavy = cfg["llm"]["fast_model"], cfg["llm"]["model"]
    quiet = lambda *a, **k: None  # noqa: E731
    results: dict[str, list[dict]] = {}
    for mode in args.modes.split(","):
        model = heavy if mode == "heavy" else light
        agent, *_ = build_session(cfg, model, use_planner=False, on_tool_call=quiet, on_event=quiet, interactive=False)
        chooser = build_chooser(cfg, agent, heavy, on_event=quiet) if mode == "auto" else None
        rows = []
        print(f"\n== {mode} ({model}{' / ' + heavy if chooser else ''})")
        for c in cases:
            agent.reset()
            start = time.monotonic()
            try:
                answer = chooser.run(c["question"]) if chooser else agent.run(c["question"])
            except Exception as exc:  # noqa: BLE001 - a failed call is a wrong answer, the run goes on
                answer = f"[error: {exc}]"
            seconds = time.monotonic() - start
            used = chooser.last.model if chooser and chooser.last else model
            escalated = bool(chooser and chooser.last and chooser.last.escalated)
            kept = bool(chooser and chooser.last and chooser.last.kept_loaded)
            ok = grade(answer, c)
            rows.append({"id": c["id"], "ok": ok, "seconds": round(seconds, 1), "model": used, "escalated": escalated, "kept": kept,
                         "answer": answer.strip()})
            print(f"  {c['id']:3} {'right' if ok else 'WRONG':5} {seconds:5.1f} s  {used}{'  (escalated)' if escalated else ''}{'  (kept loaded)' if kept else ''}")
        results[mode] = rows

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = [f"# Q1: model per question ({stamp})", "", f"Light {light}, heavy {heavy}; {len(cases)} questions.", "",
             "| Mode | Right | Total time | Median per question | Answered by the heavy model | Escalations | Kept on the loaded heavy model |", "|---|---|---|---|---|---|---|"]
    for mode, rows in results.items():
        heavy_share = sum(r["model"] == heavy for r in rows)
        lines.append(f"| {mode} | {sum(r['ok'] for r in rows)} of {len(rows)} | {sum(r['seconds'] for r in rows):.0f} s | "
                     f"{statistics.median(r['seconds'] for r in rows):.1f} s | {heavy_share} | {sum(r['escalated'] for r in rows)} | {sum(r.get('kept', False) for r in rows)} |")
    lines += ["", "| Case | Judged | " + " | ".join(results) + " |", "|---|---|" + "---|" * len(results)]
    for i, c in enumerate(cases):
        cells = [f"{'right' if results[m][i]['ok'] else 'wrong'}, {results[m][i]['seconds']} s" for m in results]
        lines.append(f"| {c['id']} | {assess(c['question']).level} | " + " | ".join(cells) + " |")
    lines += ["", "## Answers", ""]
    for i, c in enumerate(cases):
        lines += [f"### {c['id']}: {c['question']}", ""]
        for m in results:
            r = results[m][i]
            lines += [f"- **{m}** ({r['model']}, {'right' if r['ok'] else 'wrong'}): {r['answer'][:400]}"]
        lines.append("")
    out = ROOT / "evals" / "general" / "runs" / f"q1_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
