"""Wireless probe (Stage 8): what this Mac lets the agent read about Wi-Fi, the network path and Bluetooth.

    python scripts/probe_wireless.py          # about a minute; asks for the password once (wdutil)

Runs each source a Stage 8 reader could use and prints a table: available, missing or needs rights, with
how long a reading takes (a source that takes 2 s cannot be sampled every second). Raw outputs are saved
in logs/probe_wireless/ only: they name networks, devices and addresses, so nothing here is committed and
the printed table shows only values that identify no one (signal, channel, rates, times).

Sources:
- system_profiler SPAirPortDataType: the link (signal, noise, channel, width, PHY mode, MCS, rate) and
  nearby networks (Stage 7 probe: channels listed, no signal for them)
- CoreWLAN through a small Swift program: fast link readings and a scan with the signal of every network
- wdutil info (needs sudo): driver-level link details, possibly channel utilisation (CCA)
- the path: ping to the router and to the internet, DNS lookup time, networkQuality (throughput and
  responsiveness under load), interface error counters
- system_profiler SPBluetoothDataType: connected devices and whether any signal strength is given
"""

from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "logs" / "probe_wireless"

SWIFT = r"""
import CoreWLAN
import Foundation
guard let wifi = CWWiFiClient.shared().interface() else { print("no_interface"); exit(0) }
print("link rssi=\(wifi.rssiValue()) noise=\(wifi.noiseMeasurement()) tx=\(wifi.transmitRate()) " +
      "channel=\(wifi.wlanChannel()?.channelNumber ?? -1) band=\(wifi.wlanChannel()?.channelBand.rawValue ?? -1) " +
      "width=\(wifi.wlanChannel()?.channelWidth.rawValue ?? -1) phy=\(wifi.activePHYMode().rawValue) " +
      "ssid=\(wifi.ssid() == nil ? "hidden" : "visible") bssid=\(wifi.bssid() == nil ? "hidden" : "visible")")
let t0 = Date()
var values: [Int] = []
for _ in 0..<20 { values.append(wifi.rssiValue()) }
print("read20_ms=\(Int(Date().timeIntervalSince(t0) * 1000)) values=\(values.map(String.init).joined(separator: ","))")
let t1 = Date()
do {
    let nets = try wifi.scanForNetworks(withSSID: nil)
    print("scan_ms=\(Int(Date().timeIntervalSince(t1) * 1000)) count=\(nets.count)")
    for n in nets {
        print("net rssi=\(n.rssiValue) noise=\(n.noiseMeasurement) channel=\(n.wlanChannel?.channelNumber ?? -1) " +
              "band=\(n.wlanChannel?.channelBand.rawValue ?? -1) width=\(n.wlanChannel?.channelWidth.rawValue ?? -1) " +
              "ssid=\(n.ssid == nil ? "hidden" : "visible") bssid=\(n.bssid == nil ? "hidden" : "visible") " +
              "beacon=\(n.beaconInterval)")
    }
} catch { print("scan_error=\(error)") }
"""


def run(name: str, command: list[str], timeout: float = 30, stdin_tty: bool = False) -> dict:
    """Runs a command, saves its output in logs/probe_wireless/<name>.txt, returns text, code and seconds."""
    if not shutil.which(command[0]):
        return {"name": name, "ok": False, "out": "", "err": f"{command[0]} not found", "seconds": 0.0}
    started = time.perf_counter()
    try:
        done = subprocess.run(command, capture_output=not stdin_tty, stdout=subprocess.PIPE if stdin_tty else None,
                              text=True, timeout=timeout)
        out, err, code = done.stdout or "", done.stderr or "", done.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", f"timed out after {timeout} s", -1
    seconds = round(time.perf_counter() - started, 2)
    (RAW / f"{name}.txt").write_text(out + ("\n--- stderr ---\n" + err if err else ""), encoding="utf-8")
    return {"name": name, "ok": code == 0 and bool(out.strip()), "out": out, "err": err.strip()[:200], "seconds": seconds}


