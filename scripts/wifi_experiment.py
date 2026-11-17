"""Wi-Fi experiment W1: how long to measure, and whether AWDL causes the latency spikes.

    python scripts/wifi_experiment.py          # W1, about 4 minutes; asks for the password once
    python scripts/wifi_experiment.py --awdl 8 # W2: AWDL on and off in 8 random-order pairs, about 6 minutes

Keep the Mac still, in its usual place, on its usual network; nothing else using the network.

Questions (from the wireless probe of 2026-11-17):
1. How often does the signal reading update, how much does it vary at a fixed place, and how long must it be
   averaged for ±1 dB? 20 readings in 46 ms were all the same value.
2. How long must the latency be measured for a stable 95th percentile and spike share? (60 s at 5 Hz, cut into
   windows of 5-30 s and compared with the whole.)
3. Do the spikes to the router (up to 102 ms, jitter 25 ms) come from AWDL, which takes the radio off the
   channel for AirDrop and Continuity? Pings with AWDL on, off, on (A-B-A, 30 s each). AirDrop pauses for
   30 s; AWDL is switched back on at the end, also after an error.
4. Channel utilisation (CCA) and latency under load (networkQuality running).

Report: logs/wireless/experiment_w1_<time>.md and .json (not committed).
"""

from __future__ import annotations

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

from agent.device.sources import wifi  # noqa: E402

PING_HZ = 5


def sudo(*args, timeout=30) -> subprocess.CompletedProcess:
    return subprocess.run(["sudo", "-n", *args], capture_output=True, text=True, timeout=timeout)


def router() -> str:
    out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
    m = re.search(r"gateway:\s*(\S+)", out)
    if not m:
        sys.exit("No default router: connect to Wi-Fi first.")
    return m.group(1)


def ping(host: str, seconds: float) -> dict:
    count = int(seconds * PING_HZ)
    out = subprocess.run(["ping", "-c", str(count), "-i", str(1 / PING_HZ), "-W", "1000", host],
                         capture_output=True, text=True, timeout=seconds + 15).stdout
    parsed = wifi.parse_ping(out)
    series = [(seq / PING_HZ, ms) for seq, ms in sorted(parsed["replies"].items())]
    return {"series": series, "stats": wifi.latency_stats([ms for _, ms in series], parsed["sent"])}


def wdutil_reading() -> dict:
    done = sudo("wdutil", "info")
    return wifi.parse_wdutil(done.stdout) if done.returncode == 0 else {}


def awdl_state() -> str:
    out = subprocess.run(["ifconfig", "awdl0"], capture_output=True, text=True).stdout
    m = re.search(r"status:\s*(\w+)", out)
    up = "<UP," in out or "<UP>" in out
    return f"{'up' if up else 'down'}/{m.group(1) if m else '?'}"


def part_signal(router_ip: str) -> dict:
    print("1/4  Signal at 10 Hz and pings at 5 Hz, 60 s ...", flush=True)
    result = {}
    t = threading.Thread(target=lambda: result.update(ping=ping(router_ip, 60)))
    t.start()
    samples = wifi.watch(ROOT, 10, 60)
    t.join()
    t0 = samples[0]["t"] if samples else 0
    series = [(round(s["t"] - t0, 3), float(s["rssi_dbm"])) for s in samples]
    values = [v for _, v in series]
    dt = (series[-1][0] - series[0][0]) / (len(series) - 1) if len(series) > 1 else 0.1
    sigma = statistics.pstdev(values) if values else None
    period = wifi.update_period(series)
    tau = wifi.correlation_time(values, dt)
    rssi = {"samples": len(values), "mean_dbm": round(statistics.fmean(values), 2) if values else None,
            "sigma_db": round(sigma, 2) if sigma is not None else None, "min": min(values, default=None),
            "max": max(values, default=None), "distinct_values": len(set(values)), "update_period_s": period,
            "correlation_time_s": tau,
            "seconds_for_1db": wifi.seconds_for_mean(sigma, tau) if sigma and tau else None,
            "seconds_for_0_5db": wifi.seconds_for_mean(sigma, tau, 0.5) if sigma and tau else None,
            "windows_mean": wifi.window_spread(series, [1, 2, 5, 10, 20, 30], lambda v: sum(v) / len(v)),
            "noise_dbm": sorted({s["noise_dbm"] for s in samples}), "tx_mbps": sorted({s["tx_mbps"] for s in samples}),
            "channel": samples[0].get("channel") if samples else None, "band_ghz": samples[0].get("band_ghz") if samples else None,
            "width_mhz": samples[0].get("width_mhz") if samples else None, "phy": samples[0].get("phy") if samples else None}
    lat = result["ping"]
    p95 = lambda v: wifi.percentile(v, 0.95)
    spikes = lambda v: sum(x > 50 for x in v) / len(v)
    latency = {"stats": lat["stats"],
               "windows_p95": wifi.window_spread(lat["series"], [5, 10, 20, 30], p95),
               "windows_median": wifi.window_spread(lat["series"], [5, 10, 20, 30], lambda v: wifi.percentile(v, 0.5)),
               "windows_spike_share": wifi.window_spread(lat["series"], [5, 10, 20, 30], spikes)}
    return {"rssi": rssi, "rssi_series": series, "latency": latency, "latency_series": lat["series"]}


