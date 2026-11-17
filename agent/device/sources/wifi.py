"""Wi-Fi and network-path readings (Stage 8).

Sources, chosen by the wireless probe of 2026-11-17 (scripts/probe_wireless.py):
- CoreWLAN through a compiled Swift helper (wifi_helper.swift): the link (signal, noise, channel, band, width,
  PHY mode, rate) in about 2 ms, and a scan of nearby networks with their signal in about 13 s. No rights.
- wdutil info (sudo, about 6 s): channel utilisation (CCA), spatial streams, MCS index, guard interval.
- ping to the router and to the internet: latency, jitter, spikes and loss.
- networkQuality: throughput and latency under load (about 18 s).

The probe found the same link reported as -44 (wdutil), -48 (CoreWLAN) and -43 dBm (scan) at the same moment,
so one source (CoreWLAN) is used for anything fitted or compared.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import subprocess
from pathlib import Path

HELPER_SOURCE = Path(__file__).with_name("wifi_helper.swift")
PHY = {0: "none", 1: "802.11a", 2: "802.11b", 3: "802.11g", 4: "802.11n", 5: "802.11ac", 6: "802.11ax", 7: "802.11be"}


# ---------------------------------------------------------------- CoreWLAN helper

def helper(root: Path) -> Path:
    """The compiled helper in logs/bin/, built again when the Swift source is newer."""
    binary = root / "logs" / "bin" / "wifi_helper"
    if not binary.exists() or binary.stat().st_mtime < HELPER_SOURCE.stat().st_mtime:
        binary.parent.mkdir(parents=True, exist_ok=True)
        done = subprocess.run(["swiftc", "-O", "-o", str(binary), str(HELPER_SOURCE)], capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError("could not build the Wi-Fi helper: " + done.stderr.strip()[:300])
    return binary


def parse_lines(text: str) -> list[dict]:
    records = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            record = json.loads(line)
            if "phy" in record:
                record["phy"] = PHY.get(record["phy"], str(record["phy"]))
            records.append(record)
    return records


def link(root: Path) -> dict:
    out = subprocess.run([str(helper(root)), "link"], capture_output=True, text=True, timeout=10).stdout
    records = parse_lines(out)
    return records[0] if records else {}


def watch(root: Path, hz: float, seconds: float) -> list[dict]:
    out = subprocess.run([str(helper(root)), "watch", str(hz), str(seconds)], capture_output=True, text=True,
                         timeout=seconds + 20).stdout
    return parse_lines(out)


def scan(root: Path) -> list[dict]:
    out = subprocess.run([str(helper(root)), "scan"], capture_output=True, text=True, timeout=60).stdout
    return [r for r in parse_lines(out) if "error" not in r]


# ---------------------------------------------------------------- wdutil

def parse_wdutil(text: str) -> dict:
    """The WIFI section of `wdutil info`: numbers in SI-like units, channel split into band, number, width."""
    def field(label):
        m = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text, re.M)
        return m.group(1) if m else None

    def number(label):
        value = field(label)
        m = re.search(r"-?\d+(\.\d+)?", value or "")
        return float(m.group()) if m else None

    out = {"rssi_dbm": number("RSSI"), "noise_dbm": number("Noise"), "cca_percent": number("CCA"),
           "tx_mbps": number("Tx Rate"), "mcs": number("MCS Index"), "nss": number("NSS"),
           "guard_ns": number("Guard Interval"), "phy": field("PHY Mode"), "security": field("Security")}
    m = re.match(r"(\d)g(\d+)/(\d+)", field("Channel") or "")
    if m:
        out.update(band_ghz={"2": "2.4", "5": "5", "6": "6"}[m.group(1)], channel=int(m.group(2)), width_mhz=int(m.group(3)))
    return out


# ---------------------------------------------------------------- ping

def parse_ping(text: str) -> dict:
    """Replies by sequence number, so lost packets and the time of each reply are known."""
    replies = {int(s): float(t) for s, t in re.findall(r"icmp_seq=(\d+) .*?time=([\d.]+) ms", text)}
    sent = re.search(r"(\d+) packets transmitted", text)
    return {"replies": replies, "sent": int(sent.group(1)) if sent else (max(replies) + 1 if replies else 0)}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def latency_stats(times: list[float], sent: int, spike_ms: float = 50.0) -> dict:
    """Median, 95th percentile, jitter (mean change between consecutive replies), spikes and loss."""
    if not times:
        return {"sent": sent, "received": 0, "loss_percent": 100.0 if sent else None}
    return {"sent": sent, "received": len(times),
            "loss_percent": round(100 * (1 - len(times) / sent), 2) if sent else None,
            "median_ms": round(statistics.median(times), 2), "p95_ms": round(percentile(times, 0.95), 2),
            "max_ms": round(max(times), 2),
            "jitter_ms": round(statistics.mean(abs(a - b) for a, b in zip(times, times[1:])), 2) if len(times) > 1 else 0.0,
            "spike_share": round(sum(t > spike_ms for t in times) / len(times), 3)}


# ---------------------------------------------------------------- how long to measure

def update_period(samples: list[tuple[float, float]]) -> float | None:
    """Median time between changes of a reading sampled faster than it updates (a lower bound on the real
    update period when a new value can equal the old one)."""
    changes = [t for (t, v), (_, prev) in zip(samples[1:], samples) if v != prev]
    gaps = [b - a for a, b in zip(changes, changes[1:])]
    return round(statistics.median(gaps), 3) if gaps else None


def correlation_time(values: list[float], dt: float) -> float | None:
    """Lag at which the autocorrelation first falls below 1/e: readings closer than this are not independent."""
    n = len(values)
    if n < 10:
        return None
    mean = statistics.fmean(values)
    var = sum((v - mean) ** 2 for v in values)
    if var == 0:
        return None
    for lag in range(1, n // 2):
        acf = sum((values[i] - mean) * (values[i + lag] - mean) for i in range(n - lag)) / var
        if acf < 1 / math.e:
            return round(lag * dt, 3)
    return round(n // 2 * dt, 3)


def seconds_for_mean(sigma: float, tau: float, half_width: float = 1.0) -> float:
    """Averaging time for a 95% interval of ±half_width around the mean: about 2·tau seconds per independent
    reading, and (1.96·sigma / half_width)² independent readings."""
    return round(2 * tau * (1.96 * sigma / half_width) ** 2, 1)


def window_spread(series: list[tuple[float, float]], windows: list[float], stat) -> list[dict]:
    """For each window length, the statistic of every non-overlapping window against the whole series:
    the shortest window whose values stay close to the whole-series value is long enough."""
    if not series:
        return []
    whole = stat([v for _, v in series])
    start, end = series[0][0], series[-1][0]
    rows = []
    for w in windows:
        values, t = [], start
        while t + w <= end + 1e-9:
            part = [v for s, v in series if t <= s < t + w]
            if len(part) >= 3:
                values.append(stat(part))
            t += w
        if values:
            rows.append({"window_s": w, "windows": len(values), "whole": round(whole, 2),
                         "min": round(min(values), 2), "max": round(max(values), 2),
                         "worst_error": round(max(abs(v - whole) for v in values), 2)})
    return rows
