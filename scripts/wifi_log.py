"""Wi-Fi baseline log (experiment W3): the link and the network path, once a minute, for an hour or more.

    python scripts/wifi_log.py --minutes 60              # asks for the password once
    python scripts/wifi_log.py --minutes 60 --no-throughput

Why: the anomaly check of Stage 8 compares a reading with this Mac's usual values on its usual network, and
W1-W2 were a few minutes on one evening. Each round (every 60 s) records, with the durations decided in W1:
- the link for 10 s at 10 Hz (CoreWLAN): mean signal and its spread, noise, rate, channel
- pings to the router and to the internet for 10 s at 5 Hz: median, p95, jitter, spikes, loss
- AWDL state at the start and end of the pings (W2: AWDL causes the spikes on this Mac)
- DNS lookup time; driver readings (wdutil, after the pings so the Mac is idle): channel utilisation, streams
Every 10 minutes a scan of nearby networks, and every 15 minutes networkQuality (about 500 MB each), each in its
own slot so they do not disturb the pings.

Readings go to the device store (logs/device.db, names wifi.* and net.*); every round also goes to
logs/wireless/log_<time>.jsonl with the raw series. Keep the Mac plugged in, lid open, on its usual network;
use the network as usual (that is the baseline) or leave it alone, and say which.
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
import tomllib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.readings import reading  # noqa: E402
from agent.device.sources import wifi  # noqa: E402
from agent.device.store import Store  # noqa: E402

PING_HZ, PING_S, LINK_S = 5, 10, 10


def sudo_n(*args, timeout=20):
    return subprocess.run(["sudo", "-n", *args], capture_output=True, text=True, timeout=timeout)


def router() -> str | None:
    out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    m = re.search(r"gateway:\s*(\S+)", out)
    return m.group(1) if m else None


def awdl_active() -> int | None:
    out = subprocess.run(["ifconfig", "awdl0"], capture_output=True, text=True).stdout
    if not out:
        return None
    return int(("<UP," in out or "<UP>" in out) and "status: active" in out)


def ping(host: str) -> dict:
    out = subprocess.run(["ping", "-c", str(PING_HZ * PING_S), "-i", str(1 / PING_HZ), "-W", "1000", host],
                         capture_output=True, text=True, timeout=PING_S + 15).stdout
    parsed = wifi.parse_ping(out)
    times = [ms for _, ms in sorted(parsed["replies"].items())]
    return {"stats": wifi.latency_stats(times, parsed["sent"]), "series": times}


def dns_ms() -> float | None:
    times = []
    for host in [f"w3-{int(time.time())}.example.com", "apple.com"]:
        out = subprocess.run(["dig", "+tries=1", "+time=3", host], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"Query time: (\d+) msec", out)
        if m:
            times.append(float(m.group(1)))
    return statistics.median(times) if times else None


def path_readings(prefix: str, stats: dict, t: str) -> list:
    return [reading(f"net.{prefix}_median", stats.get("median_ms"), "ms", t),
            reading(f"net.{prefix}_p95", stats.get("p95_ms"), "ms", t),
            reading(f"net.{prefix}_jitter", stats.get("jitter_ms"), "ms", t),
            reading(f"net.{prefix}_spikes", None if stats.get("spike_share") is None else round(100 * stats["spike_share"], 1), "%", t),
            reading(f"net.{prefix}_loss", stats.get("loss_percent"), "%", t)]


def round_once(gateway: str | None) -> tuple[dict, list]:
    t = datetime.now().isoformat(timespec="seconds")
    row = {"time": t, "awdl_start": awdl_active()}
    results = {}
    threads = [threading.Thread(target=lambda: results.update(link=wifi.watch(ROOT, 10, LINK_S))),
               threading.Thread(target=lambda: results.update(internet=ping("1.1.1.1")))]
    if gateway:
        threads.append(threading.Thread(target=lambda: results.update(router=ping(gateway))))
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    row["awdl_end"] = awdl_active()
    samples = results.get("link", [])
    values = [s["rssi_dbm"] for s in samples if s.get("rssi_dbm")]
    first = samples[0] if samples else {}
    row["link"] = {"rssi_mean": round(statistics.fmean(values), 2) if values else None,
                   "rssi_sigma": round(statistics.pstdev(values), 2) if len(values) > 1 else None,
                   "noise": first.get("noise_dbm"), "tx_mbps": first.get("tx_mbps"), "channel": first.get("channel"),
                   "band_ghz": first.get("band_ghz"), "width_mhz": first.get("width_mhz"), "phy": first.get("phy")}
    row["router"] = results.get("router", {}).get("stats", {})
    row["internet"] = results["internet"]["stats"]
    row["router_series"] = results.get("router", {}).get("series", [])
    row["dns_ms"] = dns_ms()
    done = sudo_n("wdutil", "info")
    row["driver"] = wifi.parse_wdutil(done.stdout) if done.returncode == 0 else {}
    link, drv = row["link"], row["driver"]
    awdl = [v for v in (row["awdl_start"], row["awdl_end"]) if v is not None]
    readings = [reading("wifi.rssi", link["rssi_mean"], "dBm", t), reading("wifi.rssi_spread", link["rssi_sigma"], "dB", t),
                reading("wifi.noise", link["noise"], "dBm", t), reading("wifi.tx_rate", link["tx_mbps"], "Mb/s", t),
                reading("wifi.channel", link["channel"], "code", t), reading("wifi.band", link["band_ghz"], "text", t),
                reading("wifi.width", link["width_mhz"], "MHz", t),
                reading("wifi.cca", drv.get("cca_percent"), "%", t), reading("wifi.streams", drv.get("nss"), "count", t),
                reading("wifi.mcs", drv.get("mcs"), "code", t),
                reading("wifi.awdl_active", max(awdl) if awdl else None, "flag", t),
                reading("net.dns", row["dns_ms"], "ms", t)]
    readings += path_readings("router", row["router"], t) + path_readings("internet", row["internet"], t)
    return row, readings


def scan_summary() -> dict:
    nets = wifi.scan(ROOT)
    me = wifi.link(ROOT)
    same = [n for n in nets if n.get("channel") == me.get("channel") and n.get("band_ghz") == me.get("band_ghz")]
    bands = {}
    for n in nets:
        bands[n.get("band_ghz")] = bands.get(n.get("band_ghz"), 0) + 1
    return {"networks": len(nets), "per_band": bands, "same_channel": len(same),
            "same_channel_signals": sorted((n["rssi_dbm"] for n in same), reverse=True),
            "open_networks": sum(bool(n.get("open")) for n in nets)}


def throughput() -> dict:
    out = subprocess.run(["networkQuality", "-c"], capture_output=True, text=True, timeout=120).stdout
    try:
        data = json.loads(out)
    except ValueError:
        return {}
    return {"down_mbps": round(data.get("dl_throughput", 0) / 1e6, 1), "up_mbps": round(data.get("ul_throughput", 0) / 1e6, 1),
            "responsiveness": round(data.get("responsiveness", 0), 1), "base_rtt_ms": round(data.get("base_rtt", 0), 1)}


def block_table(rows: list[dict], minutes: int = 10) -> list[str]:
    lines = ["| Minutes | Rounds | Signal dBm | Router median ms | Router p95 ms | Router spikes % | AWDL active % | "
             "Internet p95 ms | DNS ms | CCA % |", "|---|---|---|---|---|---|---|---|---|---|"]
    t0 = datetime.fromisoformat(rows[0]["time"])
    blocks: dict[int, list[dict]] = {}
    for r in rows:
        blocks.setdefault(int((datetime.fromisoformat(r["time"]) - t0).total_seconds() // (60 * minutes)), []).append(r)

    def mean(values):
        values = [v for v in values if v is not None]
        return round(statistics.fmean(values), 1) if values else "-"
    for k, rs in sorted(blocks.items()):
        lines.append(f"| {k * minutes}-{(k + 1) * minutes} | {len(rs)} | {mean(r['link']['rssi_mean'] for r in rs)} | "
                     f"{mean(r['router'].get('median_ms') for r in rs)} | {mean(r['router'].get('p95_ms') for r in rs)} | "
                     f"{mean(None if r['router'].get('spike_share') is None else 100 * r['router']['spike_share'] for r in rs)} | "
                     f"{mean(100 * max(r['awdl_start'] or 0, r['awdl_end'] or 0) for r in rs)} | "
                     f"{mean(r['internet'].get('p95_ms') for r in rs)} | {mean(r['dns_ms'] for r in rs)} | "
                     f"{mean(r['driver'].get('cca_percent') for r in rs)} |")
    return lines


def awdl_split(rows: list[dict]) -> list[str]:
    """Rounds with AWDL active at both ends against rounds with it inactive at both ends."""
    groups = {"active": [r for r in rows if r["awdl_start"] == 1 and r["awdl_end"] == 1],
              "inactive": [r for r in rows if r["awdl_start"] == 0 and r["awdl_end"] == 0]}
    lines = ["| AWDL | Rounds | Router p95 ms (median of rounds) | Router spikes % (mean) | Router jitter ms (mean) |", "|---|---|---|---|---|"]
    for name, rs in groups.items():
        p95 = [r["router"].get("p95_ms") for r in rs if r["router"].get("p95_ms") is not None]
        sp = [100 * r["router"]["spike_share"] for r in rs if r["router"].get("spike_share") is not None]
        jt = [r["router"].get("jitter_ms") for r in rs if r["router"].get("jitter_ms") is not None]
        lines.append(f"| {name} | {len(rs)} | {round(statistics.median(p95), 1) if p95 else '-'} | "
                     f"{round(statistics.fmean(sp), 1) if sp else '-'} | {round(statistics.fmean(jt), 1) if jt else '-'} |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--no-throughput", action="store_true", help="skip networkQuality (about 500 MB per test)")
    args = parser.parse_args()

    if not wifi.link(ROOT).get("rssi_dbm"):
        sys.exit("Wi-Fi is off or not connected.")
    print("The password is asked once and kept alive for the driver readings.", flush=True)
    subprocess.run(["sudo", "-v"], check=True)

    def keep_sudo():
        while True:
            time.sleep(60)
            subprocess.run(["sudo", "-n", "-v"], capture_output=True)
    threading.Thread(target=keep_sudo, daemon=True).start()
    awake = subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])

    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8")).get("device", {})
    store = Store(ROOT / cfg.get("store", "logs/device.db"), keep_days=cfg.get("keep_days", 7))
    folder = ROOT / "logs" / "wireless"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = folder / f"log_{stamp}.jsonl"
    started, rows, extras = time.monotonic(), [], []
    last_scan = last_nq = -1e9
    print(f"Logging for {args.minutes:.0f} minutes, one round a minute. Ctrl+C stops early and still writes the report.", flush=True)
    try:
        while time.monotonic() - started < args.minutes * 60:
            round_start = time.monotonic()
            gateway = router()
            try:
                row, readings = round_once(gateway)
                store.write(readings)
                rows.append(row)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                print(f"{row['time'][11:16]}  signal {row['link']['rssi_mean']} dBm  router p95 {row['router'].get('p95_ms')} ms  "
                      f"spikes {row['router'].get('spike_share')}  AWDL {row['awdl_start']}/{row['awdl_end']}  "
                      f"internet p95 {row['internet'].get('p95_ms')} ms  DNS {row['dns_ms']} ms  CCA {row['driver'].get('cca_percent')}%", flush=True)
            except Exception as error:  # one failed round must not end an hour of logging
                print(f"round failed: {error}", flush=True)
            # extra measurements in the rest of the minute, never during the pings
            elapsed = time.monotonic() - started
            extra = None
            if elapsed - last_scan >= 600:
                extra, last_scan = {"kind": "scan", **scan_summary()}, elapsed
            elif not args.no_throughput and elapsed - last_nq >= 900:
                extra, last_nq = {"kind": "throughput", **throughput()}, elapsed
            if extra:
                extra["time"] = datetime.now().isoformat(timespec="seconds")
                extras.append(extra)
                t = extra["time"]
                if extra["kind"] == "scan":
                    store.write([reading("wifi.networks_seen", extra["networks"], "count", t),
                                 reading("wifi.same_channel", extra["same_channel"], "count", t)])
                else:
                    store.write([reading("net.down", extra.get("down_mbps"), "Mb/s", t), reading("net.up", extra.get("up_mbps"), "Mb/s", t),
                                 reading("net.responsiveness", extra.get("responsiveness"), "count", t),
                                 reading("net.base_rtt", extra.get("base_rtt_ms"), "ms", t)])
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(extra) + "\n")
                print(f"{t[11:16]}  {extra}", flush=True)
            time.sleep(max(0.0, 60 - (time.monotonic() - round_start)))
    except KeyboardInterrupt:
        print("Stopped early.", flush=True)
    finally:
        awake.terminate()
        store.close()

    if not rows:
        sys.exit("No round was recorded.")
    lines = [f"# Wi-Fi baseline log W3, {stamp}", "", f"{len(rows)} rounds over {(time.monotonic() - started) / 60:.0f} minutes. "
             f"Link: {rows[0]['link']['band_ghz']} GHz channel {rows[0]['link']['channel']}, {rows[0]['link']['width_mhz']} MHz, "
             f"{rows[0]['link']['phy']}.", "", "## By 10 minutes", ""] + block_table(rows) + \
            ["", "## Rounds by AWDL state", ""] + awdl_split(rows) + ["", "## Scans and throughput", ""] + \
            [f"- {e['time'][11:16]} {e['kind']}: " + ", ".join(f"{k} {v}" for k, v in e.items() if k not in ("kind", "time")) for e in extras]
    report = folder / f"log_{stamp}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\n\nReport: {report.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
