"""Coverage walk: Wi-Fi (5 GHz link, 2.4 and 5 GHz beacons) and Bluetooth measured at the points of a floor plan.

    python scripts/wifi_walk.py --plan logs/home/plan.json              # the walk, about 25 minutes
    python scripts/wifi_walk.py --plan logs/home/plan.json --resume     # continue the last walk
    python scripts/wifi_walk.py --plan logs/home/plan.json --doors      # door test: open and closed, about 5 minutes

At each point the Mac is put down twice, about 30 cm apart (the 5 GHz wavelength is 6 cm, so two placements
average out the fast fading), 10 s each, as decided in experiment W1:
- the 5 GHz link at 10 Hz (CoreWLAN) and pings to the router at 5 Hz
- the signal of a Bluetooth speaker or headset left next to the router, every second
then one scan (the router's 2.4 GHz and 5 GHz beacons at the same place) and the driver readings (MCS, streams,
rate, noise). AWDL is kept off during the walk (experiment W2: it causes latency spikes), so the latency at each
point shows the radio conditions; it is switched back on at the end.

Before the walk: all interior doors open (or as stated with --doors), the Mac at the same height at every
point (a chair), the screen facing the same way, and you standing behind it while it measures.
Results: logs/home/walk_<time>.jsonl; the report and maps: python scripts/coverage_report.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.coverage import Plan  # noqa: E402
from agent.device.sources import bluetooth, wifi  # noqa: E402

SECONDS, PING_HZ = 10, 5


def sudo_n(*args):
    return subprocess.run(["sudo", "-n", *args], capture_output=True, text=True, timeout=30)


def router_ip() -> str:
    out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    m = re.search(r"gateway:\s*(\S+)", out)
    if not m:
        sys.exit("Not connected: no default router.")
    return m.group(1)


class AwdlOff:
    """AWDL down for the walk; a watcher takes it down again when macOS brings it back (W2, pairs 7 and 8)."""

    def __enter__(self):
        self.stop, self.reenabled = threading.Event(), 0
        sudo_n("ifconfig", "awdl0", "down")
        threading.Thread(target=self._watch, daemon=True).start()
        return self

    def _watch(self):
        while not self.stop.wait(2):
            out = subprocess.run(["ifconfig", "awdl0"], capture_output=True, text=True).stdout
            if "status: active" in out:
                self.reenabled += 1
                sudo_n("ifconfig", "awdl0", "down")

    def __exit__(self, *exc):
        self.stop.set()
        sudo_n("ifconfig", "awdl0", "up")
        return False


def placement(gateway: str, bt_name: str | None) -> dict:
    out: dict = {"bt": []}

    def bt_poll():
        end = time.monotonic() + SECONDS
        while time.monotonic() < end:
            device = bluetooth.pick(bluetooth.connected(), bt_name)
            out["bt"].append(device["rssi_dbm"] if device else None)
            time.sleep(1)

    def do_ping():
        text = subprocess.run(["ping", "-c", str(SECONDS * PING_HZ), "-i", str(1 / PING_HZ), "-W", "1000", gateway],
                              capture_output=True, text=True, timeout=SECONDS + 15).stdout
        out["ping"] = wifi.parse_ping(text)

    threads = [threading.Thread(target=do_ping), threading.Thread(target=bt_poll)]
    for t in threads:
        t.start()
    out["link"] = wifi.watch(ROOT, 10, SECONDS)
    for t in threads:
        t.join()
    return out


def identify_router(nets: list[dict], link: dict) -> dict:
    """The router's own networks, from a scan made next to it: on 5 GHz the strongest network on the link's
    channel; on 2.4 GHz the strongest network whose name shares the 5 GHz name's stem (else the strongest)."""
    five = [n for n in nets if n.get("band_ghz") == link.get("band_ghz") and n.get("channel") == link.get("channel")]
    r5 = max(five, key=lambda n: n["rssi_dbm"]) if five else None
    stem = re.sub(r"[-_ ]?5\s?g(hz)?$", "", (r5 or {}).get("ssid", ""), flags=re.I).lower()
    twos = [n for n in nets if n.get("band_ghz") == "2.4"]
    same = [n for n in twos if stem and n.get("ssid", "").lower().startswith(stem[:4])]
    r24 = max(same or twos, key=lambda n: n["rssi_dbm"]) if (same or twos) else None
    key = lambda n: None if n is None else {"bssid": n.get("bssid") or None, "ssid": n.get("ssid"), "band_ghz": n.get("band_ghz"),
                                            "channel": n.get("channel")}
    return {"5": key(r5), "2.4": key(r24)}


