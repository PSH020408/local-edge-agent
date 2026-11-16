"""Step response of the battery registry's energy counter: when does a load show up in it, and how much?

    python scripts/gauge_step.py                 # about 7 minutes; the adapter may stay connected

Idle for 150 s, one minute of qwen3:14b generation, idle for 210 s. Meanwhile:
- the battery registry is read every second, and each publication of the power controller's running sum
  of the system load is logged (one per minute);
- powermetrics records the chip's power every second, as an independent reference for when the load
  really ran.
For each minute between two publications the report compares the counter's mean power with the chip's
mean power in the same minute and in the minute before. If the counter matches the minute before, its
publications lag by a minute, and energy must be read one publication later.

Why: energy run E2 (evals/device/energy.md) measured 4.1 W for a 14B generation in Automatic, below the
idle power, although the counter's own sample check passed.
"""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.sources import chip  # noqa: E402

IDLE_BEFORE, IDLE_AFTER = 150, 210


def registry() -> dict:
    text = subprocess.run(["ioreg", "-rn", "AppleSmartBattery", "-a"], capture_output=True).stdout
    battery = plistlib.loads(text)[0]
    telemetry = battery.get("PowerTelemetryData") or {}
    return {"update": battery.get("UpdateTime"), "sum_mj": telemetry.get("AccumulatedSystemLoad"),
            "count": telemetry.get("SystemLoadAccumulatorCount"), "load_mw": telemetry.get("SystemLoad")}


def generate(seconds_target: int = 60) -> None:
    body = {"model": "qwen3:14b", "prompt": f"{time.time()}: write a long story about a lighthouse keeper.",
            "stream": False, "think": False, "options": {"num_predict": 25 * seconds_target, "temperature": 0.7}}
    request = urllib.request.Request("http://localhost:11434/api/generate", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        response.read()


def main() -> None:
    print("Loading qwen3:14b ...", flush=True)
    body = {"model": "qwen3:14b", "prompt": "Hi", "stream": False, "options": {"num_predict": 1}}
    urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/generate", json.dumps(body).encode(),
                                                  {"Content-Type": "application/json"}), timeout=600).read()
    total = IDLE_BEFORE + 60 + IDLE_AFTER + 30
    meter = {}

    def run_powermetrics():
        meter["start"] = time.monotonic()
        out = subprocess.run(chip.command(samples=total), capture_output=True, text=True)
        meter["samples"] = [{r.name: r.value for r in sample} for sample in chip.parse(out.stdout)]

    t0 = time.monotonic()
    pm = threading.Thread(target=run_powermetrics)
    pm.start()
    publications, last, job = [], None, {}
    worker = None
    print(f"Idle {IDLE_BEFORE} s, one minute of generation, idle {IDLE_AFTER} s ...", flush=True)
    while time.monotonic() - t0 < total:
        now = time.monotonic() - t0
        if worker is None and now >= IDLE_BEFORE:
            job["on"] = now
            worker = threading.Thread(target=lambda: (generate(), job.__setitem__("off", time.monotonic() - t0)))
            worker.start()
        state = registry()
        if state["update"] != last:
            publications.append((now, state))
            last = state["update"]
            print(f"{now:6.0f} s  publication: load {state['load_mw']} mW, sum {state['sum_mj']}, count {state['count']}", flush=True)
        time.sleep(1)
    worker.join()
    pm.join()

    chip_watts = [(meter["start"] - t0 + i + 1, s.get("chip.combined_power")) for i, s in enumerate(meter.get("samples", []))]

    def chip_mean(a: float, b: float):
        values = [w for t, w in chip_watts if a < t <= b and w is not None]
        return sum(values) / len(values) if values else None

    rows = []
    for (ta, a), (tb, b) in zip(publications, publications[1:]):
        if a["sum_mj"] is None or b["sum_mj"] is None or b["count"] == a["count"]:
            continue
        counter = (b["sum_mj"] - a["sum_mj"]) / (b["count"] - a["count"]) / 1000
        same, before = chip_mean(ta, tb), chip_mean(ta - (tb - ta), ta)
        rows.append((ta, tb, counter, same, before))

    fmt = lambda v: "-" if v is None else f"{v:.1f}"  # noqa: E731
    lines = [f"# Step response of the energy counter, {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Generation from {job.get('on', 0):.0f} s to {job.get('off', 0):.0f} s.", "",
             "| Window (s) | Counter mean W | Chip W, same window | Chip W, window before |", "|---|---|---|---|"]
    lines += [f"| {ta:.0f}-{tb:.0f} | {counter:.1f} | {fmt(same)} | {fmt(before)} |" for ta, tb, counter, same, before in rows]
    report = "\n".join(lines) + "\n"
    out = ROOT / "logs" / "energy" / f"step_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print("\n" + report + f"Report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
