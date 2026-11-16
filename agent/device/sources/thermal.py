"""Thermal state: the thermal pressure level and the CPU limits macOS has recorded.

Two different signals:

- Thermal pressure level (`notifyutil -g com.apple.system.thermalpressurelevel`): the level the
  thermal manager announces to the whole system, defined in OSThermalNotification.h as
  0 nominal, 1 moderate, 2 heavy, 3 trapping, 4 sleeping. On Apple silicon this is the signal that
  goes with real throttling (on 2026-11-16 it was "moderate" while the GPU was held at its lowest
  clocks). It is read without rights, so the background sampler can log it.
- CPU limits (`pmset -g therm`): an older mechanism that records a cap on CPU speed, scheduler time
  or available CPUs (for example "CPU_Speed_Limit = 70": the CPU may run at 70% of its normal
  speed). "No CPU power status has been recorded" means no cap since start-up, recorded here as
  100% with quality "estimated", because it is an absence of a record, not a measurement.
"""

from __future__ import annotations

import re

from ..readings import Reading, now, reading

PRESSURE = {0: "nominal", 1: "moderate", 2: "heavy", 3: "trapping", 4: "sleeping"}
_LIMITS = {
    "CPU_Speed_Limit": ("thermal.cpu_speed_limit", "%"),
    "CPU_Scheduler_Limit": ("thermal.cpu_scheduler_limit", "%"),
    "CPU_Available_CPUs": ("thermal.cpu_available", "count"),
}


def parse_pressure(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    found = re.search(r"thermalpressurelevel\s+(\d+)", text)
    level = int(found.group(1)) if found else None
    return [
        reading("thermal.pressure_level", level, "level", time),
        reading("thermal.pressure", PRESSURE.get(level) if level is not None else None, "text", time),
    ]


def parse_limits(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    readings = []
    no_record = "No CPU power status has been recorded" in text
    for key, (name, unit) in _LIMITS.items():
        found = re.search(rf"{key}\s*=\s*(\d+)", text)
        if found:
            readings.append(reading(name, int(found.group(1)), unit, time))
        elif no_record and unit == "%":
            readings.append(reading(name, 100, unit, time, quality="estimated"))  # no cap since start-up
        else:
            readings.append(reading(name, None, unit, time))
    return readings


def read(shell) -> list[Reading]:
    pressure, limits = shell.run("thermal_pressure"), shell.run("pmset_therm")
    time = now()
    return parse_pressure(pressure.text if pressure.ok else "", time) + parse_limits(limits.text if limits.ok else "", time)
