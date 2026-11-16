"""Battery-aware power policy: choose the energy mode for a job on battery, switch to it, restore it, and
measure the energy the job used (docs/stage7_design.md §15).

The three parts:
1. choose()      a table in code (no model): job class and charge -> energy mode on battery.
2. BatteryMode   save -> switch -> run -> restore, like saving a register before an interrupt handler and
                 restoring it after. The restore runs even when the job fails, and is skipped when the user
                 changed the mode during the job (the user's choice wins).
3. EnergyMeter   the energy the job took from the battery, measured two ways: the battery's voltage x current
                 integrated over time, and the drop in the charge left in the battery. Two independent
                 measurements of one quantity check each other.

Only the battery setting is changed (`pmset -b`); the adapter setting stays as the user set it. The sudoers
rule allows exactly the three commands in SET_COMMANDS and nothing else, and this module runs no other
command with sudo.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .sources import battery, power

AUTOMATIC, LOW, HIGH = 0, 1, 2
NAMES = {AUTOMATIC: "Automatic", LOW: "Low Power", HIGH: "High Power"}
SET_COMMANDS = {mode: ["sudo", "-n", "/usr/bin/pmset", "-b", "powermode", str(mode)] for mode in NAMES}

HIGH_MIN_CHARGE = 50.0   # % below which a heavy job does not get High Power on battery
LOW_CHARGE = 20.0        # % below which every job runs in Low Power and heavy jobs wait

# Job classes. The jobs of the admission check (diagnosis.JOBS) map onto them.
JOB_CLASS = {"light": "light", "document_fast": "medium", "document": "heavy", "vision": "heavy", "long_run": "heavy"}


@dataclass
class Decision:
    mode: int | None     # None: leave the mode as it is
    reason: str
    defer: bool = False  # the job should wait (connect the adapter first)


def choose(job_class: str, charge: float | None, on_battery: bool) -> Decision:
    """The policy table of design §15. The energy measurements decide whether the table stays as it is."""
    if not on_battery:
        return Decision(None, "On the adapter: its own setting applies (High Power on this Mac).")
    if charge is None:
        return Decision(None, "The charge could not be read: the mode is left as it is.")
    if charge < LOW_CHARGE:
        return Decision(LOW, f"Charge below {LOW_CHARGE:g}%: Low Power for every job.", defer=job_class == "heavy")
    if job_class == "light":
        return Decision(LOW, "A light job: Low Power is fast enough and saves the battery.")
    if job_class == "medium":
        return Decision(AUTOMATIC, "A medium job: Automatic.")
    if job_class == "heavy":
        if charge >= HIGH_MIN_CHARGE:
            return Decision(HIGH, f"A heavy job with the charge at {charge:g}%: High Power.")
        return Decision(AUTOMATIC, f"A heavy job with the charge below {HIGH_MIN_CHARGE:g}%: Automatic; "
                                   "connect the adapter for a faster run.")
    raise ValueError(f"unknown job class {job_class!r}")


def battery_mode(shell) -> int | None:
    out = shell.run("pmset_custom")
    values = {r.name: r.value for r in power.parse_custom(out.text if out.ok else "")}
    return values.get("power.mode_battery")


class BatteryMode:
    """Context manager: sets the battery's energy mode for the job and restores the previous one.

        with BatteryMode(shell, decision.mode) as switch:
            run_the_job()
        switch.notes  # what happened, for the report
    """

    def __init__(self, shell, target: int | None) -> None:
        if target is not None and target not in SET_COMMANDS:
            raise ValueError(f"unknown energy mode {target!r}")
        self.shell, self.target = shell, target
        self.before: int | None = None
        self.changed = self.restored = False
        self.notes: list[str] = []

    def _set(self, mode: int) -> bool:
        out = self.shell.run("pmset_set_mode", SET_COMMANDS[mode])  # only the commands the sudoers rule allows
        if not out.ok:
            self.notes.append(f"Could not set {NAMES[mode]}: {out.error or 'failed'}.")
        return out.ok

    def __enter__(self) -> "BatteryMode":
        self.before = battery_mode(self.shell)
        if self.target is None:
            return self
        if self.before is None:
            self.notes.append("The current battery mode could not be read, so it is not changed.")
        elif self.before == self.target:
            self.notes.append(f"Already in {NAMES[self.target]}.")
        elif self._set(self.target):
            self.changed = True
            self.notes.append(f"Battery mode {NAMES[self.before]} -> {NAMES[self.target]}.")
        return self

    def __exit__(self, *exc) -> bool:
        if self.changed:
            now = battery_mode(self.shell)
            if now == self.target:
                self.restored = self._set(self.before)
                if self.restored:
                    self.notes.append(f"Restored {NAMES[self.before]}.")
            else:
                self.notes.append(f"The mode was changed to {NAMES.get(now, now)} during the job; left as it is.")
        return False  # an exception from the job is not swallowed


@dataclass
class Energy:
    seconds: float
    wh_integrated: float | None   # sum of V x I over time (trapezoids)
    wh_from_charge: float | None  # drop of the charge left (mAh) x mean voltage
    mean_watts: float | None
    samples: int


def integrate(samples: list[tuple[float, float]]) -> float:
    """Watt-hours from (seconds, watts) samples by the trapezoid rule."""
    joules = sum((t2 - t1) * (w1 + w2) / 2 for (t1, w1), (t2, w2) in zip(samples, samples[1:]))
    return joules / 3600


def _battery_state(shell) -> dict:
    out = shell.run("battery_ioreg")
    return {r.name: r.value for r in battery.parse_registry(out.text if out.ok else "")}


class EnergyMeter:
    """Samples the battery while a job runs (a background thread) and reports the energy the job used.

    Watts are counted positive while the battery discharges. The battery gauge refreshes its readings every
    few seconds (Run D3: two questions 5 s apart showed the same values), so a job should run for at least
    a minute for a usable result; the two methods agreeing is the check.
    """

    def __init__(self, shell, period: float = 1.0, clock=time.monotonic) -> None:
        self.shell, self.period, self.clock = shell, period, clock
        self.samples: list[tuple[float, float]] = []
        self.voltages: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.start_state: dict = {}
        self.end_state: dict = {}

    def sample(self) -> None:
        state = _battery_state(self.shell)
        volts, amps = state.get("battery.voltage"), state.get("battery.current")
        if volts is not None and amps is not None:
            self.samples.append((self.clock(), -volts * amps))
            self.voltages.append(volts)

    def _loop(self) -> None:
        while not self._stop.wait(self.period):
            self.sample()

    def __enter__(self) -> "EnergyMeter":
        self.start_state = _battery_state(self.shell)
        self.started = self.clock()
        self.sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.sample()
        self.end_state = _battery_state(self.shell)
        self.result = self._result()
        return False

    def _result(self) -> Energy:
        seconds = self.clock() - self.started
        integrated = integrate(self.samples) if len(self.samples) >= 2 else None
        before, after = self.start_state.get("battery.present_capacity"), self.end_state.get("battery.present_capacity")
        from_charge = None
        if before is not None and after is not None and self.voltages:
            from_charge = (before - after) / 1000 * (sum(self.voltages) / len(self.voltages))
        mean = integrated * 3600 / seconds if integrated is not None and seconds > 0 else None
        return Energy(seconds, integrated, from_charge, mean, len(self.samples))


@dataclass
class PolicyRun:
    job_class: str
    decision: Decision
    notes: list[str] = field(default_factory=list)
    energy: Energy | None = None
    result: object = None
    ran: bool = False


def run_with_policy(shell, job_class: str, job, meter_period: float = 1.0) -> PolicyRun:
    """Chooses the mode for the job, runs it in that mode with the energy meter on, and restores the mode."""
    state = _battery_state(shell)
    # Run D2: macOS kept reporting the adapter as connected after it was unplugged; the input power is checked too.
    unplugged = state.get("power.system_input") == 0 and (state.get("battery.current") or 0) < 0
    on_battery = state.get("power.external") == 0 or unplugged
    decision = choose(job_class, state.get("battery.charge"), on_battery)
    record = PolicyRun(job_class, decision)
    if decision.defer:
        record.notes.append("Deferred: connect the adapter first.")
        return record
    with BatteryMode(shell, decision.mode) as switch:
        if on_battery:
            with EnergyMeter(shell, meter_period) as meter:
                record.result = job()
            record.energy = meter.result
        else:
            record.result = job()
        record.ran = True
    record.notes += switch.notes
    return record
