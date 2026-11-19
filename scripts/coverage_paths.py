"""Does the signal go through the walls or around them? Four propagation models compared by leave-one-out error,
for each router and band of a survey walk.

    python scripts/coverage_paths.py logs/home/walk_floor-5g_20261119_095217.jsonl
    python scripts/coverage_paths.py logs/home/walk_*.jsonl --points AP-A     # per-point predictions for AP-A

Models (fitted by least squares; error on each point when it is left out of the fit):
- distance only:  A - 10 n log10(d)                      d: straight-line distance
- through walls:  A - 10 n log10(d) - L * walls            walls crossed by the straight line (the multi-wall model)
- door path:      A - 10 n log10(p) - T * turn             p: shortest route through open space and open doors;
                                                           turn: its bends in right angles (90 degrees = 1)
- both paths:     the power sum of the door path and the through-wall path (nonlinear fit)
The repeatability of the survey (3 dB RMS between two days) is the floor no model can go below.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import coverage as cv  # noqa: E402

LINEAR = {
    "distance only": lambda g: [1, -10 * math.log10(g["d"])],
    "through walls": lambda g: [1, -10 * math.log10(g["d"]), -g["walls"]],
    "door path": lambda g: [1, -10 * math.log10(g["p"]), -g["turn"]],
}


def both(params, g):
    a, n, t, l = params
    door = a - 10 * n * math.log10(g["p"]) - t * g["turn"]
    wall = a - 10 * n * math.log10(g["d"]) - l * g["walls"]
    return 10 * math.log10(10 ** (door / 10) + 10 ** (wall / 10))


def fit(model, rows):
    if model == "both paths":
        return least_squares(lambda p: [both(p, g) - y for g, y in rows], [-35, 3, 10, 10],
                             bounds=([-80, 1.5, 0, 0], [0, 6, 40, 40])).x
    x = np.array([LINEAR[model](g) for g, _ in rows])
    return np.linalg.lstsq(x, np.array([y for _, y in rows]), rcond=None)[0]


def predict(model, params, g):
    return both(params, g) if model == "both paths" else float(np.dot(LINEAR[model](g), params))


def loo(model, rows):
    errs = [predict(model, fit(model, rows[:i] + rows[i + 1:]), rows[i][0]) - rows[i][1] for i in range(len(rows))]
    return float(np.sqrt(np.mean(np.square(errs)))), errs


def geometry(plan, ap, ids):
    p = plan.for_router(ap["xy"], ap.get("height_m"))
    routes = cv.DoorPaths(p, p.router)
    out = {}
    for pid in ids:
        xy = plan.points[pid]["xy"]
        r = routes.route(xy)
        out[pid] = {"d": p.distance_m(xy), "walls": cv.walls_crossed(p.walls, p.router, xy), "p": r["path_m"], "turn": r["turn"]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("walks", nargs="+", type=Path)
    ap.add_argument("--plan", type=Path, default=ROOT / "logs" / "home" / "plan.json")
    ap.add_argument("--points", help="print per-point predictions for this access point (e.g. AP-A)")
    args = ap.parse_args()
    plan = cv.Plan.load(args.plan)
    aps = {a["name"].split()[0]: a for a in json.loads(args.plan.read_text())["access_points"]}
    models = list(LINEAR) + ["both paths"]
    print(f"{'walk':10} {'signal':18} {'N':>3} " + " ".join(f"{m:>14}" for m in models) + "   fitted (door path: n, dB per 90 deg; both: wall dB)")
    for walk in args.walks:
        rows = [json.loads(line) for line in walk.open()]
        rows = [r for r in rows if "id" in r and r["id"] in plan.points]
        series = [("AP-A", "link", None)]
        if any(r.get("beacons") for r in rows):
            for name, a in aps.items():
                series += [(name, s, s) for s in a["ssids"]]
        cache = {}
        for name, label, ssid in series:
            if name not in cache:
                cache[name] = geometry(plan, aps[name], [r["id"] for r in rows])
            data = []
            for r in rows:
                y = r.get("rssi") if ssid is None else ((r.get("beacons") or {}).get(ssid) or {}).get("rssi_dbm")
                if y is not None and not (ssid is None and r.get("link_band") not in (None, "5")):
                    data.append((cache[name][r["id"]], float(y), r["id"]))
            if len(data) < 6:
                continue
            pairs = [(g, y) for g, y, _ in data]
            res = {m: loo(m, pairs) for m in models}
            dp, bp = fit("door path", pairs), fit("both paths", pairs)
            print(f"{walk.stem[-15:]:10} {name + ' ' + label:18} {len(pairs):>3} " + " ".join(f"{res[m][0]:>14.1f}" for m in models)
                  + f"   n {dp[1]:.1f}, {dp[2]:.0f} dB; wall {bp[3]:.0f} dB")
            if args.points == name and ssid is None:
                for (g, y, pid), e_dp, e_w in zip(data, res["door path"][1], res["through walls"][1]):
                    print(f"    {pid:>3} {plan.points[pid].get('label', '')[:22]:22} measured {y:6.1f}  door path {y + e_dp:6.1f}  "
                          f"through walls {y + e_w:6.1f}   route {g['p']:.1f} m, turn {g['turn']:.2f}, walls {g['walls']}")


if __name__ == "__main__":
    main()
