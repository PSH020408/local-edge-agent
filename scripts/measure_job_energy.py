"""Energy of one job in each energy mode on battery: the experiment behind the policy table (design §15).

Run it on battery (the adapter unplugged), with the charge at 40% or more:
    python scripts/measure_job_energy.py --job heavy          # qwen3:14b writes 800 tokens
    python scripts/measure_job_energy.py --job long_prompt    # qwen3:14b reads a long prompt, writes 50 tokens
    python scripts/measure_job_energy.py --job medium         # qwen3:4b-instruct writes 3,000 tokens

The same job runs in Low Power, Automatic and High Power; the battery mode is restored after each run. The
energy comes from the power controller's running sum of the system load (power_policy.measure), so each
run waits for the registry's publications (one per minute): about 3-4 minutes per mode. The report gives
time, tokens per second, watts and the energy per 1,000 tokens. Whether racing at High Power uses less
energy than going slowly is decided here. Reports go to logs/energy/.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import power_policy as pp  # noqa: E402
from agent.device.shell import LiveShell  # noqa: E402

JOBS = {  # name: (model, tokens to write, long prompt)
    "heavy": ("qwen3:14b", 800, False),
    "long_prompt": ("qwen3:14b", 50, True),
    "medium": ("qwen3:4b-instruct", 3000, False),
}
PROMPT = ("Write a detailed technical report on how lithium-ion battery packs in laptops are managed: cell "
          "balancing, charge limits, thermal limits and state-of-charge estimation. Use several sections.")
OLLAMA = "http://localhost:11434/api/generate"


def long_prompt() -> str:
    """About 8,000 tokens of this project's own documents, for a job that is mostly reading (prefill)."""
    text = "\n\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "docs/roadmap.md", "docs/stage7_design.md"))
    return text[:32000] + "\n\nSummarise the documents above in five sentences."


def generate(model: str, tokens: int, prompt: str) -> dict:
    body = {"model": model, "prompt": prompt, "stream": False, "think": False,
            "options": {"num_predict": tokens, "temperature": 0, "seed": 1, "num_ctx": 16384}}
    request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", choices=JOBS, default="heavy")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    model, tokens, reads_long = JOBS[args.job]
    base = long_prompt() if reads_long else PROMPT
    shell = LiveShell()

    state = pp._battery_state(shell)
    if state.get("power.external") != 0:
        sys.exit("Unplug the adapter first: the energy is measured from the battery.")
    if (state.get("battery.charge") or 0) < 40:
        sys.exit("The charge is below 40%: connect the adapter and try later.")
    start_mode = pp.battery_mode(shell)
    print(f"On battery at {state.get('battery.charge')}%, battery mode {pp.NAMES.get(start_mode)}. Loading {model} ...", flush=True)
    generate(model, 1, "Hello")  # load the model before measuring

    rows = []
    for repeat in range(1, args.repeats + 1):
        for mode in (pp.LOW, pp.AUTOMATIC, pp.HIGH):
            # A different first line each run: Ollama reuses the cached prompt otherwise, and the reading is skipped.
            prompt = f"Run {repeat}-{mode}.\n{base}"
            with pp.BatteryMode(shell, mode) as switch:
                result, energy = pp.measure(shell, lambda: generate(model, tokens, prompt))
            count, read = result.get("eval_count", 0), result.get("prompt_eval_count", 0)
            row = {"mode": pp.NAMES[mode], "repeat": repeat, "seconds": round(energy.seconds, 1),
                   "prompt_tokens": read, "prompt_tokens_per_s": round(read / (result.get("prompt_eval_duration", 1) / 1e9), 1),
                   "tokens": count, "tokens_per_s": round(count / (result.get("eval_duration", 1) / 1e9), 1),
                   "mean_w": energy.mean_watts and round(energy.mean_watts, 1),
                   "idle_w": energy.idle_watts and round(energy.idle_watts, 1),
                   "wh": energy.wh and round(energy.wh, 3), "check": energy.check, "notes": " ".join(switch.notes)}
            rows.append(row)
            print(json.dumps(row), flush=True)

    end_mode = pp.battery_mode(shell)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "logs" / "energy" / f"energy_{args.job}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Energy per mode on battery, {args.job} job ({model}, {tokens} tokens written), {stamp}", "",
             f"Battery mode before: {pp.NAMES.get(start_mode)}; after: {pp.NAMES.get(end_mode)}.", "",
             "| Mode | Run | Time (s) | Prompt tokens | Read/s | Tokens | Written/s | Mean W | Idle W | Wh | Check |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['mode']} | {r['repeat']} | {r['seconds']} | {r['prompt_tokens']} | {r['prompt_tokens_per_s']} | {r['tokens']} | "
              f"{r['tokens_per_s']} | {r['mean_w']} | {r['idle_w']} | {r['wh']} | {r['check']} |" for r in rows]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBattery mode restored: {pp.NAMES.get(end_mode)} (was {pp.NAMES.get(start_mode)}). Report: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
