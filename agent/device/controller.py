"""Power feedback controller: holds the chip's power at a target during long jobs by pacing the work.

The loop, as in a control course:
- plant:     the job's pace (duty, 0-1) -> chip power. Measured on 2026-11-17: power follows the load within a
             second, and the power budget then decays with a time constant of about 12 s under full load;
             macOS's thermal pressure only reacts minutes later, so the controller watches power, not pressure.
- sensor:    chip power from powermetrics every second, smoothed by an exponential moving average.
- actuator:  the duty of the job. The work is cut into short chunks; after each chunk the job rests for
             chunk_time x (1 - duty) / duty, like the off time of a PWM signal.
- controller: PI. error = target - measured; duty = Kp x error + integral, clamped to [min_duty, 1]. The
             integral stops growing while the output sits at a limit (anti-windup), so the loop does not
             overshoot when the target becomes reachable again.

Tuning from the measured plant: the duty-to-power gain K is the job's full-speed power minus idle power, and
power follows the load within the 1 s update, so the loop is mostly integral: Ki = 1 / (K x 6 s) for a
closed-loop time constant of about 6 s, and Kp = 0.3 / K for a quick first reaction (tested on a simulated
plant with the measured burst decay in tests/test_controller.py).
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field

from .sources import chip


@dataclass
class PI:
    kp: float
    ki: float
    target: float
    low: float = 0.05
    high: float = 1.0
    integral: float = 0.0
    idle_watts: float | None = None   # with full_watts: feedforward of the duty the target should need
    full_watts: float | None = None

    def feedforward(self) -> float:
        """The duty a linear plant would need for the target: (target - idle) / (full - idle).

        Hardware test 1 (2026-11-17) without it: on each step the loop started from the old duty and the
        integral had to travel the whole way (an undershoot to 12 W for an 18.6 W target, 15 s to settle).
        With it, a new target moves the duty at once and the integral only corrects the plant's nonlinearity."""
        if self.idle_watts is None or self.full_watts is None or self.full_watts <= self.idle_watts:
            return 0.0
        return min(1.0, max(0.0, (self.target - self.idle_watts) / (self.full_watts - self.idle_watts)))

    def update(self, measured: float, dt: float) -> float:
        error = self.target - measured
        ff = self.feedforward()
        # Anti-windup by clamping: the integral may only grow until the output reaches its limit. A first
        # version stopped integrating whenever the next output would pass the limit, and then the output stuck
        # at 0.95 with a target out of reach (found by the simulated-plant test).
        self.integral += self.ki * error * dt
        self.integral = min(max(self.integral, self.low - ff - self.kp * error), self.high - ff - self.kp * error)
        return min(self.high, max(self.low, ff + self.kp * error + self.integral))

    @classmethod
    def tuned(cls, target: float, full_watts: float, idle_watts: float, closed_loop_seconds: float = 6.0,
              feedforward: bool = True) -> "PI":
        """For a plant that is a gain K (W per unit of duty) within the update period, an integral gain of
        1 / (K x T) gives a closed-loop time constant T; the proportional part (0.3 / K) adds a quick first
        reaction. T = 6 s leaves room for the sensor's lag (1 s averaging, then smoothing: about 2.5 s)."""
        gain = max(1.0, full_watts - idle_watts)
        if feedforward:
            return cls(kp=0.3 / gain, ki=1.0 / (gain * closed_loop_seconds), target=target, integral=0.0,
                       idle_watts=idle_watts, full_watts=full_watts)
        return cls(kp=0.3 / gain, ki=1.0 / (gain * closed_loop_seconds), target=target, integral=0.7)


class PowerSensor:
    """Chip power every second from powermetrics (one-sample calls), smoothed: alpha 0.4."""

    def __init__(self, alpha: float = 0.4, command=None):
        self.alpha, self.raw, self.smooth, self.count = alpha, None, None, 0
        self.command = command or (lambda: chip.command(samples=1))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.is_set():
            out = subprocess.run(self.command(), capture_output=True, text=True)
            samples = chip.parse(out.stdout)
            if samples:
                watts = {r.name: r.value for r in samples[-1]}.get("chip.combined_power")
                if watts is not None:
                    self.raw = watts
                    self.smooth = watts if self.smooth is None else self.alpha * watts + (1 - self.alpha) * self.smooth
                    self.count += 1
            else:
                self._stop.wait(1.0)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)


@dataclass
class Trace:
    rows: list[dict] = field(default_factory=list)

    def add(self, **row):
        self.rows.append(row)


def run_paced(chunk, seconds: float, sensor: PowerSensor, pi: PI | None, trace: Trace, phase: str,
              clock=time.monotonic, sleep=time.sleep, update_every: float = 1.0, start: float | None = None) -> int:
    """Runs `chunk()` repeatedly for `seconds`, paced by the PI controller (full speed when `pi` is None).

    Returns the number of chunks done (the work)."""
    start = clock() if start is None else start
    began, done, duty, last_update, seen = clock(), 0, 1.0, clock(), None
    while clock() - began < seconds:
        t0 = clock()
        chunk()
        done += 1
        spent = clock() - t0
        now = clock()
        fresh = getattr(sensor, "count", None) != seen  # hardware test 1: updating twice on one sample doubled the integral gain
        if pi is not None and now - last_update >= update_every and sensor.smooth is not None and fresh:
            duty = pi.update(sensor.smooth, now - last_update)
            last_update, seen = now, getattr(sensor, "count", None)
            trace.add(t=round(now - start, 2), phase=phase, target=pi.target, raw=sensor.raw,
                      smooth=round(sensor.smooth, 2), duty=round(duty, 3), chunks=done)
        elif pi is None and now - last_update >= update_every:
            last_update = now
            trace.add(t=round(now - start, 2), phase=phase, target=None, raw=sensor.raw,
                      smooth=None if sensor.smooth is None else round(sensor.smooth, 2), duty=1.0, chunks=done)
        if duty < 1.0:
            sleep(spent * (1 - duty) / duty)
    return done


def step_metrics(rows: list[dict], target: float, band: float = 0.10) -> dict:
    """Settling time (when the smoothed power last entered ±band around the target), the largest excursion
    above and below the target after settling began, and the steady-state error and ripple (last 30 s)."""
    if not rows:
        return {}
    t0 = rows[0]["t"]
    values = [(r["t"] - t0, r["smooth"]) for r in rows if r.get("smooth") is not None]
    if not values:
        return {}
    outside = [t for t, v in values if abs(v - target) > band * target]
    settled = 0.0 if not outside else (None if outside[-1] == values[-1][0] else outside[-1])
    tail = [v for t, v in values if t >= values[-1][0] - 30]
    inside = [abs(v - target) <= band * target for _, v in values]
    first = next((t for (t, _), ok in zip(values, inside) if ok), None)
    return {"settling_s": None if settled is None else round(settled, 1),
            "first_in_band_s": None if first is None else round(first, 1),
            "inside_band_share": round(sum(inside) / len(inside), 2),
            "above_w": round(max(0.0, max(v for _, v in values) - target), 2),
            "below_w": round(max(0.0, target - min(v for _, v in values)), 2),
            "steady_error_w": round(sum(tail) / len(tail) - target, 2),
            "steady_ripple_w": round(max(tail) - min(tail), 2)}
