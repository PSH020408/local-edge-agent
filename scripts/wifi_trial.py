"""Which home network is best at this place: ranked from one scan, then, when the ranking is too close, tested by
joining each candidate in turn.

    sudo -v
    python scripts/wifi_trial.py --label "Room C" --rank-only    # ranking only, the connection is not touched
    python scripts/wifi_trial.py --label "Room C"                # ranking, then a test of the closest candidates
    python scripts/wifi_trial.py --label "Room C" --ssids "curi6 5g" curi   # test these networks

Ranking (agent/device/wifi_choice.py): SNR, SINR (co-channel networks heard above the CCA level of -82 dBm share
airtime; weaker ones add to the noise) and the link rate expected from the rate-against-SNR table of walks 1-2.

Test of each network, about 1 minute each, AWDL off (experiment W2):
- join it (networksetup; saved passwords come from the keychain, otherwise you are asked) and time the join;
- link signal, noise and rate at 5 Hz for 10 s, the driver's MCS, streams and channel utilisation (wdutil);
- pings to its router at 5 Hz for 30 s (median, p95, spikes, loss);
- download and upload (networkQuality): this includes the router's own modulation for what it sends and the
  link behind the router, neither of which the Mac can read directly.
The Mac joins the network it started on at the end (or the best one with --keep-best).
Each join drops the connection for a few seconds: do not run this during a call.
Results: logs/home/trial_<label>_<time>.jsonl.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.device import wifi_choice  # noqa: E402
from agent.device.sources import wifi  # noqa: E402
from wifi_walk import AwdlOff, sudo_n, throughput  # noqa: E402

PING_SECONDS, PING_HZ = 30, 5


def wifi_device() -> str:
    out = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True).stdout
    m = re.search(r"Hardware Port: Wi-Fi\nDevice: (\S+)", out)
    return m.group(1) if m else "en0"


def gateway() -> str | None:
    out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    m = re.search(r"gateway:\s*(\S+)", out)
    return m.group(1) if m else None


def join(device: str, ssid: str, password: str | None = None, timeout: float = 30) -> tuple[bool, float, str]:
    """Join `ssid`; True once a router answers and the joined network has that name. networksetup can print an
    error and still exit 0, so success is checked, not assumed."""
    start = time.monotonic()
    command = ["networksetup", "-setairportnetwork", device, ssid] + ([password] if password else [])
    out = subprocess.run(command, capture_output=True, text=True, timeout=60)
    text = (out.stdout + out.stderr).strip()
    if re.search(r"admin|privilege|not permitted", text, re.I):
        out = sudo_n(*command)
        text = (out.stdout + out.stderr).strip()
    if re.search(r"error|fail|could not", text, re.I):
        return False, time.monotonic() - start, text
    while time.monotonic() - start < timeout:
        gw = gateway()
        if gw and subprocess.run(["ping", "-c", "1", "-W", "1000", gw], capture_output=True).returncode == 0:
            name = wifi.current_ssid(ROOT)
            if name is None or name.lower() == ssid.lower():
                return True, time.monotonic() - start, text
        time.sleep(0.5)
    return False, time.monotonic() - start, text or "no router answered"


def measure() -> dict:
    gw = gateway()
    link = wifi.watch(ROOT, 5, 10)
    rssi = [s["rssi_dbm"] for s in link if s.get("rssi_dbm")]
    record: dict = {"gateway": gw}
    if rssi:
        record.update(rssi=round(sum(rssi) / len(rssi), 1), noise=link[0].get("noise_dbm"), channel=link[0].get("channel"),
                      band=link[0].get("band_ghz"), width=link[0].get("width_mhz"))
        if record["noise"]:
            record["snr"] = round(record["rssi"] - record["noise"], 1)
    drv = sudo_n("wdutil", "info")
    if drv.returncode == 0:
        d = wifi.parse_wdutil(drv.stdout)
        record.update(mcs=d.get("mcs"), nss=d.get("nss"), tx_mbps=d.get("tx_mbps"), cca=d.get("cca_percent"))
    if gw:
        count = PING_SECONDS * PING_HZ
        out = subprocess.run(["ping", "-c", str(count), "-i", str(1 / PING_HZ), "-W", "1000", gw], capture_output=True,
                             text=True, timeout=PING_SECONDS + 20).stdout
        parsed = wifi.parse_ping(out)
        if parsed["sent"]:
            record["latency"] = wifi.latency_stats([ms for _, ms in sorted(parsed["replies"].items())], parsed["sent"])
    record["throughput"] = throughput()
    return record


def best_measured(results: list[dict]) -> dict | None:
    """Fastest download among the networks that met the real-time criterion (p95 to the router <= 50 ms, loss
    <= 1%); the fastest of all if none did."""
    ok = [r for r in results if r.get("joined")]
    good = [r for r in ok if (r.get("latency") or {}).get("p95_ms", 999) <= 50 and (r.get("latency") or {}).get("loss_percent", 100) <= 1]
    pool = good or ok
    return max(pool, key=lambda r: (r.get("throughput") or {}).get("down_mbps", 0)) if pool else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="here", help="name of the place, for the log")
    ap.add_argument("--ssids", nargs="+", help="networks to test (default: the current one and the closest candidates)")
    ap.add_argument("--rank-only", action="store_true", help="rank from one scan; do not change networks")
    ap.add_argument("--keep-best", action="store_true", help="stay on the best network at the end")
    ap.add_argument("--max", type=int, default=3, help="networks to test at most (default 3)")
    args = ap.parse_args()

    device = wifi_device()
    known = wifi_choice.parse_preferred(subprocess.run(["networksetup", "-listpreferredwirelessnetworks", device],
                                                       capture_output=True, text=True).stdout)
    start_ssid = wifi.current_ssid(ROOT)
    link = wifi.link(ROOT)
    print(f"Wi-Fi device {device}; joined: {start_ssid or 'unknown'}; saved networks: {len(known)}")
    print("Scanning (about 25 s) ...")
    nets = wifi.scan(ROOT) + wifi.scan(ROOT)      # two scans: one hears about 4 of 6 home networks (walk 2)
    cands = wifi_choice.candidates(nets, link.get("noise_dbm") or -93, link.get("width_mhz") or 80,
                                   known or None, start_ssid)
    choice = wifi_choice.decide(cands)
    print(f"\n{'network':14} {'band':>5} {'ch':>4} {'signal':>7} {'SNR':>5} {'SINR':>5} {'worst':>6} {'shared':>6} {'rate':>6}")
    for c in cands:
        mark = " <- joined" if c.current else ""
        print(f"{c.ssid[:14]:14} {c.band_ghz:>5} {c.channel:>4} {c.signal:>7.0f} {c.snr:>5.0f} {c.sinr:>5.0f} "
              f"{c.sinr_worst:>6.0f} {c.shared:>6} {c.rate:>6.0f}{mark}")
    print(f"\nRanking: {choice.action.upper()} - {choice.reason}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "logs" / "home" / f"trial_{re.sub(r'[^A-Za-z0-9]+', '-', args.label).strip('-')}_{stamp}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = {"label": args.label, "time": datetime.now().isoformat(timespec="seconds"), "start_ssid": start_ssid}
    with out_path.open("a") as fh:
        fh.write(json.dumps({**base, "kind": "ranking", "action": choice.action, "reason": choice.reason,
                             "candidates": [c.__dict__ for c in cands]}) + "\n")
    if args.rank_only:
        print(f"Saved: {out_path.relative_to(ROOT)}")
        return

    if args.ssids:
        todo = args.ssids
    else:
        todo = ([start_ssid] if start_ssid else []) + [c.ssid for c in cands if c.ssid != start_ssid]
    todo = todo[:args.max]
    if sudo_n("true").returncode != 0:
        sys.exit("Run `sudo -v` first (wdutil and AWDL need it).")
    print(f"\nTesting {len(todo)} networks, about 1 minute each: {', '.join(todo)}")
    results = []
    with AwdlOff():
        for ssid in todo:
            print(f"\n- {ssid}: joining ...", flush=True)
            ok, seconds, text = join(device, ssid)
            if not ok and re.search(r"password|auth|could not|fail", text, re.I):
                password = getpass.getpass(f"  password for {ssid} (not stored, Enter to skip): ")
                if password:
                    ok, seconds, text = join(device, ssid, password)
            record = {**base, "kind": "test", "ssid": ssid, "joined": ok, "join_seconds": round(seconds, 1)}
            if ok:
                print(f"  joined in {seconds:.1f} s; measuring ...", flush=True)
                record.update(measure())
                lat, tp = record.get("latency") or {}, record.get("throughput") or {}
                print(f"  signal {record.get('rssi')} dBm, SNR {record.get('snr')} dB, MCS {record.get('mcs')}, "
                      f"p95 {lat.get('p95_ms')} ms, loss {lat.get('loss_percent')}%, "
                      f"down {tp.get('down_mbps')} / up {tp.get('up_mbps')} Mb/s")
            else:
                print(f"  could not join: {text[:120]}")
            results.append(record)
            with out_path.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
        best = best_measured(results)
        back = best["ssid"] if (args.keep_best and best) else start_ssid
        if back:
            print(f"\nJoining {back} ...")
            ok, _, text = join(device, back)
            if not ok:
                print(f"  could not join {back} ({text[:80]}); join it from the Wi-Fi menu.")
    if best:
        tp = best.get("throughput") or {}
        print(f"\nBest measured here: {best['ssid']} (down {tp.get('down_mbps')} Mb/s, "
              f"p95 {(best.get('latency') or {}).get('p95_ms')} ms). Ranking said: {choice.action} "
              f"{choice.best.ssid if choice.best else ''}.")
    print(f"Saved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
