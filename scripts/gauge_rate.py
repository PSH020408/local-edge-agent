"""How often the battery registry refreshes each value: the time resolution of every power measurement.

    python scripts/gauge_rate.py --seconds 60

Reads the battery registry once per second and reports, for each field, how many times it changed and the
median interval between changes. Motivation: the first energy experiment (logs/energy/, 2026-11-16) gave
two methods that disagreed by up to ten times on runs of 30-60 s, and Run D3 showed the same battery values
in two questions 5 s apart.
"""

from __future__ import annotations

import argparse
import plistlib
import statistics
import subprocess
import time

FIELDS = ("UpdateTime", "Voltage", "Amperage", "InstantAmperage", "AppleRawCurrentCapacity")
TELEMETRY = ("SystemLoad", "SystemPowerIn", "BatteryPower", "AccumulatedSystemLoad", "SystemLoadAccumulatorCount",
             "AccumulatedBatteryPower", "BatteryPowerAccumulatorCount", "AccumulatedSystemEnergyConsumed", "SystemEnergyConsumed")


def read() -> dict:
    text = subprocess.run(["ioreg", "-rn", "AppleSmartBattery", "-a"], capture_output=True).stdout
    battery = plistlib.loads(text)[0]
    telemetry = battery.get("PowerTelemetryData") or {}
    values = {k: battery.get(k) for k in FIELDS}
    values.update({k: telemetry.get(k) for k in TELEMETRY})
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    start = time.monotonic()
    previous, changes, first, last = read(), {}, None, None
    first = dict(previous)
    for _ in range(args.seconds):
        time.sleep(1)
        now, current = time.monotonic() - start, read()
        for key, value in current.items():
            if value != previous.get(key):
                changes.setdefault(key, []).append(now)
        previous, last = current, current
    print(f"{'field':34} {'changes':>7} {'median interval (s)':>20}  first -> last")
    for key in FIELDS + TELEMETRY:
        times = changes.get(key, [])
        gaps = [b - a for a, b in zip(times, times[1:])]
        median = f"{statistics.median(gaps):.1f}" if gaps else "-"
        print(f"{key:34} {len(times):7d} {median:>20}  {first.get(key)} -> {last.get(key)}")


if __name__ == "__main__":
    main()
