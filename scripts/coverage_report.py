"""Coverage report from a walk: models scored on held-out points, coverage maps for every home network, the
best network per place, and what each signal level allowed (SNR, MCS, rate, latency at each point).

    python scripts/coverage_report.py --walk logs/home/walk_<label>_<time>.jsonl [--doors logs/home/doors_<time>.jsonl]

Signals: the Mac's link to its own router; the beacons of every home network (three routers, two bands each)
heard in the scan at each point; a Bluetooth LE device next to the Mac's router. Each signal is modelled from the
position of the router that sends it. Methods (agent/device/coverage.py): multi-wall, multi-wall plus interpolated
residuals, interpolation, distance only, free space. A method is chosen by leave-one-out error on the training
points; every method is also scored once on the points held out before the walk. Everything stays in logs/home/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import coverage as cv  # noqa: E402

# IEEE 802.11ac minimum receiver sensitivity, 80 MHz channel, MCS 0-9 (dBm): the standard's floor; real chips do better.
SENSITIVITY_80 = [-76, -73, -71, -68, -64, -60, -59, -58, -53, -51]
USES = [("games and video calls", lambda r: r["latency"].get("p95_ms", 1e9) <= 50 and r["latency"].get("loss_percent", 100) <= 1),
        ("streaming and browsing", lambda r: (r.get("tx_mbps") or 0) >= 50 and r["latency"].get("loss_percent", 100) <= 2),
        ("messaging only", lambda r: r["latency"].get("loss_percent", 100) <= 5)]
COLORS = [(46, 160, 67), (120, 190, 60), (240, 180, 40)]
AP_COLORS = [(196, 30, 70), (30, 120, 80), (110, 60, 170)]   # AP-A, AP-B, AP-C as on the home's measurement map


def load_rows(path: Path) -> list[dict]:
    """The last row of each point counts (a point measured again with --redo); rows marked invalid are dropped."""
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if "id" in r:
            rows[r["id"]] = r
    for r in rows.values():   # walk 1 kept CoreWLAN's rate; the driver's matches the MCS
        if r.get("driver_rate"):
            r["tx_mbps"] = r["driver_rate"]
    return [r for r in rows.values() if not r.get("invalid") and r.get("rssi") is not None]


def measured_zones(rows: list[dict]) -> tuple[list, list[str]]:
    """For each use, the weakest link signal above which every measured point met the use's criterion."""
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
            zones.append(next(z for z in cv.PRIOR_ZONES if z[1] == name))
        else:
            all_ok = all(ok(r) for r in ranked)
            notes.append(f"{name}: every point at or above {passing:.0f} dBm met it"
                         + (" (all points did: the real limit is lower than measured)" if all_ok else ""))
            zones.append((round(passing, 1), name, color))
    zones.append((-200.0, "unreliable", (215, 60, 50)))
    return zones, notes


def signals(rows: list[dict], plan_data: dict) -> list[dict]:
    """Every signal in the walk with the router it comes from."""
    aps = plan_data.get("access_points") or [{"name": "router", "xy": plan_data["router"], "height_m": plan_data.get("router_height_m", 0.1), "ssids": []}]
    band = next((r.get("link_band") for r in rows if r.get("link_band")), "5")
    out = [{"key": "rssi", "name": f"link to {aps[0]['name']} ({band} GHz)", "ap": 0, "band": band}]
    names = sorted({n for r in rows for n in (r.get("beacons") or {})})
    for name in names:
        ap = next((i for i, a in enumerate(aps) if name in [s.lower() for s in a["ssids"]]), None)
        if ap is None:
            continue
        b = next(r["beacons"][name]["band_ghz"] for r in rows if name in (r.get("beacons") or {}))
        key = f"b:{name}"
        for r in rows:
            r[key] = (r.get("beacons") or {}).get(name, {}).get("rssi_dbm")
        out.append({"key": key, "name": f"{name} ({aps[ap]['name']}, {b} GHz)", "ap": ap, "band": b})
    if any(r.get("ble") is not None for r in rows):
        out.append({"key": "ble", "name": "Bluetooth LE device next to " + aps[0]["name"], "ap": 0, "band": "bt"})
    for s in out:
        s["ap_info"] = aps[s["ap"]]
    return out