def find(nets: list[dict], ident: dict | None) -> int | None:
    if not ident:
        return None
    for n in nets:
        if ident.get("bssid") and n.get("bssid") == ident["bssid"]:
            return n["rssi_dbm"]
    same = [n for n in nets if n.get("ssid") == ident.get("ssid") and n.get("band_ghz") == ident.get("band_ghz")]
    return max(n["rssi_dbm"] for n in same) if same else None


def summarise(point_id: str, plan: Plan, placements: list[dict], nets: list[dict], driver: dict, routers: dict,
              doors_closed: int = 0) -> dict:
    p = plan.points[point_id]
    rssi = [[s["rssi_dbm"] for s in pl["link"] if s.get("rssi_dbm")] for pl in placements]
    means = [statistics.fmean(v) for v in rssi if v]
    noise = [s["noise_dbm"] for pl in placements for s in pl["link"] if s.get("noise_dbm")]
    replies = [ms for pl in placements for _, ms in sorted(pl["ping"]["replies"].items())]
    sent = sum(pl["ping"]["sent"] for pl in placements)
    bt = [v for pl in placements for v in pl["bt"]]
    bt_ok = [v for v in bt if v is not None]
    row = {"id": point_id, "label": p.get("label", ""), "xy": p["xy"], **plan.geometry(p["xy"]),
           "doors_closed": doors_closed, "time": datetime.now().isoformat(timespec="seconds"),
           "rssi": round(statistics.fmean(means), 2) if means else None,
           "rssi_placements": [round(m, 2) for m in means],
           "rssi_spread": round(statistics.pstdev([x for v in rssi for x in v]), 2) if sum(map(len, rssi)) > 1 else None,
           "noise": statistics.median(noise) if noise else None,
           "tx_mbps": placements[-1]["link"][-1].get("tx_mbps") if placements[-1]["link"] else None,
           "phy": placements[-1]["link"][-1].get("phy") if placements[-1]["link"] else None,
           "mcs": driver.get("mcs"), "nss": driver.get("nss"), "driver_rate": driver.get("tx_mbps"), "cca": driver.get("cca_percent"),
           "scan_5": find(nets, routers.get("5")), "scan_24": find(nets, routers.get("2.4")),
           "bt": round(statistics.fmean(bt_ok), 1) if bt_ok else None,
           "bt_connected_share": round(len(bt_ok) / len(bt), 2) if bt else None,
           "latency": wifi.latency_stats(replies, sent)}
    if row["rssi"] is not None and row["noise"] is not None:
        row["snr"] = round(row["rssi"] - row["noise"], 1)
    return row


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", default="logs/home/plan.json")
    parser.add_argument("--resume", action="store_true", help="continue the most recent walk")
    parser.add_argument("--doors", action="store_true", help="door test at the plan's door points")
    parser.add_argument("--bt", default=None, help="part of the Bluetooth device's name (default: the only connected audio device)")
    args = parser.parse_args()

    plan = Plan.load(ROOT / args.plan)
    folder = (ROOT / args.plan).parent
    link = wifi.link(ROOT)
    if not link.get("rssi_dbm"):
        sys.exit("Wi-Fi is off or not connected.")
    print("The password is asked once (driver readings, AWDL).", flush=True)
    subprocess.run(["sudo", "-v"], check=True)

    def keep_sudo():
        while True:
            time.sleep(60)
            subprocess.run(["sudo", "-n", "-v"], capture_output=True)
    threading.Thread(target=keep_sudo, daemon=True).start()
    awake = subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
    gateway = router_ip()

    device = bluetooth.pick(bluetooth.connected(), args.bt)
    if device is None:
        print("No Bluetooth audio device found connected: connect the speaker next to the router (or pass --bt NAME); "
              "the walk continues without Bluetooth.", flush=True)
    else:
        print(f"Bluetooth: following '{device['name']}' ({device['kind']}), signal now {device['rssi_dbm']} dBm"
              + ("" if device["rssi_dbm"] is not None else " (macOS gives no signal for it: Bluetooth will be blank)"), flush=True)
    bt_name = device["name"] if device else args.bt

    if args.doors:
        points = [(pid, 0) for pid in plan.points if pid.startswith("D")]
        points = [x for pid, _ in points for x in ((pid, 0), (pid, 1))]
        log = folder / f"doors_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    else:
        order = plan.order or list(plan.points)
        points = [(pid, 0) for pid in order if not pid.startswith("D")]
        logs = sorted(folder.glob("walk_*.jsonl"))
        log = logs[-1] if args.resume and logs else folder / f"walk_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    done, routers = set(), {}
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("kind") == "routers":
                routers = rec["routers"]
            elif "id" in rec:
                done.add((rec["id"], rec.get("doors_closed", 0)))
    todo = [p for p in points if p not in done]
    print(f"{len(todo)} measurements to go ({len(done)} already in {log.name}). AWDL is off until the end. "
          f"Enter = measure, s = skip, q = stop (the rest can be measured with --resume).", flush=True)

    with AwdlOff() as awdl:
        for k, (pid, closed) in enumerate(todo, 1):
            label = plan.points[pid].get("label", "")
            door = "" if not args.doors else (" — door CLOSED" if closed else " — door OPEN")
            answer = ask(f"\n[{k}/{len(todo)}] Point {pid} {label}{door}: put the Mac there, step behind it, press Enter ")
            if answer == "q":
                break
            if answer == "s":
                continue
            first = placement(gateway, bt_name)
            placements = [first]
            if not args.doors:
                if ask("  Move the Mac about 30 cm (same height), press Enter ") == "q":
                    break
                placements.append(placement(gateway, bt_name))
            print("  scanning (13 s) ...", flush=True)
            nets = wifi.scan(ROOT)
            if not routers:
                routers = identify_router(nets, wifi.link(ROOT))
                print(f"  router networks: 5 GHz '{(routers['5'] or {}).get('ssid')}', 2.4 GHz '{(routers['2.4'] or {}).get('ssid')}'",
                      flush=True)
                if ask("  Are these your router's two networks? [Enter = yes, n = no] ") == "n":
                    twos = [n for n in nets if n.get("band_ghz") == "2.4"]
                    for i, n in enumerate(twos):
                        print(f"   {i}: {n.get('ssid')} ({n['rssi_dbm']} dBm)")
                    pick = ask("  Number of your 2.4 GHz network: ")
                    if pick.isdigit() and int(pick) < len(twos):
                        n = twos[int(pick)]
                        routers["2.4"] = {"bssid": n.get("bssid") or None, "ssid": n.get("ssid"), "band_ghz": "2.4", "channel": n.get("channel")}
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"kind": "routers", "routers": routers}) + "\n")
            done_drv = sudo_n("wdutil", "info")
            driver = wifi.parse_wdutil(done_drv.stdout) if done_drv.returncode == 0 else {}
            row = summarise(pid, plan, placements, nets, driver, routers, closed)
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            lat = row["latency"]
            print(f"  {row['distance_m']} m, {row['walls']} walls: 5 GHz {row['rssi']} dBm (SNR {row.get('snr')}, MCS {row['mcs']}, "
                  f"{row['tx_mbps']} Mb/s), 2.4 GHz {row['scan_24']} dBm, Bluetooth {row['bt']} dBm; "
                  f"router p95 {lat.get('p95_ms')} ms, loss {lat.get('loss_percent')}%", flush=True)
            if row["rssi_placements"] and len(row["rssi_placements"]) == 2:
                gap = abs(row["rssi_placements"][0] - row["rssi_placements"][1])
                if gap > 6:
                    print(f"  note: the two placements differ by {gap:.1f} dB (a deep fade or the body in the way)", flush=True)
        print(f"\nAWDL switched back on (macOS re-enabled it {awdl.reenabled} times during the walk).", flush=True)
    awake.terminate()
    print(f"Saved: {log.relative_to(ROOT)}\nNext: python scripts/coverage_report.py --walk {log.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
