"""Background sampler: reads the fast sources every period and stores them, and measures its own cost.

Fast sources (about 0.1-0.2 s per round): battery, power, thermal, load, memory. Storage space and
health are read every `slow_period`. The sampler is meant to run at background priority
(`taskpolicy -b python scripts/run_sampler.py`), which macOS schedules on the efficiency cores.

Its own cost is part of every round: the CPU time of the sampler process and of the commands it
started (getrusage for children), stored as sampler.cpu_seconds and as a share of the period
(sampler.cpu_share). The budget is under 1% of one core.
"""

from __future__ import annotations

import resource
import time
from dataclasses import dataclass, field

from .readings import Reading, reading
from .sources import battery, load, memory, power, storage, thermal

FAST_READERS = (battery.read, power.read, thermal.read, load.read, memory.read)
SLOW_READERS = (storage.read,)


def _cpu_seconds() -> float:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


@dataclass
class RoundResult:
    readings: list[Reading]
    cpu_seconds: float
    wall_seconds: float


@dataclass
class Sampler:
    shell: object
    store: object | None = None
    period: float = 10.0
    slow_period: float = 600.0
    rounds: int = 0
    totals: dict = field(default_factory=lambda: {"cpu_seconds": 0.0, "wall_seconds": 0.0})
    _last_slow: float = float("-inf")

    def sample_once(self, clock: float | None = None) -> RoundResult:
        clock = time.monotonic() if clock is None else clock
        started_cpu, started_wall = _cpu_seconds(), time.monotonic()
        readings: list[Reading] = []
        for read in FAST_READERS:
            readings += read(self.shell)
        if clock - self._last_slow >= self.slow_period:
            for read in SLOW_READERS:
                readings += read(self.shell)
            self._last_slow = clock
        cpu, wall = _cpu_seconds() - started_cpu, time.monotonic() - started_wall
        readings += [
            reading("sampler.cpu_seconds", round(cpu, 4), "s"),
            reading("sampler.cpu_share", round(100 * cpu / self.period, 3), "%"),
            reading("sampler.round_seconds", round(wall, 4), "s"),
        ]
        if self.store is not None:
            self.store.write(readings)
        self.rounds += 1
        self.totals["cpu_seconds"] += cpu
        self.totals["wall_seconds"] += wall
        return RoundResult(readings, cpu, wall)

    def run(self, duration: float | None = None, sleep=time.sleep, on_round=None) -> None:
        """Samples every `period` seconds until `duration` has passed (forever when None)."""
        start = time.monotonic()
        while duration is None or time.monotonic() - start < duration:
            began = time.monotonic()
            result = self.sample_once(began)
            if on_round:
                on_round(self, result)
            if self.store is not None and self.rounds % 360 == 0:  # about once an hour at 10 s
                self.store.prune()
            sleep(max(0.0, self.period - (time.monotonic() - began)))