def profiler_wifi() -> dict:
    times, last = [], None
    for k in range(3):
        last = run(f"wifi_profiler_{k}", ["system_profiler", "SPAirPortDataType", "-json"])
        times.append(last["seconds"])
    found = {"seconds per reading": round(statistics.median(times), 2)}
    try:
        iface = json.loads(last["out"])["SPAirPortDataType"][0]["spairport_airport_interfaces"][0]
    except (ValueError, KeyError, IndexError):
        return {"status": "missing", "found": found}
    cur = iface.get("spairport_current_network_information", {})
    for key, label in [("spairport_signal_noise", "signal / noise"), ("spairport_network_channel", "channel"),
                       ("spairport_network_phymode", "PHY mode"), ("spairport_network_mcs", "MCS"),
                       ("spairport_network_rate", "link rate Mb/s")]:
        found[label] = cur.get(key, "missing")
    others = iface.get("spairport_airport_other_local_wireless_networks", [])
    found["nearby networks"] = len(others)
    found["nearby with signal"] = sum(any("signal" in k for k in n) for n in others)
    return {"status": "available" if cur else "missing", "found": found}


def corewlan() -> dict:
    if not shutil.which("swift") or subprocess.run(["xcode-select", "-p"], capture_output=True).returncode != 0:
        return {"status": "missing", "found": {"note": "no Swift (Xcode Command Line Tools); pyobjc is the alternative"}}
    source = RAW / "corewlan_probe.swift"
    source.write_text(SWIFT, encoding="utf-8")
    result = run("corewlan", ["swift", str(source)], timeout=120)
    out = result["out"]
    if not result["ok"]:
        return {"status": "missing", "found": {"error": result["err"][:120]}}
    found = {"run time s (compile + scan)": result["seconds"]}
    link = re.search(r"^link (.*)$", out, re.M)
    if link:
        found["link"] = link.group(1)
    read = re.search(r"read20_ms=(\d+) values=(\S+)", out)
    if read:
        found["20 RSSI reads ms"] = int(read.group(1))
        found["RSSI values"] = read.group(2)
    scan = re.search(r"scan_ms=(\d+) count=(\d+)", out)
    nets = re.findall(r"^net rssi=(-?\d+) noise=(-?\d+) channel=(-?\d+) band=(-?\d+) width=(-?\d+) ssid=(\w+)", out, re.M)
    if scan:
        found["scan ms"], found["networks seen"] = int(scan.group(1)), int(scan.group(2))
        found["with signal"] = sum(int(n[0]) != 0 for n in nets)
        found["names visible"] = sum(n[5] == "visible" for n in nets)
        bands = {}
        for n in nets:  # first probe run: counted by the raw band number, so every band showed 1
            label = {"1": "2.4 GHz", "2": "5 GHz", "3": "6 GHz"}.get(n[3], n[3])
            bands[label] = bands.get(label, 0) + 1
        found["per band"] = bands
        found["signals"] = sorted((int(n[0]) for n in nets), reverse=True)[:12]
    elif "scan_error" in out:
        found["scan"] = re.search(r"scan_error=(.*)", out).group(1)[:120]
    return {"status": "available" if link else "missing", "found": found}


def wdutil() -> dict:
    result = run("wdutil", ["sudo", "-n", "wdutil", "info"], timeout=30)
    if not result["ok"]:
        print("wdutil needs the administrator password once (the output stays in logs/probe_wireless/):", flush=True)
        result = run("wdutil", ["sudo", "wdutil", "info"], timeout=90, stdin_tty=True)
    if not result["ok"]:
        return {"status": "needs rights", "found": {"error": result["err"][:120]}}
    found = {"seconds per reading": result["seconds"]}
    for label in ["RSSI", "Noise", "CCA", "Tx Rate", "Channel", "PHY Mode", "NSS", "Guard Interval", "MCS Index",
                  "Security", "Country Code", "Power Mgmt", "Op Mode"]:
        m = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.+)$", result["out"], re.M)
        if m:
            found[label] = m.group(1).strip()[:40]
    found["fields with 'utilization' or 'CCA'"] = len(re.findall(r"(?i)cca|utiliz", result["out"]))
    return {"status": "available", "found": found}


def ping(name: str, host: str) -> dict:
    result = run(name, ["ping", "-c", "20", "-i", "0.2", "-t", "15", host], timeout=25)
    if not result["ok"] and "interval" in (result["err"] + result["out"]).lower():
        result = run(name, ["ping", "-c", "8", "-i", "1", "-t", "15", host], timeout=25)
    out = result["out"]
    loss = re.search(r"([\d.]+)% packet loss", out)
    rtt = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", out)
    times = [float(x) for x in re.findall(r"time=([\d.]+) ms", out)]
    found = {"seconds": result["seconds"]}
    if loss:
        found["loss %"] = float(loss.group(1))
    if rtt:
        found["min/avg/max ms"] = f"{rtt.group(1)}/{rtt.group(2)}/{rtt.group(3)}"
        found["stddev ms"] = float(rtt.group(4))
    if len(times) > 1:
        found["jitter ms (mean |Δ|)"] = round(statistics.mean(abs(a - b) for a, b in zip(times, times[1:])), 2)
    return {"status": "available" if rtt else "missing", "found": found}


