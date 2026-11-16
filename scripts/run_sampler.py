"""Background sampler: stores the fast readings every period in logs/device.db.

Run it at background priority, which macOS schedules on the efficiency cores:
    taskpolicy -b python scripts/run_sampler.py                 # until stopped with Ctrl+C
    taskpolicy -b python scripts/run_sampler.py --minutes 10    # for an experiment

The cost experiment of Stage 7 runs it twice for 10 minutes, at default and at background priority:
    python scripts/run_sampler.py --minutes 10 --label default
    taskpolicy -b python scripts/run_sampler.py --minutes 10 --label background
and compares the CPU time per round printed at the end (and stored as sampler.cpu_seconds).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.sampler import Sampler  # noqa: E402
from agent.device.shell import LiveShell  # noqa: E402
from agent.device.store import Store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--period", type=float, default=10.0, help="seconds between rounds")
    parser.add_argument("--minutes", type=float, default=None, help="stop after this many minutes")
    parser.add_argument("--label", default="", help="name of the run in the summary")
    args = parser.parse_args()

    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    store = Store(ROOT / cfg.get("device", {}).get("store", "logs/device.db"))
    sampler = Sampler(LiveShell(), store, period=args.period)
    cpu, wall = [], []

    def on_round(s, result):
        cpu.append(result.cpu_seconds)
        wall.append(result.wall_seconds)
        print(f"round {s.rounds}: {len(result.readings)} readings, {result.wall_seconds:.2f} s, "
              f"CPU {result.cpu_seconds * 1000:.0f} ms ({100 * result.cpu_seconds / args.period:.2f}% of one core)", flush=True)

    try:
        sampler.run(duration=args.minutes * 60 if args.minutes else None, on_round=on_round)
    except KeyboardInterrupt:
        pass
    if cpu:
        print(f"\n{args.label or 'run'}: {len(cpu)} rounds, CPU per round median {statistics.median(cpu) * 1000:.0f} ms, "
              f"mean {100 * statistics.mean(cpu) / args.period:.2f}% of one core, round time median {statistics.median(wall):.2f} s; "
              f"{store.count()} readings stored")


if __name__ == "__main__":
    main()