def part_awdl(router_ip: str) -> dict:
    print("2/4  AWDL on, off, on: pings 30 s each (AirDrop pauses for 30 s) ...", flush=True)
    phases = {}
    try:
        phases["on (before)"] = dict(ping(router_ip, 30), awdl=awdl_state())
        sudo("ifconfig", "awdl0", "down")
        states = []
        watcher_stop = threading.Event()

        def watch_state():
            while not watcher_stop.is_set():
                states.append(awdl_state())
                watcher_stop.wait(5)
        w = threading.Thread(target=watch_state, daemon=True)
        w.start()
        phases["off"] = ping(router_ip, 30)
        watcher_stop.set()
        w.join()
        phases["off"]["awdl"] = ", ".join(states)
    finally:
        sudo("ifconfig", "awdl0", "up")
    phases["on (after)"] = dict(ping(router_ip, 30), awdl=awdl_state())
    return {name: {"awdl": p["awdl"], **p["stats"]} for name, p in phases.items()} | {
        "_series": {name: p["series"] for name, p in phases.items()}}


def part_wdutil() -> list[dict]:
    print("3/4  Driver readings at rest (wdutil, 3 readings) ...", flush=True)
    return [wdutil_reading() for _ in range(3)]


def part_load(router_ip: str) -> dict:
    print("4/4  Under load: networkQuality with pings and driver readings, about 25 s ...", flush=True)
    result = {"wdutil": []}
    nq = subprocess.Popen(["networkQuality", "-c"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    time.sleep(2)
    t = threading.Thread(target=lambda: result.update(ping=ping(router_ip, 15)))
    t.start()
    while t.is_alive():
        reading = wdutil_reading()
        if reading:
            result["wdutil"].append(reading)
    out, _ = nq.communicate(timeout=90)
    try:
        data = json.loads(out)
        result["networkquality"] = {k: (round(v / 1e6, 1) if "throughput" in k else round(v, 1))
                                    for k, v in data.items() if isinstance(v, (int, float))}
    except ValueError:
        result["networkquality"] = {}
    result["ping_stats"] = result.pop("ping")["stats"]
    return result


def table(rows: list[dict], title: str) -> list[str]:
    lines = [f"**{title}**", "", "| Window s | Windows | Whole | Min | Max | Worst error |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['window_s']} | {r['windows']} | {r['whole']} | {r['min']} | {r['max']} | {r['worst_error']} |" for r in rows]
    return lines + [""]


def awdl_pairs(router_ip: str, pairs: int, seconds: float = 20.0) -> dict:
    """Experiment W2: AWDL on and off in pairs, the order inside each pair drawn at random.

    W1's single on-off-on showed the spikes falling over time whatever the state (p95 173 -> 80 -> 60 ms), so a
    drift can pass for an effect. Pairs in random order cancel the drift; the test is the sign of the
    difference in each pair (spike share and p95, off minus on)."""
    import random
    rng = random.Random(2026)
    rows = []
    try:
        for k in range(pairs):
            order = ["on", "off"] if rng.random() < 0.5 else ["off", "on"]
            row = {"pair": k + 1, "order": "-".join(order)}
            for state in order:
                sudo("ifconfig", "awdl0", "down" if state == "off" else "up")
                time.sleep(1)
                p = ping(router_ip, seconds)
                row[state] = dict(p["stats"], awdl=awdl_state())
            print(f"  pair {k + 1}/{pairs}: spikes on {row['on']['spike_share']}, off {row['off']['spike_share']}", flush=True)
            rows.append(row)
    finally:
        sudo("ifconfig", "awdl0", "up")
    diffs = {key: [r["off"][key] - r["on"][key] for r in rows if r["off"].get(key) is not None and r["on"].get(key) is not None]
             for key in ("spike_share", "p95_ms", "jitter_ms", "max_ms")}
    summary = {key: {"mean_off_minus_on": round(statistics.fmean(d), 3) if d else None,
                     "sd": round(statistics.stdev(d), 3) if len(d) > 1 else None,
                     "pairs_lower_off": sum(x < 0 for x in d), "pairs": len(d)} for key, d in diffs.items()}
    return {"pairs": rows, "summary": summary}


def main_w2(pairs: int) -> None:
    link = wifi.link(ROOT)
    if not link or not link.get("rssi_dbm"):
        sys.exit("Wi-Fi is off or not connected.")
    subprocess.run(["sudo", "-v"], check=True)
    router_ip = router()
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    def keep_sudo():  # the run outlasts sudo's 5-minute cache
        while True:
            time.sleep(60)
            subprocess.run(["sudo", "-n", "-v"])
    threading.Thread(target=keep_sudo, daemon=True).start()
    print(f"W2: AWDL on and off in {pairs} pairs of 20 s, random order, about {pairs * 42 // 60 + 1} minutes ...", flush=True)
    result = awdl_pairs(router_ip, pairs)
    awake.terminate()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "logs" / "wireless"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"experiment_w2_{stamp}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = [f"# Wi-Fi experiment W2, {stamp}", "", "| Pair | Order | Spikes on | Spikes off | p95 on | p95 off | Jitter on | Jitter off | AWDL when off |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in result["pairs"]:
        lines.append(f"| {r['pair']} | {r['order']} | {r['on']['spike_share']} | {r['off']['spike_share']} | {r['on'].get('p95_ms')} | "
                     f"{r['off'].get('p95_ms')} | {r['on'].get('jitter_ms')} | {r['off'].get('jitter_ms')} | {r['off']['awdl']} |")
    lines += ["", "| Measure | Mean off − on | SD | Pairs lower with AWDL off |", "|---|---|---|---|"]
    for key, m in result["summary"].items():
        lines.append(f"| {key} | {m['mean_off_minus_on']} | {m['sd']} | {m['pairs_lower_off']} of {m['pairs']} |")
    (folder / f"experiment_w2_{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\n\nReport: logs/wireless/experiment_w2_{stamp}.md")


def main() -> None:
    if "--awdl" in sys.argv:
        main_w2(int(sys.argv[sys.argv.index("--awdl") + 1]) if len(sys.argv) > sys.argv.index("--awdl") + 1 else 8)
        return
    link = wifi.link(ROOT)
    if not link or not link.get("power_on") or not link.get("rssi_dbm"):
        sys.exit("Wi-Fi is off or not connected.")
    print("The password is asked once; it is kept for a few minutes for the driver readings and AWDL.", flush=True)
    subprocess.run(["sudo", "-v"], check=True)
    router_ip = router()
    started = time.time()
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    result = {"link": link}
    result["signal"] = part_signal(router_ip)
    subprocess.run(["sudo", "-v"])
    result["awdl"] = part_awdl(router_ip)
    subprocess.run(["sudo", "-v"])
    result["wdutil_rest"] = part_wdutil()
    result["load"] = part_load(router_ip)
    awake.terminate()
    result["minutes"] = round((time.time() - started) / 60, 1)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "logs" / "wireless"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"experiment_w1_{stamp}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

    s, lat = result["signal"]["rssi"], result["signal"]["latency"]
    lines = [f"# Wi-Fi experiment W1, {stamp}", "",
             f"Link: {link.get('band_ghz')} GHz channel {link.get('channel')}, {link.get('width_mhz')} MHz, {link.get('phy')}, "
             f"{link.get('tx_mbps')} Mb/s. {result['minutes']} minutes.", "",
             "## 1. Signal at a fixed place (CoreWLAN, 10 Hz, 60 s)", "",
             f"Mean {s['mean_dbm']} dBm, σ {s['sigma_db']} dB, range {s['min']} to {s['max']}, {s['distinct_values']} distinct values. "
             f"Update period about {s['update_period_s']} s; correlation time {s['correlation_time_s']} s. "
             f"Averaging needed for ±1 dB (95%): {s['seconds_for_1db']} s; for ±0.5 dB: {s['seconds_for_0_5db']} s. "
             f"Noise values {s['noise_dbm']}; rates {s['tx_mbps']}.", ""]
    lines += table(s["windows_mean"], "Mean signal by window length (dBm)")
    lines += ["## 2. Latency to the router at rest (5 Hz, 60 s)", "", f"Whole: {lat['stats']}", ""]
    lines += table(lat["windows_median"], "Median latency by window (ms)")
    lines += table(lat["windows_p95"], "95th percentile by window (ms)")
    lines += table(lat["windows_spike_share"], "Share of replies above 50 ms by window")
    lines += ["## 3. AWDL on, off, on (pings to the router, 30 s each)", "",
              "| Phase | AWDL state | Median ms | p95 ms | Max ms | Jitter ms | Spikes > 50 ms | Loss % |", "|---|---|---|---|---|---|---|---|"]
    for name, p in result["awdl"].items():
        if not name.startswith("_"):
            lines.append(f"| {name} | {p['awdl']} | {p.get('median_ms')} | {p.get('p95_ms')} | {p.get('max_ms')} | "
                         f"{p.get('jitter_ms')} | {p.get('spike_share')} | {p.get('loss_percent')} |")
    load = result["load"]
    lines += ["", "## 4. Driver readings and load", "",
              "At rest: " + "; ".join(f"RSSI {r.get('rssi_dbm')}, CCA {r.get('cca_percent')}%, NSS {r.get('nss')}, MCS {r.get('mcs')}"
                                     for r in result["wdutil_rest"]), "",
              "Under load: " + "; ".join(f"RSSI {r.get('rssi_dbm')}, CCA {r.get('cca_percent')}%, rate {r.get('tx_mbps')}"
                                        for r in load["wdutil"]), "",
              f"Pings under load: {load['ping_stats']}", "", f"networkQuality: {load['networkquality']}", ""]
    (folder / f"experiment_w1_{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\nReport: logs/wireless/experiment_w1_{stamp}.md")


if __name__ == "__main__":
    main()