def gateway() -> str | None:
    result = run("route", ["route", "-n", "get", "default"], timeout=10)
    m = re.search(r"gateway:\s*(\S+)", result["out"])
    return m.group(1) if m else None


def dns() -> dict:
    times = []
    for k, host in enumerate([f"probe{int(time.time())}.example.com", "github.com", "naver.com", "apple.com"]):
        result = run(f"dns_{k}", ["dig", "+tries=1", "+time=3", host], timeout=10)
        m = re.search(r"Query time: (\d+) msec", result["out"])
        if m:
            times.append(int(m.group(1)))
    return {"status": "available" if times else "missing", "found": {"query times ms": times}}


def network_quality() -> dict:
    result = run("networkquality", ["networkQuality", "-c"], timeout=90)
    try:
        data = json.loads(result["out"])
    except ValueError:
        return {"status": "missing", "found": {"error": result["err"][:120]}}
    found = {"seconds": result["seconds"]}
    for key, value in data.items():
        if isinstance(value, (int, float)):
            found[key] = round(value / 1e6, 1) if "throughput" in key else value
    found["keys"] = sorted(data)[:30]
    return {"status": "available", "found": found}


def interface_counters() -> dict:
    result = run("netstat", ["netstat", "-I", "en0", "-b"], timeout=10)
    lines = [l.split() for l in result["out"].splitlines() if l.strip()]
    if len(lines) < 2:
        return {"status": "missing", "found": {}}
    header, row = lines[0], lines[1]
    found = {h: v for h, v in zip(header, row) if h in ("Ipkts", "Ierrs", "Ibytes", "Opkts", "Oerrs", "Obytes", "Coll")}
    return {"status": "available", "found": found}


def ipconfig() -> dict:
    result = run("ipconfig", ["ipconfig", "getsummary", "en0"], timeout=10)
    keys = sorted(set(re.findall(r"^\s*([A-Za-z][A-Za-z ]+?)\s*:", result["out"], re.M)))
    return {"status": "available" if result["ok"] else "missing", "found": {"fields": keys[:30]}}


def bluetooth() -> dict:
    result = run("bluetooth", ["system_profiler", "SPBluetoothDataType", "-json"], timeout=30)
    try:
        data = json.loads(result["out"])["SPBluetoothDataType"][0]
    except (ValueError, KeyError, IndexError):
        return {"status": "missing", "found": {}}
    connected = data.get("device_connected", [])
    rssi = re.findall(r'"device_rssi"\s*:\s*"?(-?\d+)', result["out"])
    found = {"seconds per reading": result["seconds"], "connected devices": len(connected),
             "kinds": [list(d.values())[0].get("device_minorType", "?") for d in connected],
             "known, not connected": len(data.get("device_not_connected", [])),
             "signal values given": [int(r) for r in rssi]}
    return {"status": "available", "found": found}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    print("Wireless probe: about a minute. Keep the Mac where it usually is, on its usual network.", flush=True)
    results = {}
    results["wdutil info (sudo)"] = wdutil()       # first, so the password prompt comes at the start
    print("Reading the link and scanning ...", flush=True)
    results["system_profiler Wi-Fi"] = profiler_wifi()
    results["CoreWLAN (Swift)"] = corewlan()
    results["ipconfig summary"] = ipconfig()
    results["interface counters"] = interface_counters()
    print("Testing the path: router, internet, DNS ...", flush=True)
    router = gateway()
    with ThreadPoolExecutor(2) as pool:
        to_router = pool.submit(ping, "ping_router", router) if router else None
        to_internet = pool.submit(ping, "ping_internet", "1.1.1.1")
        results["ping router"] = to_router.result() if to_router else {"status": "missing", "found": {"note": "no default gateway"}}
        results["ping internet (1.1.1.1)"] = to_internet.result()
    results["DNS lookups"] = dns()
    print("Measuring throughput and responsiveness (networkQuality, about 20 s) ...", flush=True)
    results["networkQuality"] = network_quality()
    results["Bluetooth"] = bluetooth()

    print("\n| Source | Status | What was found |\n|---|---|---|")
    for name, r in results.items():
        text = "; ".join(f"{k}: {v}" for k, v in r["found"].items())
        print(f"| {name} | {r['status']} | {text} |")
    (RAW / "summary.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nRaw outputs: logs/probe_wireless/ (not committed)")


if __name__ == "__main__":
    main()
