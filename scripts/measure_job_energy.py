"""Energy of one job in each energy mode on battery: the experiment behind the policy table (design §15).

Run it on battery (the adapter unplugged), with the charge at 40% or more:
    python scripts/measure_job_energy.py --job heavy          # qwen3:14b, about 6-8 minutes
    python scripts/measure_job_energy.py --job medium         # qwen3:4b-instruct

The same generation (fixed prompt, seed and length) runs in Low Power, Automatic and High Power, each with
the energy meter on; the battery mode is restored after each run. The report gives time, tokens per
second, watts and the energy per 1,000 tokens, measured two ways (V x I integrated, and the drop in the
charge left). Whether racing at High Power uses less energy than going slowly is decided here.
Reports go to logs/energy/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import power_policy as pp  # noqa: E402
from agent.device.shell import LiveShell  # noqa: E402

JOBS = {
    "heavy": ("qwen3:14b", 800),
    "medium": ("qwen3:4b-instruct", 3000),
}
PROMPT = ("Write a detailed technical report on how lithium-ion battery packs in laptops are managed: cell "
          "balancing, charge limits, thermal limits and state-of-charge estimation. Use several sections.")
OLLAMA = "http://localhost:11434/api/generate"


def generate(model: str, tokens: int) -> dict:
    body = {"model": model, "prompt": PROMPT, "stream": False, "think": False,
            "options": {"num_predict": tokens, "temperature": 0, "seed": 1}}
    request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", choices=JOBS, default="heavy")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--pause", type=float, default=20.0, help="seconds between runs, to let the chip cool")
    args = parser.parse_args()
    model, tokens = JOBS[args.job]
    shell = LiveShell()

    state = pp._battery_state(shell)
    if state.get("power.external") != 0:
        sys.exit("Unplug the adapter first: the energy is measured from the battery.")
    if (state.get("battery.charge") or 0) < 40:
        sys.exit("The charge is below 40%: connect the adapter and try later.")
    start_mode = pp.battery_mode(shell)
    print(f"On battery at {state.get('battery.charge')}%, battery mode {pp.NAMES.get(start_mode)}. Loading {model} ...", flush=True)
    generate(model, 1)  # load the model before measuring

    rows = []
    for repeat in range(1, args.repeats + 1):
        for mode in (pp.LOW, pp.AUTOMATIC, pp.HIGH):
            with pp.BatteryMode(shell, mode) as switch, pp.EnergyMeter(shell, period=1.0) as meter:
                result = generate(model, tokens)
            energy, count = meter.result, result.get("eval_count", 0)
            per_k = lambda wh: None if wh is None or not count else 1000 * wh / count  # noqa: E731
            row = {"mode": pp.NAMES[mode], "repeat": repeat, "seconds": round(energy.seconds, 1), "tokens": count,
                   "tokens_per_s": round(count / (result.get("eval_duration", 1) / 1e9), 1),
                   "mean_w": energy.mean_watts and round(energy.mean_watts, 1),
                   "wh": energy.wh_integrated and round(energy.wh_integrated, 3),
                   "wh_from_charge": energy.wh_from_charge and round(energy.wh_from_charge, 3),
                   "wh_per_1k_tokens": per_k(energy.wh_integrated) and round(per_k(energy.wh_integrated), 3),
                   "samples": energy.samples, "notes": " ".join(switch.notes)}
            rows.append(row)
            print(json.dumps(row), flush=True)
            time.sleep(args.pause)

    end_mode = pp.battery_mode(shell)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "logs" / "energy" / f"energy_{args.job}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Energy per mode on battery, {args.job} job ({model}, {tokens} tokens), {stamp}", "",
             f"Battery mode before: {pp.NAMES.get(start_mode)}; after: {pp.NAMES.get(end_mode)}.", "",
             "| Mode | Run | Time (s) | Tokens | Tokens/s | Mean W | Wh (V x I) | Wh (charge drop) | Wh per 1k tokens |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['mode']} | {r['repeat']} | {r['seconds']} | {r['tokens']} | {r['tokens_per_s']} | {r['mean_w']} | "
              f"{r['wh']} | {r['wh_from_charge']} | {r['wh_per_1k_tokens']} |" for r in rows]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBattery mode restored: {pp.NAMES.get(end_mode)} (was {pp.NAMES.get(start_mode)}). Report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
