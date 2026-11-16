"""Run a whole test set (vision or documents) in one go and write a report.

Each case gets a fresh conversation (the same as /reset) and goes through the same code path
as main.py: the image planner when it applies, otherwise the agent loop. The report keeps the
full tool results, so every answer can be scored afterwards.

Usage:
    python scripts/run_eval_set.py --set documents --fast   # the document set, fast profile
    python scripts/run_eval_set.py --set vision --fast      # the vision set (also: run_vision_set.py)
    python scripts/run_eval_set.py --set vision --compare   # small, large, small-accurate, large-accurate
    python scripts/run_eval_set.py --profiles small,large   # any list of profiles, with a comparison
    python scripts/run_eval_set.py --fast --only 02,06      # selected cases
    python scripts/run_eval_set.py --fast --no-planner      # the agent loop alone, for comparison

Reports are written to logs/<set>_runs/ (not committed): one per profile, and a comparison
table when more than one profile runs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import LLMError  # noqa: E402
from agent.display import format_event, format_tool_call  # noqa: E402
from main import build_session, describe_setup, load_config, profile_name, resolve_profile, select_model  # noqa: E402

# set name -> (folder with cases.toml, subfolder with the files, field in each case that names the file)
SETS = {
    "vision": ("evals/vision", "images", "image"),
    "documents": ("evals/documents", "files", "file"),
}
DEFAULT_SET = "vision"
# Model size x checking method. The vision model is the same in all four.
COMPARE = ["small", "large", "small-accurate", "large-accurate"]


def matches(answer: str, entry: str) -> bool:
    """One expected entry; alternatives are separated by ' | '."""
    low = answer.lower()
    return any(alt.strip().lower() in low for alt in entry.split(" | ") if alt.strip())


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return (out.stdout.strip() or "unknown") + (" + uncommitted changes" if dirty else "")
    except OSError:
        return "unknown"


def run_profile(cfg: dict, args, name: str | None, cases: list[dict], stamp: str) -> dict:
    folder, subfolder, key = SETS[args.set]
    files = ROOT / folder / subfolder
    """Run every case with one profile; write its report and return a summary for the comparison."""
    profile = resolve_profile(cfg, name)
    model = select_model(cfg, args, profile)
    trace: list[str] = []

    def on_tool_call(tool: str, call_args: dict, result: str) -> None:
        print(format_tool_call(tool, call_args, result))
        trace.append(f"-> {tool}({call_args})\n{result}")

    def on_event(message: str) -> None:
        print(format_event(message))
        trace.append(f"⚙ {message}")

    agent, planner, _, _, vision_config, planner_model = build_session(
        cfg, model, args.planner_model, use_planner=not args.no_planner,
        on_tool_call=on_tool_call, on_event=on_event, interactive=False, profile=profile,
    )
    setup = describe_setup(model, vision_config, planner, planner_model, profile) + f" | Code: {git_commit()}"
    print(f"\033[1m{setup}\033[0m\n")

    rows, details, results = [], [], {}
    started = time.perf_counter()
    for number, case in enumerate(cases, 1):
        image = files / case[key]
        question = f"{folder}/{subfolder}/{case[key]} {case['question']}"
        print(f"\033[1m[{number}/{len(cases)}] {case['id']}\033[0m {case['question']}")
        trace.clear()
        agent.reset()
        start = time.perf_counter()
        if not image.is_file():
            answer, status = f"[skipped: {image.name} is missing]", "skipped"
        else:
            try:
                answer = planner.run(question) if planner else None
                if answer is None:
                    answer = agent.run(question)
                status = "ok"
            except LLMError as exc:
                answer, status = f"[error: {exc}]", "error"
        seconds = time.perf_counter() - start
        expect = case.get("expect", [])
        hits = [e for e in expect if matches(answer, e)]
        bad = [a for a in case.get("avoid", []) if a.lower() in answer.lower()]
        warned = answer.count("⚠")
        print(f"agent> {answer}\n  ({seconds:.1f} s, key facts {len(hits)}/{len(expect)}"
              + (f", flagged: {', '.join(bad)}" if bad else "") + ")\n")
        results[case["id"]] = {"seconds": seconds, "hits": len(hits), "total": len(expect), "bad": bad,
                               "warned": warned, "status": status}

        missing = [e for e in expect if e not in hits]
        rows.append(f"| {case['id']} | {seconds:.1f} | {len(hits)}/{len(expect)} | {', '.join(bad) or '-'} | {warned} | {status} |")
        details.append("\n".join([
            f"## {case['id']} — {case[key]}",
            "",
            f"**Question:** {case['question']}",
            "",
            f"**Expected:** {case.get('note', '')}" + (f" (pages {', '.join(map(str, case['pages']))})" if case.get("pages") else ""),
            "",
            f"**Key facts missing:** {', '.join(missing) or '-'}  ",
            f"**Flagged:** {', '.join(bad) or '-'}  ",
            f"**Warnings in the answer (⚠):** {warned}  ",
            f"**Time:** {seconds:.1f} s",
            "",
            "### Answer",
            "",
            answer,
            "",
            "### Trace",
            "",
            "```text",
            "\n\n".join(trace),
            "```",
            "",
        ]))

    total = time.perf_counter() - started
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = profile.get("name", "default")
    path = out_dir / f"run_{stamp}_{label}.md"
    report = [
        f"# {args.set.capitalize()} set run {datetime.now():%Y-%m-%d %H:%M} — {label}",
        "",
        setup,
        "",
        f"Cases: {len(cases)} | Total: {total / 60:.1f} min",
        "",
        "Key facts are a quick indicator only; score each answer by reading it.",
        "",
        "| Case | Seconds | Key facts | Flagged | ⚠ in answer | Status |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        *details,
    ]
    path.write_text("\n".join(report), encoding="utf-8")
    print(f"Done: {len(cases)} cases in {total / 60:.1f} min")
    print(f"Report: {path.relative_to(ROOT)}\n")
    return {"name": label, "setup": setup, "minutes": total / 60, "results": results, "path": path}


def write_comparison(runs: list[dict], cases: list[dict], stamp: str, out: Path, set_name: str = "vision") -> Path:
    header = "| Case | " + " | ".join(r["name"] for r in runs) + " |"
    lines = [
        f"# {set_name.capitalize()} set comparison {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Each cell: key facts found / expected, ⚠ warnings in the answer, seconds. A flagged hallucination is marked 👻.",
        "Key facts are an indicator only; the answers are scored by reading the per-profile reports.",
        "",
        *[f"- **{r['name']}**: {r['setup']} ({r['minutes']:.1f} min) — `{r['path'].name}`" for r in runs],
        "",
        header,
        "|---|" + "---|" * len(runs),
    ]
    for case in cases:
        cells = []
        for r in runs:
            x = r["results"].get(case["id"])
            if not x:
                cells.append("-")
                continue
            cell = f"{x['hits']}/{x['total']}, ⚠{x['warned']}, {x['seconds']:.0f} s"
            cells.append(cell + (" 👻" if x["bad"] else ""))
        lines.append(f"| {case['id']} | " + " | ".join(cells) + " |")
    totals = []
    for r in runs:
        hits = sum(x["hits"] for x in r["results"].values())
        total = sum(x["total"] for x in r["results"].values())
        ghosts = sum(1 for x in r["results"].values() if x["bad"])
        totals.append(f"{hits}/{total}, 👻{ghosts}, {r['minutes']:.0f} min")
    lines.append("| **Total** | " + " | ".join(totals) + " |")
    path = out / f"compare_{stamp}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a test set")
    parser.add_argument("--set", choices=sorted(SETS), default=DEFAULT_SET, help="which test set")
    parser.add_argument("--config", default=str(ROOT / "config.toml"))
    parser.add_argument("--cases", help="cases.toml to use instead of the set's own")
    parser.add_argument("--model", help="override the main model")
    parser.add_argument("--fast", action="store_true", help="profile 'fast' from config.toml")
    parser.add_argument("--accurate", action="store_true", help="profile 'accurate' from config.toml")
    parser.add_argument("--profile", help="any profile name from config.toml")
    parser.add_argument("--profiles", help="several profiles in a row, e.g. small,large; writes a comparison")
    parser.add_argument("--compare", action="store_true", help="the four profiles: " + ", ".join(COMPARE))
    parser.add_argument("--planner-model", help="override the model that plans image questions")
    parser.add_argument("--no-planner", action="store_true", help="send every question to the agent loop")
    parser.add_argument("--only", help="comma-separated case ids, e.g. 02,06,H3")
    parser.add_argument("--out", help="report folder (default logs/<set>_runs)")
    parser.add_argument("--no-speed-check", action="store_true", help="skip the speed check before the run")
    parser.add_argument("--force", action="store_true", help="run even if the speed check finds the Mac much slower than normal")
    args = parser.parse_args()
    args.cases = args.cases or str(ROOT / SETS[args.set][0] / "cases.toml")
    args.out = args.out or str(ROOT / "logs" / f"{args.set}_runs")

    cfg = load_config(Path(args.config))
    with open(args.cases, "rb") as f:
        cases = tomllib.load(f)["case"]
    if args.only:
        wanted = {c.strip().upper() for c in args.only.split(",")}
        cases = [c for c in cases if c["id"].upper() in wanted]

    names = COMPARE if args.compare else [n.strip() for n in args.profiles.split(",")] if args.profiles else [profile_name(args)]
    for name in names:
        resolve_profile(cfg, name)  # fail before hours of running, not in the middle
    if not args.no_speed_check:
        # Stage 7: Run 45 lost hours to a GPU held at its lowest clocks; a few seconds of checking first.
        from agent.device.speed_check import before_long_run
        checked = before_long_run(cfg["llm"]["host"])
        print(f"Speed check: {checked.message}")
        if checked.verdict == "much slower" and not args.force:
            sys.exit("Stopped before the run. Fix the cause above (or restart the Mac), or run again with --force.")
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    runs = [run_profile(cfg, args, name, cases, stamp) for name in names]
    if len(runs) > 1:
        path = write_comparison(runs, cases, stamp, Path(args.out), args.set)
        print(f"Comparison: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
