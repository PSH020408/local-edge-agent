"""Capture: n seconds of per-second readings for a diagnosis, reduced to features.

While a question is being diagnosed, the fast sources are read once a second for n seconds and
powermetrics records n one-second samples in one process, run in a parallel thread. Each numeric
reading becomes a feature set: mean, minimum, maximum, first, last and slope per minute.
Text readings (a process name, the power source) keep their last value.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .readings import Reading
from .sources import battery, chip, load, memory, power, thermal
from .store import Window, window_of

CAPTURE_READERS = (battery.read, power.read, thermal.read, load.read, memory.read)


@dataclass
class Capture:
    seconds: int
    latest: dict[str, Reading] = field(default_factory=dict)
    features: dict[str, Window] = field(default_factory=dict)
    samples: int = 0
    chip_samples: int = 0

    def value(self, name: str):
        r = self.latest.get(name)
        return r.value if r is not None and r.ok else None

    def mean(self, name: str):
        w = self.features.get(name)
        return w.mean if w else None


def capture(shell, seconds: int = 10, with_chip: bool = True, sleep=time.sleep) -> Capture:
    chip_result: list[list[Reading]] = []
    worker = None
    if with_chip:
        worker = threading.Thread(target=lambda: chip_result.extend(chip.read_samples(shell, seconds)), daemon=True)
        worker.start()
    series: dict[str, list[tuple[str, float]]] = {}
    result = Capture(seconds)

    def add(readings: list[Reading]) -> None:
        for r in readings:
            if not r.ok:
                result.latest.setdefault(r.name, r)
                continue
            result.latest[r.name] = r
            if isinstance(r.value, (int, float)) and not isinstance(r.value, bool):
                series.setdefault(r.name, []).append((r.time, float(r.value)))

    for second in range(max(1, seconds)):
        began = time.monotonic()
        for read in CAPTURE_READERS:
            add(read(shell))
        result.samples += 1
        if second < seconds - 1:
            sleep(max(0.0, 1.0 - (time.monotonic() - began)))
    if worker is not None:
        worker.join(timeout=seconds + 10)
        for sample in chip_result:
            add(sample)
        result.chip_samples = len(chip_result)
    result.features = {name: window_of(points) for name, points in series.items()}
    return result
