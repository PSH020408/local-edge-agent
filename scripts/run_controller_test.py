"""Recorded test of the power feedback controller (agent/device/controller.py) on real deep-learning training.

    python scripts/run_controller_test.py            # about 5 minutes; on the adapter or on battery

Phases: 10 s idle (idle power), 60 s of training at full speed (the job's full power), then training held at
65% and then 40% of that power by the PI controller, 90 s each. Recorded every second: target, measured chip
power (raw and smoothed), duty, training steps. Reported per phase: settling time, excursions, steady-state
error and ripple, training steps per second, and chip energy per training step.

Keep the Mac on its own while it runs. Reports: logs/controller/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.controller import PI, PowerSensor, Trace, run_paced, step_metrics  # noqa: E402
from agent.device.workloads import MAC, Trainer, unload_models  # noqa: E402


def phase_summary(rows: list[dict], seconds: float, target: float | None) -> dict:
    watts = [r["raw"] for r in rows if r.get("raw") is not None]
    chunks = rows[-1]["chunks"] if rows else 0
    mean = sum(watts) / len(watts) if watts else None
    out = {"steps_per_s": round(chunks / seconds, 2), "mean_w": None if mean is None else round(mean, 2),
           "joules_per_step": None if mean is None or not chunks else round(mean * seconds / chunks, 3)}
    if target is not None:
        out.update(step_metrics(rows, target))
    return out


def main() -> None:
    unload_models()
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())]) if MAC else None
    trainer = Trainer()
    trainer.step()  # build and warm up
    sensor = PowerSensor().start()
    while sensor.smooth is None:
        time.sleep(0.2)
    trace, start = Trace(), time.monotonic()
    print("Idle 10 s ...", flush=True)
    idle_rows_from = len(trace.rows)
    run_paced(lambda: time.sleep(0.2), 10, sensor, None, trace, "idle", start=start)
    idle = [r["raw"] for r in trace.rows[idle_rows_from:] if r.get("raw") is not None]
    idle_w = sum(idle) / len(idle) if idle else 0.5

    print("Training at full speed, 60 s ...", flush=True)
    full_from = len(trace.rows)
    run_paced(trainer.step, 60, sensor, None, trace, "full speed", start=start)
    tail = [r["raw"] for r in trace.rows[full_from:] if r.get("raw") is not None][-30:]
    full_w = sum(tail) / len(tail)

    targets = [round(0.65 * full_w, 1), round(0.40 * full_w, 1)]
    pi = PI.tuned(targets[0], full_w, idle_w)
    for target in targets:
        pi.target = target
        print(f"Training held at {target} W, 90 s ...", flush=True)
        run_paced(trainer.step, 90, sensor, pi, trace, f"held at {target} W", start=start)
    sensor.stop()
    if awake:
        awake.terminate()

    phases = [("idle", 10, None), ("full speed", 60, None)] + [(f"held at {t} W", 90, t) for t in targets]
    summary = {name: phase_summary([r for r in trace.rows if r["phase"] == name], secs, target) for name, secs, target in phases}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "logs" / "controller"
    folder.mkdir(parents=True, exist_ok=True)
    result = {"idle_w": round(idle_w, 2), "full_w": round(full_w, 2), "kp": pi.kp, "ki": pi.ki, "summary": summary, "trace": trace.rows}
    (folder / f"controller_{stamp}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = [f"# Power controller test, {stamp}", "", f"Idle {idle_w:.2f} W, training at full speed {full_w:.2f} W; "
             f"Kp {pi.kp:.4f}, Ki {pi.ki:.4f} per W.", "",
             "| Phase | Steps/s | Mean chip W | J per step | Settling s | Above W | Below W | Steady error W | Ripple W |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, _, _ in phases:
        m = summary[name]
        lines.append(f"| {name} | {m['steps_per_s']} | {m['mean_w']} | {m['joules_per_step']} | {m.get('settling_s', '-')} | "
                     f"{m.get('above_w', '-')} | {m.get('below_w', '-')} | {m.get('steady_error_w', '-')} | {m.get('steady_ripple_w', '-')} |")
    (folder / f"controller_{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\n\nReport: logs/controller/controller_{stamp}.md")


if __name__ == "__main__":
    main()
