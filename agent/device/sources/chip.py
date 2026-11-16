"""Chip frequency, residency and power per second, from `powermetrics` (administrator rights,
allowed without a password for that one command by /etc/sudoers.d/powermetrics).

powermetrics samples the hardware counters over an interval and prints, per CPU cluster and for
the GPU: the average frequency while active, the share of time active ("residency") and the time
spent in each frequency state, plus CPU, GPU and Neural Engine power and the thermal pressure.
The highest frequency listed for a cluster is its maximum, so a reading also says how far below
its maximum a cluster runs: the GPU held at 338-618 MHz of 1,578 MHz on 2026-11-16 is visible
here as about a quarter of its maximum while 100% active.

One call with `-n N -i 1000` gives N one-second samples; parse() returns them all, each sample
with its own time, so a capture of n seconds needs one process, not n.
"""

from __future__ import annotations

import re
from datetime import datetime

from ..readings import Reading, now, reading

PRESSURE = {"nominal": 0, "moderate": 1, "heavy": 2, "trapping": 3, "sleeping": 4}


def command(samples: int = 1, interval_ms: int = 1000) -> list[str]:
    return ["sudo", "-n", "/usr/bin/powermetrics", "-n", str(samples), "-i", str(interval_ms),
            "-s", "cpu_power,gpu_power,ane_power,thermal"]


def _sample_time(block: str) -> str:
    found = re.search(r"\(([A-Z][a-z]{2} [A-Z][a-z]{2} +\d+ \d\d:\d\d:\d\d \d{4})", block)
    if found:
        try:
            return datetime.strptime(" ".join(found.group(1).split()), "%a %b %d %H:%M:%S %Y").isoformat(timespec="seconds")
        except ValueError:
            pass
    return now()


def _states(listing: str) -> list[int]:
    return [int(mhz) for mhz in re.findall(r"(\d+) MHz:", listing)]


def parse_sample(block: str, time: str | None = None) -> list[Reading]:
    time = time or _sample_time(block)
    readings = []
    for name, freq in re.findall(r"^(E|P\d)-Cluster HW active frequency:\s*(\d+) MHz", block, re.M):
        key = name.lower()
        residency = re.search(rf"^{name}-Cluster HW active residency:\s*([\d.]+)%\s*\((.*)\)", block, re.M)
        readings += [
            reading(f"chip.{key}_cluster_frequency", int(freq), "MHz", time),
            reading(f"chip.{key}_cluster_active", float(residency.group(1)) if residency else None, "%", time),
            reading(f"chip.{key}_cluster_max_frequency", max(_states(residency.group(2))) if residency else None, "MHz", time),
        ]
    for label, name in (("CPU Power", "cpu_power"), ("GPU Power", "gpu_power"), ("ANE Power", "ane_power"),
                        (r"Combined Power \(CPU \+ GPU \+ ANE\)", "combined_power")):
        found = re.search(rf"^{label}:\s*(\d+) mW", block, re.M)
        readings.append(reading(f"chip.{name}", round(int(found.group(1)) / 1000, 3) if found else None, "W", time))
    gpu_freq = re.search(r"^GPU HW active frequency:\s*(\d+) MHz", block, re.M)
    gpu_res = re.search(r"^GPU HW active residency:\s*([\d.]+)%\s*\((.*)\)", block, re.M)
    pressure = re.search(r"^Current pressure level:\s*(\w+)", block, re.M)
    level = PRESSURE.get(pressure.group(1).lower()) if pressure else None
    readings += [
        reading("chip.gpu_frequency", int(gpu_freq.group(1)) if gpu_freq else None, "MHz", time),
        reading("chip.gpu_active", float(gpu_res.group(1)) if gpu_res else None, "%", time),
        reading("chip.gpu_max_frequency", max(_states(gpu_res.group(2))) if gpu_res else None, "MHz", time),
        reading("chip.thermal_pressure_level", level, "level", time),
    ]
    return readings


def parse(text: str) -> list[list[Reading]]:
    """One list of readings per sample."""
    blocks = re.split(r"\*\*\* Sampled system activity", text)[1:]
    return [parse_sample("*** Sampled system activity" + block) for block in blocks]


def read(shell) -> list[Reading]:
    output = shell.run("powermetrics")
    samples = parse(output.text) if output.ok else []
    if samples:
        return samples[-1]
    return [reading(name, None, unit) for name, unit in (("chip.cpu_power", "W"), ("chip.gpu_power", "W"),
                                                         ("chip.gpu_frequency", "MHz"), ("chip.thermal_pressure_level", "level"))]


def read_samples(shell, seconds: int) -> list[list[Reading]]:
    """`seconds` one-second samples from one powermetrics process (used by the capture)."""
    output = shell.run("powermetrics", command(samples=seconds))
    return parse(output.text) if output.ok else []
