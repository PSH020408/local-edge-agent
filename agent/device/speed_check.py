"""Speed check before a long run: a short self-test of the machine, like a power-on self-test.

Why: Run 45 of Stage 6 took hours longer than usual because the GPU was held at its lowest clocks, and this
was found only after the run. A 100-token generation with the run's model takes a few seconds; its speed is
compared with the speed this Mac normally reaches. If it is far below, the performance diagnosis runs at
once and the long run is stopped before it wastes hours.

The normal speeds were measured in energy runs E1-E3 (evals/device/energy.md): qwen3:14b writes 25.1-25.4
tokens/s in Automatic and High Power, 14.1-14.2 in Low Power. Generation is bound by memory bandwidth, so
the speed is stable from run to run, which makes it a good health signal.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field

# Tokens per second written, by model and energy mode (power.mode_now: 0 automatic, 1 low power, 2 high power).
NORMAL = {"qwen3:14b": {0: 25.3, 1: 14.1, 2: 25.3}}
SLOW, MUCH_SLOWER = 0.8, 0.6   # shares of the normal speed


@dataclass
class SpeedCheck:
    model: str
    tokens_per_s: float | None
    normal: float | None
    load_seconds: float | None
    verdict: str                  # "normal", "slow", "much slower", "no normal known" or "failed"
    message: str
    findings: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float | None:
        return None if not self.tokens_per_s or not self.normal else self.tokens_per_s / self.normal


def ollama_generate(host: str, model: str, tokens: int = 100) -> dict:
    body = {"model": model, "prompt": f"Check {time.time():.0f}. Write a short paragraph about rivers.",
            "stream": False, "think": False, "options": {"num_predict": tokens, "temperature": 0}}
    request = urllib.request.Request(f"{host}/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def check(generate, model: str, mode: int | None, diagnose=None) -> SpeedCheck:
    """`generate(model)` returns Ollama's response; `diagnose()` returns the titles of the performance findings."""
    try:
        result = generate(model)
    except Exception as exc:  # noqa: BLE001
        return SpeedCheck(model, None, None, None, "failed", f"The speed check could not run: {exc}")
    count, duration = result.get("eval_count") or 0, (result.get("eval_duration") or 0) / 1e9
    speed = count / duration if count and duration else None
    load = (result.get("load_duration") or 0) / 1e9
    normal = NORMAL.get(model, {}).get(mode if mode is not None else 0)
    if speed is None:
        return SpeedCheck(model, None, normal, load, "failed", "The model returned no timing.")
    if normal is None:
        return SpeedCheck(model, speed, None, load, "no normal known", f"{model}: {speed:.1f} tokens/s (no normal speed recorded).")
    ratio = speed / normal
    text = f"{model}: {speed:.1f} tokens/s, {100 * ratio:.0f}% of the normal {normal:g} tokens/s for this energy mode."
    if ratio >= SLOW:
        return SpeedCheck(model, speed, normal, load, "normal", text)
    verdict = "slow" if ratio >= MUCH_SLOWER else "much slower"
    findings = diagnose() if diagnose else []
    cause = ("Diagnosis: " + "; ".join(findings) + ".") if findings else "The diagnosis found no cause in the readings."
    hours = "" if verdict == "slow" else " A long run would take about " + f"{1 / ratio:.1f} times as long."
    return SpeedCheck(model, speed, normal, load, verdict, f"{text}{hours} {cause}", findings)


REFERENCE_MODEL = "qwen3:14b"  # a fixed reference job: the check measures the machine, not the run's model


def before_long_run(host: str, model: str = REFERENCE_MODEL, shell=None) -> SpeedCheck:
    """Runs the check on this Mac: the energy mode from pmset, the diagnosis from the device agent."""
    from .agent import DeviceAgent
    from .shell import LiveShell
    from .sources import power

    shell = shell or LiveShell()
    mode = {r.name: r.value for r in power.read(shell)}.get("power.mode_now")

    def diagnose() -> list[str]:
        report = DeviceAgent(shell, capture_seconds=5).diagnose("can I run a long test run now?", topic="performance").report
        return [f.title for f in report.findings if f.severity in ("problem", "warning")]

    return check(lambda m: ollama_generate(host, m), model, mode, diagnose)
