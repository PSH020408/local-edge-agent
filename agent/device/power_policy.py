"""Battery-aware power policy: choose the energy mode for a job on battery, switch to it, restore it, and
measure the energy the job used (docs/stage7_design.md §15).

The three parts:
1. choose()      a table in code (no model): job class and charge -> energy mode on battery.
2. BatteryMode   save -> switch -> run -> restore, like saving a register before an interrupt handler and
                 restoring it after. The restore runs even when the job fails, and is skipped when the user
                 changed the mode during the job (the user's choice wins).
3. measure()     the energy of the job from counters kept in hardware, read at the registry's publications
                 (once a minute): on the adapter the power controller's running sum of the system load, on
                 battery the gauge's coulomb counter (the charge left). Chosen by experiment (E1, E2 and
                 the step tests in evals/device/energy.md).

Only the battery setting is changed (`pmset -b`); the adapter setting stays as the user set it. The sudoers
rule allows exactly the three commands in SET_COMMANDS and nothing else, and this module runs no other
command with sudo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .sources import battery, power

AUTOMATIC, LOW, HIGH = 0, 1, 2
NAMES = {AUTOMATIC: "Automatic", LOW: "Low Power", HIGH: "High Power"}
SET_COMMANDS = {mode: ["sudo", "-n", "/usr/bin/pmset", "-b", "powermode", str(mode)] for mode in NAMES}

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
        # Energy run E1 (evals/device/energy.md): qwen3:14b generated 25.3 tokens/s in both Automatic and High
        # Power, 14.1 in Low Power. Generation is bound by memory bandwidth, so High Power cannot speed it up.
        return Decision(AUTOMATIC, "A heavy job: Automatic. Model generation is limited by memory bandwidth, so "
                                   "High Power would not make it faster (energy run E1).")
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
    seconds: float            # the job's own run time
    wh: float | None          # energy of the job: the window's energy minus the idle power over the parts outside the job
    mean_watts: float | None  # mean system load while the job ran
    idle_watts: float | None  # mean system load in the minute before the job
    window_seconds: float     # from the publication before the job to the last one counted
    check: str                # "ok", or why the result should not be used
    windows: int = 1          # publications after the job until the counter was back near idle
    source: str = "system counter"  # on battery: "charge drop" (the gauge's coulomb counter)


def integrate(samples: list[tuple[float, float]]) -> float:
    """Watt-hours from (seconds, watts) samples by the trapezoid rule."""
    joules = sum((t2 - t1) * (w1 + w2) / 2 for (t1, w1), (t2, w2) in zip(samples, samples[1:]))
    return joules / 3600


def _battery_state(shell) -> dict:
    out = shell.run("battery_ioreg")
    return {r.name: r.value for r in battery.parse_registry(out.text if out.ok else "")}


def wait_for_publication(shell, after, sleep=time.sleep, clock=time.monotonic, timeout: float = 90.0):
    """Polls once per second until the registry publishes new values (UpdateTime changes); returns (state, time)."""
    started = clock()
    while True:
        state = _battery_state(shell)
        if state.get("battery.update_time") != after:
            return state, clock()
        if clock() - started > timeout:
            raise TimeoutError("the battery registry did not publish new values")
        sleep(1.0)


def measure(shell, job, sleep=time.sleep, clock=time.monotonic) -> tuple[object, Energy]:
    """Runs `job` between publications of the battery registry and returns its energy.

    History: E1 integrated V x I sampled every second, but the registry publishes once a minute. E2 used the
    power controller's running sum of the system load: right on the adapter (step test, same minute, no
    lag), but on battery it hardly moved during a 14B generation (6.4 W against 4.9 W idle while the chip
    alone drew 17 W) and the energy never arrived later either. On battery the energy therefore comes from
    the battery gauge's own coulomb counter: the drop of the charge left (mAh) times the voltage.

    The job starts right after a publication. After the job the window is extended, one publication at a
    time, until a window is back near the idle power (measured the same way in the minute before), so
    energy that is reported late is still counted; the idle power is subtracted for the time outside the job.
    """
    first, _ = wait_for_publication(shell, None, sleep, clock)
    first, t_first = wait_for_publication(shell, first.get("battery.update_time"), sleep, clock)  # a fresh one
    start, t_start = wait_for_publication(shell, first.get("battery.update_time"), sleep, clock)
    source = "charge drop" if start.get("power.external") == 0 else "system counter"
    idle = _mean_watts(first, start, t_start - t_first, source)
    t0 = clock()
    result = job()
    t1 = clock()
    seen = _battery_state(shell).get("battery.update_time")
    end, t_end = wait_for_publication(shell, seen, sleep, clock)
    previous, t_previous, windows = start, t_start, 1
    while windows < 5:
        recent = _mean_watts(previous, end, t_end - t_previous, source)
        if idle is None or recent is None or (recent <= 1.2 * idle + 1.0 and t_end - t_previous >= 20):
            break
        previous, t_previous = end, t_end
        end, t_end = wait_for_publication(shell, end.get("battery.update_time"), sleep, clock)
        windows += 1
    window = t_end - t_start
    total = _joules(start, end, source)
    outside = (t0 - t_start) + (t_end - t1)
    check = "ok"
    if total is None or idle is None:
        check = f"the {source} was not readable"
    elif source == "system counter":
        samples = _samples(start, end)
        if samples is None or abs(samples - window) > max(3.0, 0.05 * window):
            check = f"{samples} load samples in a {window:.0f} s window: a publication was missed"
    joules = None if total is None or idle is None else total - idle * outside
    mean = None if joules is None or t1 <= t0 else joules / (t1 - t0)
    # Energy run E2: a 14B generation came out at 4.1 W, below the 5.1 W idle, with the sample check passed.
    if check == "ok" and mean is not None and mean < idle:
        check = f"the job's mean ({mean:.1f} W) is below the idle power ({idle:.1f} W): the window missed the job"
    # Energy run E3: the idle minute before a Low Power run read -4.5 W (the charge left went up), and the
    # subtraction then added energy to the job. The gauge re-estimates its charge now and then.
    if check == "ok" and idle is not None and idle < 0.5:
        check = f"the idle power read {idle:.1f} W, which is not physical: the gauge re-estimated its charge"
    if check == "ok" and windows == 5:
        check = "not back near idle after five publications"
    return result, Energy(t1 - t0, None if joules is None else joules / 3600, mean, idle, window, check, windows, source)


def _joules(a: dict, b: dict, source: str = "system counter") -> float | None:
    if source == "charge drop":
        mah = (a.get("battery.present_capacity"), b.get("battery.present_capacity"))
        volts = [v for v in (a.get("battery.voltage"), b.get("battery.voltage")) if v is not None]
        if None in mah or not volts:
            return None
        return (mah[0] - mah[1]) / 1000 * (sum(volts) / len(volts)) * 3600
    x, y = a.get("power.system_energy_sum"), b.get("power.system_energy_sum")
    return None if x is None or y is None else y - x


def _samples(a: dict, b: dict) -> float | None:
    x, y = a.get("power.system_load_samples"), b.get("power.system_load_samples")
    return None if x is None or y is None else y - x


def _mean_watts(a: dict, b: dict, seconds: float, source: str = "system counter") -> float | None:
    joules = _joules(a, b, source)
    if joules is None:
        return None
    if source == "system counter":
        samples = _samples(a, b)
        return joules / samples if samples else None
    return joules / seconds if seconds > 0 else None


@dataclass
class PolicyRun:
    job_class: str
    decision: Decision
    notes: list[str] = field(default_factory=list)
    energy: Energy | None = None
    result: object = None
    ran: bool = False


def run_with_policy(shell, job_class: str, job, measure_energy: bool = False) -> PolicyRun:
    """Chooses the mode for the job, runs it in that mode, and restores the mode.

    With `measure_energy` the job's energy is measured as well; that waits for up to three publications of
    the battery registry (one per minute), so it is for experiments, not for every job.
    """
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
        if on_battery and measure_energy:
            record.result, record.energy = measure(shell, job)
        else:
            record.result = job()
        record.ran = True
    record.notes += switch.notes
    return record
