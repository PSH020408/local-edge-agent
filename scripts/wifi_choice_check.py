"""Replay a survey walk through the network choice: what would the agent have advised at each point, and how did
the joined network actually behave there?

    python scripts/wifi_choice_check.py logs/home/walk_floor-5g_20261119_095217.jsonl --current "curi6 5g"

The beacons recorded at each point stand in for the scan; the latency is that of the network joined during the walk.
A good rule advises staying where the joined network had no latency spikes and switching where it had them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import wifi_choice  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("walk", type=Path)
    ap.add_argument("--current", required=True, help="network joined during the walk")
    ap.add_argument("--spike-ms", type=float, default=50.0, help="p95 to the router above this counts as spiky")
    args = ap.parse_args()
    tally: dict[str, list[int]] = {}
    print(f"{'pt':>3} {'place':22} {'advice':7} {'best':10} {'SINR now':>8} {'SINR best':>9} {'p95 ms':>7}")
    for line in args.walk.open():
        r = json.loads(line)
        if "id" not in r or not r.get("beacons"):     # header lines; walk 1 recorded no beacons of the other routers
            continue
        scan = [{"ssid": k, **v} for k, v in (r.get("beacons") or {}).items()]
        choice = wifi_choice.decide(wifi_choice.candidates(scan, r.get("noise") or -93, r.get("link_width") or 80, None, args.current))
        p95 = (r.get("latency") or {}).get("p95_ms")
        bad = p95 is None or p95 > args.spike_ms        # no latency: the link was lost there
        tally.setdefault(choice.action, [0, 0])[bad] += 1
        cur = choice.current
        print(f"{r['id']:>3} {r.get('label', '')[:22]:22} {choice.action:7} {(choice.best.ssid if choice.best else '-')[:10]:10} "
              f"{(cur.sinr if cur else float('nan')):>8.0f} {(choice.best.sinr if choice.best else float('nan')):>9.0f} "
              f"{('lost' if p95 is None else f'{p95:.0f}'):>7}")
    print("\nadvice: points without / with spikes or loss on the joined network")
    for action, (good, bad) in sorted(tally.items()):
        print(f"  {action:7} {good:3} / {bad}")


if __name__ == "__main__":
    main()
