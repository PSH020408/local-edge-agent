"""One record format for every hardware reading (the hardware abstraction layer of Stage 7).

Every reader returns a list of Reading records. The layers above (store, diagnosis, answers) never
see a macOS command or its output format, only names, values and SI units. A value that cannot be
read becomes a Reading with quality "missing" instead of an exception, so a diagnosis can say
"cannot tell" rather than fail.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime

# Units used across the device layer. Readers convert to these (macOS reports mV, mA and
# hundredths of a degree).
UNITS = {
    "V", "A", "W", "Wh", "J", "mAh", "%", "°C", "MHz", "bytes", "bytes/s", "count", "min", "s",
    "flag",   # 1 or 0
    "level",  # an ordered state, such as thermal pressure 0-4
    "code",   # a status code reported by the hardware, kept as it is
    "text",   # a short label such as "Good" or "AC Power"
    "score",  # a relative score computed by macOS, such as a process's energy impact
}
QUALITIES = {"ok", "missing", "estimated"}
_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")  # "<source>.<item>", e.g. battery.cycle_count


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Reading:
    name: str
    value: float | int | str | None
    unit: str
    time: str
    quality: str = "ok"

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(f"reading name must look like 'source.item': {self.name!r}")
        if self.unit not in UNITS:
            raise ValueError(f"unknown unit {self.unit!r} for {self.name}")
        if self.quality not in QUALITIES:
            raise ValueError(f"unknown quality {self.quality!r}")
        if self.value is None and self.quality != "missing":
            raise ValueError(f"{self.name} has no value but is not marked missing")

    @property
    def ok(self) -> bool:
        return self.quality != "missing"

    def as_dict(self) -> dict:
        return asdict(self)


def reading(name: str, value, unit: str, time: str | None = None, quality: str = "ok") -> Reading:
    """A reading; a value of None is recorded as missing."""
    if value is None:
        quality = "missing"
    return Reading(name, value, unit, time or now(), quality)


def by_name(readings: list[Reading]) -> dict[str, Reading]:
    return {r.name: r for r in readings}
