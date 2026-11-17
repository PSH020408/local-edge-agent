"""Coverage report from a walk: path-loss models scored on held-out points, coverage maps, and what each signal
level allows (SNR, MCS, rate and latency measured at each point).

    python scripts/coverage_report.py --walk logs/home/walk_<time>.jsonl [--doors logs/home/doors_<time>.jsonl]

Models (agent/device/coverage.py), each fitted on the training points and scored on the held-out points
chosen before the walk: multi-wall, distance only, free space (n = 2), and interpolation of the measured values.
Maps: 5 GHz (with use zones), 2.4 GHz and Bluetooth, as contour lines on the plan. Everything stays in logs/home/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import coverage as cv  # noqa: E402

SIGNALS = [("rssi", "5 GHz link (CoreWLAN)"), ("scan_5", "5 GHz beacons (scan)"), ("scan_24", "2.4 GHz beacons (scan)"),
           ("bt", "Bluetooth speaker at the router")]
# IEEE 802.11ac minimum receiver sensitivity, 80 MHz channel, MCS 0-9 (dBm): the standard's floor; real chips do better.
SENSITIVITY_80 = [-76, -73, -71, -68, -64, -60, -59, -58, -53, -51]
USES = [("games and video calls", lambda r: r["latency"].get("p95_ms", 1e9) <= 50 and r["latency"].get("loss_percent", 100) <= 1),
        ("streaming and browsing", lambda r: (r.get("tx_mbps") or 0) >= 50 and r["latency"].get("loss_percent", 100) <= 2),
        ("messaging only", lambda r: r["latency"].get("loss_percent", 100) <= 5)]
COLORS = [(46, 160, 67), (120, 190, 60), (240, 180, 40)]


def measured_zones(rows: list[dict]) -> tuple[list, list[str]]:
    """For each use, the weakest 5 GHz signal above which every measured point met the use's criterion."""
    ranked = sorted([r for r in rows if r.get("rssi") is not None], key=lambda r: -r["rssi"])
    zones, notes = [], []
    for (name, ok), color in zip(USES, COLORS):
        passing = None
        for r in ranked:
            if not ok(r):
                break
            passing = r["rssi"]
        if passing is None:
            notes.append(f"{name}: failed even at the strongest point; prior threshold kept")
            prior = next(z for z in cv.PRIOR_ZONES if z[1] == name)
            zones.append(prior)
        else:
            all_ok = all(ok(r) for r in ranked)
            notes.append(f"{name}: every point at or above {passing:.0f} dBm met it" +
                         (" (all points did: the real limit is lower than measured)" if all_ok else ""))
            zones.append((round(passing, 1), name, color))
    zones.append((-200.0, "unreliable", (215, 60, 50)))
    return zones, notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--walk", required=True)
    parser.add_argument("--doors", default=None)
    parser.add_argument("--plan", default="logs/home/plan.json")
    args = parser.parse_args()

    plan = cv.Plan.load(ROOT / args.plan)
    rows = [json.loads(l) for l in (ROOT / args.walk).read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if "id" in r]
    out = ROOT / "logs" / "home" / f"report_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# Coverage report, {out.name}", "", f"{len(rows)} points; held out before the walk: {', '.join(plan.holdout)}.", ""]

    lines += ["## Path-loss models, scored on the held-out points", ""]
    results = {}
    for key, name in SIGNALS:
        res = cv.compare(plan, rows, key)
        results[key] = res
        if "_model" not in res:
            lines += [f"**{name}:** too few points ({res['train_points']}).", ""]
            continue
        lines += [f"**{name}** ({res['train_points']} training, {res['test_points']} held out)", "",
                  "| Model | A at 1 m, dBm | n | Loss per wall, dB | Fit RMSE dB | Held-out RMSE dB | Held-out max error dB |",
                  "|---|---|---|---|---|---|---|"]
        for model in ["multi-wall", "distance only", "free space (n = 2)", "interpolation (IDW)"]:
            m = res[model]
            h = m["holdout"]
            lines.append(f"| {model} | {m.get('a_dbm', '-')} | {m.get('n', '-')} | {m.get('wall_db', '-')} | {m.get('fit_rmse_db', '-')} | "
                         f"{h.get('rmse_db', '-')} | {h.get('max_abs_db', '-')} |")
        lines.append("")

    zones, notes = measured_zones(rows)
    lines += ["## What each signal level allowed (5 GHz, AWDL off)", "", *[f"- {n}" for n in notes], "",
              "| Point | Distance m | Walls | Signal dBm | SNR dB | MCS | Streams | Rate Mb/s | Standard's floor for this MCS | "
              "Router p95 ms | Loss % | 2.4 GHz dBm | Bluetooth dBm |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -(r.get("snr") or -999)):
        mcs = r.get("mcs")
        floor = SENSITIVITY_80[int(mcs)] if mcs is not None and 0 <= int(mcs) < 10 else "-"
        lat = r["latency"]
        lines.append(f"| {r['id']}{'*' if r['id'] in plan.holdout else ''} | {r['distance_m']} | {r['walls']} | {r.get('rssi')} | "
                     f"{r.get('snr')} | {mcs} | {r.get('nss')} | {r.get('tx_mbps')} | {floor} | {lat.get('p95_ms')} | "
                     f"{lat.get('loss_percent')} | {r.get('scan_24')} | {r.get('bt')} |")
    lines += ["", "\\* held out.", ""]

    if args.doors:
        drows = [json.loads(l) for l in (ROOT / args.doors).read_text(encoding="utf-8").splitlines()]
        drows = [r for r in drows if "id" in r]
        lines += ["## Router-room door: open against closed", "", "| Point | 5 GHz open | 5 GHz closed | 2.4 GHz open | 2.4 GHz closed | BT open | BT closed |",
                  "|---|---|---|---|---|---|---|"]
        diffs = {k: [] for k, _ in SIGNALS}
        for pid in sorted({r["id"] for r in drows}):
            o = next((r for r in drows if r["id"] == pid and not r["doors_closed"]), {})
            c = next((r for r in drows if r["id"] == pid and r["doors_closed"]), {})
            for k in diffs:
                if o.get(k) is not None and c.get(k) is not None:
                    diffs[k].append(o[k] - c[k])
            lines.append(f"| {pid} | {o.get('rssi')} | {c.get('rssi')} | {o.get('scan_24')} | {c.get('scan_24')} | {o.get('bt')} | {c.get('bt')} |")
        lines += ["", "Mean loss of the closed door: " + ", ".join(
            f"{name.split(' (')[0]} {sum(d) / len(d):.1f} dB" for (k, name), d in ((s, diffs[s[0]]) for s in SIGNALS) if d), ""]

    lines += ["## Maps", ""]
    for key, name in SIGNALS:
        res = results.get(key, {})
        if "_model" not in res:
            continue
        model = res["_model"]
        values = cv.predict_map(plan, model)
        title = f"{name}: n {model.n:.2f}, {model.wall_db:.1f} dB per wall, held-out RMSE {res['multi-wall']['holdout'].get('rmse_db')} dB"
        levels = [-50, -60, -70, -80, -90] if key == "bt" else cv.LEVELS
        path = cv.render(plan, values, out / f"map_{key}.png", title, measured=rows, key=key,
                         zones=zones if key == "rssi" else None, levels=levels)
        lines.append(f"- {name}: {path.name}")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps({k: {m: v for m, v in r.items() if m != "_model"} for k, r in results.items()}, indent=1),
                                      encoding="utf-8")
    print("\n".join(lines) + f"\nReport and maps: {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