def with_geometry(plan: cv.Plan, rows: list[dict], key: str) -> list[dict]:
    out = []
    for r in rows:
        if r.get(key) is None:
            continue
        g = plan.geometry(r["xy"])
        out.append({"id": r["id"], "xy": r["xy"], **g, key: r[key]})
    return out


def best_network_map(plan: cv.Plan, maps: dict[int, np.ndarray], aps: list[dict], out_path: Path, title: str) -> Path:
    """Each place coloured by the router whose network is strongest there."""
    stack = np.stack([np.nan_to_num(m, nan=-999) for m in maps.values()])
    best = np.array(list(maps))[np.argmax(stack, axis=0)]
    strongest = stack.max(axis=0)
    base = np.asarray(Image.open(plan.display_image or plan.image).convert("RGB")).astype(float)
    for ap, color in zip(maps, AP_COLORS):
        area = plan.floor & (best == ap) & (strongest > -998)
        base[area] = 0.55 * base[area] + 0.45 * np.array(AP_COLORS[ap % 3])
    img = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(img)
    font, bold = cv._font(12), cv._font(14)
    for ap in maps:
        x, y = aps[ap]["xy"]
        d.rectangle([x - 7, y - 7, x + 7, y + 7], fill=AP_COLORS[ap % 3], outline=(255, 255, 255), width=2)
    d.rectangle([0, 0, img.width, 24], fill=(255, 255, 255))
    d.text((8, 4), title, fill=(0, 0, 0), font=bold)
    x, y = 8, 28
    d.rectangle([0, 24, img.width, 46], fill=(255, 255, 255))
    for ap in maps:
        d.rectangle([x, y, x + 14, y + 14], fill=AP_COLORS[ap % 3])
        text = f"{aps[ap]['name']} strongest"
        d.text((x + 18, y), text, fill=(0, 0, 0), font=font)
        x += 34 + int(d.textlength(text, font=font))
    img.save(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--walk", required=True)
    parser.add_argument("--doors", default=None)
    parser.add_argument("--plan", default="logs/home/plan.json")
    args = parser.parse_args()

    plan = cv.Plan.load(ROOT / args.plan)
    plan_data = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))
    rows = load_rows(ROOT / args.walk)
    condition = next((r.get("condition") for r in rows if r.get("condition")), "walk")
    height = next((r.get("router_height_m") for r in rows if r.get("router_height_m") is not None), plan.router_height_m)
    out = ROOT / "logs" / "home" / f"report_{condition}_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# Coverage report: {condition}", "", f"{len(rows)} valid points; held out before the walk: {', '.join(plan.holdout)}. "
             f"Method chosen by leave-one-out error on the training points; held-out errors computed once.", ""]

    sigs = signals(rows, plan_data)
    zones, notes = measured_zones(rows)
    results, maps_by_band = {}, {}
    lines += ["## Models", "", "| Signal | Points (train / held out) | Multi-wall: n, dB per wall | Chosen method | LOO RMSE dB | "
              "Held-out RMSE dB (chosen) | Held-out RMSE dB: multi-wall / + residuals / IDW / distance / free space | Gate |",
              "|---|---|---|---|---|---|---|---|"]
    for s in sigs:
        ap = s["ap_info"]
        own = s["ap"] == 0
        ap_plan = plan.for_router(ap["xy"], height if own else ap.get("height_m", 0.1))
        data = with_geometry(ap_plan, rows, s["key"])
        res = cv.compare(ap_plan, data, s["key"])
        results[s["key"]] = res
        if "chosen" not in res:
            lines.append(f"| {s['name']} | {res['train_points']} / {res['test_points']} | too few points | | | | | |")
            continue
        h = {m: res[m]["holdout"].get("rmse_db", "-") for m in cv.METHODS}
        mw = res["multi-wall"]
        lines.append(f"| {s['name']} | {res['train_points']} / {res['test_points']} | {mw['n']}, {mw['wall_db']} | {res['chosen']} | "
                     f"{res[res['chosen']]['loo_rmse_db']} | {h[res['chosen']]} | {' / '.join(str(h[m]) for m in cv.METHODS)} | "
                     f"{'passed' if res['gate_multi_wall'] else 'not passed'} |")
        # Rule written before the walk: a model that fails the gate is not used for the map; interpolation is.
        method = res["chosen"] if res["gate_multi_wall"] else "interpolation (IDW)"
        values = cv.predict_map(ap_plan, res["_model"], method=method, train=res["_train"], key=s["key"])
        is_link = s["key"] == "rssi"
        levels = [-50, -60, -70, -80, -90] if s["band"] == "bt" else cv.LEVELS
        title = f"{s['name']}: {method}, held-out RMSE {h[method]} dB"
        cv.render(ap_plan, values, out / f"map_{s['key'].replace(':', '_')}.png", title, measured=data, key=s["key"],
                  zones=zones if is_link else None, levels=levels)
        if s["key"].startswith("b:"):
            maps_by_band.setdefault(s["band"], {})[s["ap"]] = values
    lines += ["", "Gate (written before the walk): multi-wall held-out RMSE at most 5 dB and lower than every baseline.", ""]

    aps = plan_data.get("access_points", [])
    for band, maps in maps_by_band.items():
        if len(maps) > 1:
            best_network_map(plan, maps, aps, out / f"best_network_{band.replace('.', '')}ghz.png",
                             f"Strongest home network on {band} GHz (predicted)")
            lines.append(f"- best network, {band} GHz: best_network_{band.replace('.', '')}ghz.png")

    lines += ["", f"## What each signal level allowed (link, AWDL off)", "", *[f"- {n}" for n in notes], "",
              "| Point | Distance m | Walls | Signal dBm | SNR dB | MCS | Streams | Rate Mb/s | Standard's floor for this MCS | "
              "Router p95 ms | Loss % | Download Mb/s | BLE dBm |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -(r.get("snr") or -999)):
        mcs = r.get("mcs")
        floor = SENSITIVITY_80[int(mcs)] if mcs is not None and 0 <= int(mcs) < 10 else "-"
        lat = r["latency"]
        lines.append(f"| {r['id']}{'*' if r['id'] in plan.holdout else ''} | {r['distance_m']} | {r['walls']} | {r.get('rssi')} | "
                     f"{r.get('snr')} | {mcs} | {r.get('nss')} | {r.get('tx_mbps')} | {floor} | {lat.get('p95_ms')} | "
                     f"{lat.get('loss_percent')} | {(r.get('throughput') or {}).get('down_mbps', '-')} | {r.get('ble')} |")
    lines += ["", "\\* held out.", ""]

    if args.doors:
        drows = [json.loads(l) for l in (ROOT / args.doors).read_text(encoding="utf-8").splitlines()]
        drows = [r for r in drows if "id" in r]
        lines += ["## Door of the Mac's router room: open against closed", "", "| Point | Link open | Link closed | BLE open | BLE closed |",
                  "|---|---|---|---|---|"]
        diffs = {"rssi": [], "ble": []}
        for pid in sorted({r["id"] for r in drows}):
            o = next((r for r in drows if r["id"] == pid and not r["doors_closed"]), {})
            c = next((r for r in drows if r["id"] == pid and r["doors_closed"]), {})
            for k in diffs:
                if o.get(k) is not None and c.get(k) is not None:
                    diffs[k].append(o[k] - c[k])
            lines.append(f"| {pid} | {o.get('rssi')} | {c.get('rssi')} | {o.get('ble')} | {c.get('ble')} |")
        lines += ["", "Mean loss of the closed door: " + ", ".join(f"{k} {sum(d) / len(d):.1f} dB" for k, d in diffs.items() if d), ""]

    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps({k: {m: v for m, v in r.items() if not m.startswith("_")} for k, r in results.items()},
                                                 indent=1), encoding="utf-8")
    print("\n".join(lines) + f"\nReport and maps: {out.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
