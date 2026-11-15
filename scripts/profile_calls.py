"""Where the time of a run goes: a summary of logs/model_calls.jsonl by model.

Each model call is logged by agent/llm.py with the time Ollama spent loading the model, reading
the prompt and writing the answer. This script adds them up per model and counts the loads that
took more than a second (the model was not in memory and had to be read from disk).

Usage:
    python scripts/profile_calls.py                      # the whole log
    python scripts/profile_calls.py --since 2026-11-16T01:00
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", default=str(ROOT / "logs" / "model_calls.jsonl"))
    parser.add_argument("--since", default="", help="ISO time; only calls from then on")
    args = parser.parse_args()

    rows = []
    for line in Path(args.log).read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("time", "") >= args.since:
            rows.append(record)
    if not rows:
        raise SystemExit("no calls in the log")

    by_model: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        m = by_model[r["model"]]
        m["calls"] += 1
        m["wall_s"] += r.get("wall_s", 0)
        m["load_s"] += r.get("load_s", 0)
        m["reloads"] += 1 if r.get("load_s", 0) > 1 else 0
        m["prompt_s"] += r.get("prompt_s", 0)
        m["gen_s"] += r.get("gen_s", 0)
        m["prompt_tokens"] += r.get("prompt_tokens", 0)
        m["output_tokens"] += r.get("output_tokens", 0)

    total = sum(m["wall_s"] for m in by_model.values())
    print(f"{len(rows)} calls, {total / 60:.1f} min of model time, {rows[0]['time']} to {rows[-1]['time']}\n")
    print("| Model | Calls | Minutes | Share | Loading | Reloads | Reading prompt | Writing | Prompt tok/s | Output tok/s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, m in sorted(by_model.items(), key=lambda kv: -kv[1]["wall_s"]):
        read_rate = m["prompt_tokens"] / m["prompt_s"] if m["prompt_s"] else 0
        write_rate = m["output_tokens"] / m["gen_s"] if m["gen_s"] else 0
        print(f"| {name} | {int(m['calls'])} | {m['wall_s'] / 60:.1f} | {m['wall_s'] / total:.0%} | {m['load_s'] / 60:.1f} min "
              f"| {int(m['reloads'])} | {m['prompt_s'] / 60:.1f} min | {m['gen_s'] / 60:.1f} min | {read_rate:.0f} | {write_rate:.1f} |")
    peak = max((sum(x.get("gb", 0) for x in r.get("loaded", [])) for r in rows), default=0)
    print(f"\nMost memory held by loaded models at once: {peak:.1f} GB")


if __name__ == "__main__":
    main()
