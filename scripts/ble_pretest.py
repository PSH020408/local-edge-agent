"""Bluetooth LE pre-test: is the advertising device heard often and steadily enough for the walk?

    python scripts/ble_pretest.py --name MyiPhone --seconds 60

Keep the device and the Mac still (for example 1 m apart) while it runs. Reported: packets per second, the
signal's median and spread, how the mean of 5, 10 and 20 s windows differs from the whole (the walk averages
20 s per point: two placements of 10 s), and whether the device's identifier changed (iPhones rotate their
Bluetooth address, which must not break the walk: it is followed by name).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.sources import ble, wifi  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()

    print(f"Starting the Bluetooth scanner (about 15 s; allow Terminal to use Bluetooth if asked) ...", flush=True)
    monitor = ble.BleMonitor(args.name).start()
    if not monitor.wait_ready(45):
        monitor.stop()
        sys.exit(f"'{args.name}' was not heard in 45 s: check that its Bluetooth is on and Settings > Bluetooth is open.")
    start = time.time()
    print(f"Heard. Measuring for {args.seconds:.0f} s; keep both still ...", flush=True)
    time.sleep(args.seconds)
    monitor.stop()
    heard = [(t - start, r) for t, r in monitor.heard if t >= start and r < 0]
    if len(heard) < 5:
        sys.exit(f"Only {len(heard)} packets in {args.seconds:.0f} s: too few for the walk.")
    values = [r for _, r in heard]
    gaps = [b - a for (a, _), (b, _) in zip(heard, heard[1:])]
    print(f"\nPackets: {len(values)} in {args.seconds:.0f} s ({len(values) / args.seconds:.1f} per second); "
          f"longest silence {max(gaps):.1f} s")
    print(f"Signal: median {statistics.median(values):.0f} dBm, mean {statistics.fmean(values):.1f}, "
          f"spread (SD) {statistics.pstdev(values):.1f} dB, range {min(values)} to {max(values)}")
    for w in (5, 10, 20):
        rows = wifi.window_spread([(t, float(r)) for t, r in heard], [w], lambda v: sum(v) / len(v))
        if rows:
            r = rows[0]
            print(f"  {w:>2} s windows: {r['windows']}, means {r['min']} to {r['max']} dBm, worst error {r['worst_error']} dB")
    print("\nFor the walk: 20 s per point is enough if the 20 s windows stay within about 1-2 dB of the whole "
          "and there is no silence longer than a few seconds.")


if __name__ == "__main__":
    main()
