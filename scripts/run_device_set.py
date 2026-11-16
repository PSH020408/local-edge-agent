"""Runs the Stage 7 device test set and writes a report.

Each case is a question, a device state (a scenario built from recorded outputs, or the Mac as it is)
and the expected route and findings. The report lists, per case: the route, the findings against the
expectation, the strings expected in the answer, numbers in the answer that are not in the facts,
whether the model or the code template wrote the answer, and the time of each stage. It also keeps
the facts, the findings and, for live cases, the readings the answer was based on, so every answer
can be graded by hand.

Usage:
    python scripts/run_device_set.py                 # all cases (live cases measure this Mac)
    python scripts/run_device_set.py --only B01,P02  # some cases
    python scripts/run_device_set.py --no-live       # scenarios only
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals" / "device"))

from agent.device.answer import report_text  # noqa: E402
from agent.device.shell import FixtureShell, LiveShell  # noqa: E402
from main import build_device_agent, load_config  # noqa: E402
from scenarios import FIXTURES, overrides  # noqa: E402


def check(case: dict, result) -> dict:
    expected_route = case.get("route", "none")
    got_route = result.route.topic or "none"
    codes = result.report.codes() if result.report else []
    missing = [c for c in case.get("expect", []) if c not in codes]
    forbidden = [c for c in case.get("forbid", []) if c in codes]
    keys_missing = [k for k in case.get("keys", []) if k.lower() not in result.answer.lower()]
    return {
        "route_ok": got_route == expected_route,
        "findings_ok": not missing and not forbidden,
        "missing": missing,
        "forbidden": forbidden,
        "keys_missing": keys_missing,
    }


def warm_up(agent) -> dict:
    times = {}
    for name, llm in (("router", agent.router_llm), ("writer", agent.writer_llm)):
        started = time.perf_counter()
        try:
            llm.chat([{"role": "user", "content": "Reply with OK."}])
        except Exception as exc:  # noqa: BLE001
            times[name] = f"failed: {exc}"
            continue
        times[name] = round(time.perf_counter() - started, 2)
    return times


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", default=str(ROOT / "evals" / "device" / "cases.toml"))
    parser.add_argument("--only", default="")
    parser.add_argument("--no-live", action="store_true")
    args = parser.parse_args()

    cfg = load_config(ROOT / "config.toml")
    cases = tomllib.loads(Path(args.cases).read_text(encoding="utf-8"))["case"]
    if args.only:
        wanted = {c.strip() for c in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted]
    if args.no_live:
        cases = [c for c in cases if c.get("scenario") != "live"]

    probe_agent = build_device_agent(cfg, shell=FixtureShell(FIXTURES))
    if probe_agent is None:
        raise SystemExit("The device agent is disabled in config.toml ([device] enabled = false).")
    warm = warm_up(probe_agent)
    print(f"Warm-up: {warm}")

    rows = []
    for case in cases:
        live = case.get("scenario") == "live"
        shell = LiveShell() if live else FixtureShell(FIXTURES, overrides=overrides(case.get("scenario", "recorded")))
        agent = build_device_agent(cfg, shell=shell, sleep=None if live else (lambda s: None))
        if not live:
            agent.capture_seconds, agent.battery_seconds = 3, 1
        started = time.perf_counter()
        result = agent.diagnose(case["question"])
        seconds = time.perf_counter() - started
        verdict = check(case, result)
        rows.append((case, result, verdict, seconds))
        flags = "route " + ("ok" if verdict["route_ok"] else "WRONG") + ", findings " + ("ok" if verdict["findings_ok"] else "WRONG")
        print(f"{case['id']:4} {seconds:6.1f} s  {flags}  answer by {result.method or '-'}")

    out_dir = ROOT / "logs" / "device_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"run_{stamp}.md"
    path.write_text(render(rows, cfg, warm), encoding="utf-8")
    print(f"\nReport: {path.relative_to(ROOT)}")


def render(rows, cfg, warm) -> str:
    device = cfg.get("device", {})
    routed = [r for r in rows if r[0].get("route", "none") != "none" or True]
    route_ok = sum(1 for _, _, v, _ in rows if v["route_ok"])
    scored = [r for r in rows if r[0].get("expect") or r[0].get("forbid")]
    findings_ok = sum(1 for _, _, v, _ in scored if v["findings_ok"])
    keyed = [r for r in rows if r[0].get("keys")]
    keys_ok = sum(1 for _, _, v, _ in keyed if not v["keys_missing"])
    answered = [r for r in rows if r[1].report]
    by_method = {}
    for _, result, _, _ in answered:
        by_method[result.method] = by_method.get(result.method, 0) + 1
    unsupported = sum(1 for _, result, _, _ in answered if result.unsupported)

    lines = [
        f"# Device set run {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Answer model: {device.get('answer_model')} | Router model: {device.get('router_model')} | "
        f"Live capture: {device.get('capture_seconds')} s | Warm-up: {warm}",
        "",
        f"- Route right: {route_ok} of {len(rows)}",
        f"- Findings as expected: {findings_ok} of {len(scored)}",
        f"- All expected strings in the answer: {keys_ok} of {len(keyed)}",
        f"- Answers by: " + ", ".join(f"{k} {v}" for k, v in sorted(by_method.items())),
        f"- Answers with a number not in the facts at first: {unsupported} of {len(answered)}",
    ]
    for topic in ("battery", "performance"):
        times = [s for c, r, _, s in rows if r.report and r.route.topic == topic and c.get("scenario") == "live"]
        if times:
            lines.append(f"- Live {topic} questions: median {statistics.median(times):.1f} s, max {max(times):.1f} s")
    lines += ["", "| # | Scenario | Route (expected → got, method) | Findings | Keys missing | Numbers not in facts | Answer by | Time (s) |",
              "|---|---|---|---|---|---|---|---|"]
    for case, result, v, seconds in rows:
        got = result.route.topic or "none"
        findings = "ok" if v["findings_ok"] else "missing " + ", ".join(v["missing"]) + (" / forbidden " + ", ".join(v["forbidden"]) if v["forbidden"] else "")
        if not (case.get("expect") or case.get("forbid")):
            findings = "-"
        lines.append(f"| {case['id']} | {case.get('scenario')} | {case.get('route', 'none')} → {got} ({result.route.method}) | {findings} | "
                     f"{', '.join(v['keys_missing']) or '-'} | {', '.join(result.unsupported) or '-'} | {result.method or '-'} | {seconds:.1f} |")
    for case, result, v, seconds in rows:
        lines += ["", f"## {case['id']} — {case['question']}", "",
                  f"**Scenario:** {case.get('scenario')}  ",
                  f"**Route:** {result.route.topic or 'none'} by {result.route.method} (rule matches {result.route.matches})  ",
                  f"**Expected findings:** {', '.join(case.get('expect', [])) or '-'}; forbidden: {', '.join(case.get('forbid', [])) or '-'}  ",
                  f"**Timings:** {result.timings}  "]
        if case.get("note"):
            lines.append(f"**Note:** {case['note']}  ")
        if result.report:
            lines += ["", "### Answer", "", result.answer]
            if result.rejected:
                lines += ["", f"### First answer of the model, not used ({result.rejected_reason})", "", "```text", result.rejected[:3000], "```"]
            lines += ["", "### Diagnosis given to the writer", "", "```text", report_text(result.report), "```"]
            if case.get("scenario") == "live":
                lines += ["", "### Readings", "", "```text"]
                lines += [f"{name} = {value} {unit} {quality if quality != 'ok' else ''}".rstrip() for name, (value, unit, quality) in result.readings.items()]
                lines.append("```")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
