"""Network agent (Stage 8): Wi-Fi link and network path measured on request, diagnosed by code.

"Why is my Wi-Fi slow?" is answered by locating the problem on the path, hop by hop:
- the radio link (signal, noise, SNR, rate, MCS) from CoreWLAN and wdutil;
- the Wi-Fi segment: pings to the router (latency, spikes, loss) and the AWDL state, which W2 showed to cause
  the spikes on this Mac (p95 3.2 ms with AWDL down against 60-170 ms with it up);
- beyond the router: pings to the internet compared with the router (the provider adds the difference);
- DNS lookup time.

Measuring times come from experiment W1: 10 s gives the median and the spike share; the 95th percentile needs
30 s, so a question about a call or a game measures for 30 s.

"Can I play an online game now?" gets a verdict per use from the measured path, not from the signal alone:
Wi-Fi adapts its modulation to the SNR (link adaptation), so a weak signal first lowers the rate and only later
costs latency and loss, and each use is limited by a different quantity.

| Use | Criterion (internet path) | Basis |
|---|---|---|
| online games | median <= 40 ms, p95 <= 60 ms, spikes <= 2 %, loss <= 1 % | common guidance for real-time games |
| video calls | p95 <= 150 ms, jitter <= 30 ms, loss <= 1 % | ITU-T G.114: one-way delay under 150 ms for conversation |
| 4K streaming | throughput >= 25 Mb/s (measured on request) | streaming services ask 15-25 Mb/s for 4K |
| browsing | median <= 100 ms, loss <= 2 % | |
| messaging | loss <= 5 % | |
"""

from __future__ import annotations

import json
import re
import statistics
import threading
import time
from dataclasses import dataclass, field

from .diagnosis import Finding, Report
from .sources import bluetooth, wifi

USES = {
    "game": "online games",
    "video_call": "video calls",
    "streaming": "4K streaming",
    "browsing": "browsing",
    "messaging": "messaging",
}
USE_WORDS = [
    ("game", r"게임|(?<![a-z])gam(e|es|ing)(?![a-z])|롤|배그|발로란트|오버워치"),
    ("video_call", r"화상\s*(통화|회의)|줌|zoom|facetime|페이스타임|video call|meeting|통화"),
    ("streaming", r"스트리밍|유튜브|넷플릭스|4k|영상\s*(시청|보기)|youtube|netflix|stream"),
    ("browsing", r"웹\s*서핑|검색|브라우징|browsing|web"),
    ("messaging", r"메신저|카톡|카카오톡|메시지|messag|chat|imessage"),
]
OVERVIEW = r"뭘\s*할\s*수|뭐\s*할\s*수|어떤\s*(것|거|작업)|what can i do"
SPEED_WORDS = r"속도|빠르|다운로드|업로드|대역폭|몇\s*메가|speed|download|upload|mbps|throughput|4k|스트리밍|stream"
SCAN_WORDS = r"채널|혼잡|붐비|주변\s*(와이파이|네트워크)|다른\s*와이파이|어떤\s*와이파이|channel|crowded|nearby networks|which wi-?fi"
BT_WORDS = r"블루투스|에어팟|이어폰|헤드폰|스피커|마우스|키보드|bluetooth|airpods|headphones?|earbuds|speaker"


def uses_from_question(question: str) -> list[str]:
    q = question.lower()
    if re.search(OVERVIEW, q):
        return list(USES)
    return [key for key, pattern in USE_WORDS if re.search(pattern, q)]


# ---------------------------------------------------------------- measurement

@dataclass
class Measurement:
    link: list[dict] = field(default_factory=list)
    router: dict = field(default_factory=dict)       # latency_stats
    internet: dict = field(default_factory=dict)
    gateway: str | None = None
    awdl: list[int | None] = field(default_factory=list)
    dns_ms: list[float] = field(default_factory=list)
    driver: dict = field(default_factory=dict)
    throughput: dict = field(default_factory=dict)
    scan: list[dict] = field(default_factory=list)
    bluetooth: list[dict] | None = None
    seconds: float = 10.0
    notes: list[str] = field(default_factory=list)


def awdl_active(text: str) -> int | None:
    if not text:
        return None
    return int(("<UP," in text or "<UP>" in text) and "status: active" in text)


def measure(shell, helper: str, question: str = "", ping_seconds: float | None = None) -> Measurement:
    """Pings, link and AWDL at the same time; then DNS, driver readings, and the extras the question needs."""
    q = question.lower()
    uses = uses_from_question(question)
    seconds = ping_seconds or (30.0 if {"game", "video_call"} & set(uses) else 10.0)
    m = Measurement(seconds=seconds)
    gw = re.search(r"gateway:\s*(\S+)", shell.run("route", ["route", "-n", "get", "default"]).text)
    m.gateway = gw.group(1) if gw else None
    count = int(seconds * 5)
    m.awdl.append(awdl_active(shell.run("awdl", ["ifconfig", "awdl0"]).text))
    results: dict = {}

    def ping(name, host):
        out = shell.run(name, ["ping", "-c", str(count), "-i", "0.2", "-W", "1000", host], timeout=seconds + 15)
        parsed = wifi.parse_ping(out.text)
        results[name] = wifi.latency_stats([ms for _, ms in sorted(parsed["replies"].items())], parsed["sent"]) if parsed["sent"] else {}

    def watch():
        out = shell.run("wifi_watch", [helper, "watch", "5", str(min(seconds, 10))], timeout=30)
        results["link"] = wifi.parse_lines(out.text)

    threads = [threading.Thread(target=ping, args=("ping_internet", "1.1.1.1")), threading.Thread(target=watch)]
    if m.gateway:
        threads.append(threading.Thread(target=ping, args=("ping_router", m.gateway)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    m.link, m.router, m.internet = results.get("link", []), results.get("ping_router", {}), results.get("ping_internet", {})
    m.awdl.append(awdl_active(shell.run("awdl", ["ifconfig", "awdl0"]).text))
    for k, host in enumerate([f"agent-{int(time.time())}.example.com", "apple.com"]):
        found = re.search(r"Query time: (\d+) msec", shell.run(f"dns_{k}", ["dig", "+tries=1", "+time=3", host]).text)
        if found:
            m.dns_ms.append(float(found.group(1)))
    drv = shell.run("wdutil", ["sudo", "-n", "wdutil", "info"])
    if drv.ok and "RSSI" in drv.text:
        m.driver = wifi.parse_wdutil(drv.text)
    else:
        m.notes.append("driver readings need the administrator password (sudo); not measured")
    if re.search(SPEED_WORDS, q) or "streaming" in uses:
        nq = shell.run("networkquality", ["networkQuality", "-c"], timeout=90)
        try:
            data = json.loads(nq.text)
            m.throughput = {"down_mbps": round(data.get("dl_throughput", 0) / 1e6, 1), "up_mbps": round(data.get("ul_throughput", 0) / 1e6, 1),
                            "responsiveness": round(data.get("responsiveness", 0), 1), "base_rtt_ms": round(data.get("base_rtt", 0), 1)}
        except ValueError:
            m.notes.append("throughput test failed")
    if re.search(SCAN_WORDS, q):
        m.scan = wifi.parse_lines(shell.run("wifi_scan", [helper, "scan"], timeout=60).text)
    if re.search(BT_WORDS, q):
        m.bluetooth = bluetooth.parse(shell.run("bluetooth", ["system_profiler", "SPBluetoothDataType", "-json"], timeout=20).text)
    return m


# ---------------------------------------------------------------- diagnosis

def _verdict(use: str, m: Measurement) -> tuple[str, str]:
    i = m.internet
    if not i or not i.get("received"):
        return "not now", "no reply from the internet"
    med, p95, loss, spikes, jitter = i.get("median_ms", 0), i.get("p95_ms", 0), i.get("loss_percent", 0), i.get("spike_share", 0), i.get("jitter_ms", 0)
    if use == "game":
        if loss > 3 or med > 100:
            return "not now", f"internet median {med} ms, loss {loss}%"
        if med > 40 or p95 > 60 or spikes > 0.02 or loss > 1:
            return "with care", f"median {med} ms, p95 {p95} ms, {spikes * 100:.0f}% of replies above 50 ms, loss {loss}%"
        return "yes", f"median {med} ms, p95 {p95} ms, loss {loss}%"
    if use == "video_call":
        if loss > 3 or p95 > 300:
            return "not now", f"p95 {p95} ms, loss {loss}%"
        if p95 > 150 or jitter > 30 or loss > 1:
            return "with care", f"p95 {p95} ms, jitter {jitter} ms, loss {loss}%"
        return "yes", f"p95 {p95} ms, jitter {jitter} ms, loss {loss}%"
    if use == "streaming":
        down = m.throughput.get("down_mbps")
        if down is None:
            return "not measured", "throughput not measured"
        if down < 10:
            return "not now", f"download {down} Mb/s"
        return ("yes" if down >= 25 else "with care"), f"download {down} Mb/s"
    if use == "browsing":
        if loss > 5 or med > 300:
            return "not now", f"median {med} ms, loss {loss}%"
        return ("yes" if med <= 100 and loss <= 2 else "with care"), f"median {med} ms, loss {loss}%"
    return ("yes" if loss <= 5 else "with care"), f"loss {loss}%"


def report(m: Measurement, question: str = "", baseline: dict | None = None) -> Report:
    r = Report("network")
    f, findings = r.facts, r.findings
    rssi = [s["rssi_dbm"] for s in m.link if s.get("rssi_dbm")]
    if not rssi:
        f["Wi-Fi"] = "not connected"
        findings.append(Finding("no_wifi", "problem", "The Mac is not connected to Wi-Fi.", {"Wi-Fi": "not connected"},
                                "Turn Wi-Fi on and join the network."))
        return r
    first = m.link[0]
    signal = round(statistics.fmean(rssi), 1)
    noise = first.get("noise_dbm")
    snr = round(signal - noise, 1) if noise else None
    f["band and channel"] = f"{first.get('band_ghz')} GHz, channel {first.get('channel')}, {first.get('width_mhz')} MHz, {first.get('phy')}"
    f["signal"] = f"{signal} dBm"
    if noise:
        f["noise"] = f"{noise} dBm"
        f["SNR"] = f"{snr} dB"
    f["link rate"] = f"{first.get('tx_mbps')} Mb/s"
    d = m.driver
    if d:
        f["MCS"] = f"{d.get('mcs'):.0f}" if d.get("mcs") is not None else "not given"
        f["spatial streams"] = f"{d.get('nss'):.0f}" if d.get("nss") is not None else "not given"
        f["channel utilisation"] = f"{d.get('cca_percent'):.0f}%" if d.get("cca_percent") is not None else "not given"
    awdl = [a for a in m.awdl if a is not None]
    awdl_on = bool(awdl) and max(awdl) == 1
    f["AWDL (AirDrop, Handoff)"] = "active" if awdl_on else ("inactive" if awdl else "not read")
    ro, it = m.router, m.internet
    span = f"{m.seconds:.0f} s"
    if ro:
        f["latency to the router"] = (f"median {ro.get('median_ms')} ms, p95 {ro.get('p95_ms')} ms, jitter {ro.get('jitter_ms')} ms, "
                                      f"{(ro.get('spike_share') or 0) * 100:.0f}% of replies above 50 ms, loss {ro.get('loss_percent')}% ({span})")
    if it:
        f["latency to the internet"] = (f"median {it.get('median_ms')} ms, p95 {it.get('p95_ms')} ms, jitter {it.get('jitter_ms')} ms, "
                                        f"loss {it.get('loss_percent')}% ({span})")
    if m.dns_ms:
        f["DNS lookup"] = f"{statistics.median(m.dns_ms):.0f} ms"
    t = m.throughput
    if t:
        f["download"], f["upload"] = f"{t['down_mbps']} Mb/s", f"{t['up_mbps']} Mb/s"
        if t.get("responsiveness"):
            f["latency under load"] = f"about {60000 / t['responsiveness']:.0f} ms ({t['responsiveness']:.0f} round trips per minute)"

    # The radio link.
    if signal < -80 or (snr is not None and snr < 10):
        findings.append(Finding("signal_weak", "problem", "The Wi-Fi signal is very weak.", {"signal": f["signal"], **({"SNR": f["SNR"]} if snr else {})},
                                "Move closer to the router or remove walls in between; at this level the link drops to its slowest modulation."))
    elif signal < -72 or (snr is not None and snr < 20):
        findings.append(Finding("signal_low", "warning", "The Wi-Fi signal is low.", {"signal": f["signal"], **({"SNR": f["SNR"]} if snr else {})},
                                "Calls and games may stutter; moving closer to the router or into its room helps."))

    # The Wi-Fi segment: the router hop.
    if ro and ro.get("received"):
        spikes, loss = ro.get("spike_share") or 0, ro.get("loss_percent") or 0
        if loss > 1:
            findings.append(Finding("wifi_loss", "problem", "Packets are lost between the Mac and the router.",
                                    {"latency to the router": f["latency to the router"], "signal": f["signal"]},
                                    "The Wi-Fi link itself is the problem: move closer or change the channel."))
        if spikes >= 0.03:
            if awdl_on:
                findings.append(Finding("awdl_spikes", "warning",
                                        "The latency to the router jumps from time to time; AWDL (AirDrop and Handoff) is active and causes this on this Mac.",
                                        {"latency to the router": f["latency to the router"], "AWDL (AirDrop, Handoff)": "active",
                                         "test on this Mac": "with AWDL off, p95 to the router fell to about 3 ms in 5 of 6 pairs (experiment W2)"},
                                        "For a call or a game, turn AirDrop off and Handoff off (System Settings, General, AirDrop & Handoff)."))
            else:
                findings.append(Finding("wifi_spikes", "warning", "The latency to the router jumps from time to time; the cause is not identified.",
                                        {"latency to the router": f["latency to the router"], "AWDL (AirDrop, Handoff)": f["AWDL (AirDrop, Handoff)"]},
                                        "Other devices using the Wi-Fi heavily or interference can cause this."))
    # Beyond the router.
    if ro and it and ro.get("received") and it.get("received"):
        extra = (it.get("median_ms") or 0) - (ro.get("median_ms") or 0)
        if (it.get("loss_percent") or 0) > max(1.0, (ro.get("loss_percent") or 0) + 1) or extra > 80:
            findings.append(Finding("internet_problem", "problem", "The problem is beyond the router: the internet connection adds delay or loses packets.",
                                    {"latency to the router": f["latency to the router"], "latency to the internet": f["latency to the internet"]},
                                    "The Wi-Fi is fine; restart the router or modem, or check the provider."))
    elif it and not it.get("received"):
        findings.append(Finding("internet_down", "problem", "The internet does not answer, although Wi-Fi is connected.",
                                {"latency to the internet": "no reply"}, "Restart the router or modem; check the provider."))
    if m.dns_ms and statistics.median(m.dns_ms) > 100:
        findings.append(Finding("dns_slow", "warning", "Name lookups (DNS) are slow, so pages start slowly.", {"DNS lookup": f["DNS lookup"]},
                                "Restart the router, or set a public DNS server in the network settings."))
    if d and (d.get("cca_percent") or 0) > 50 and not t:
        findings.append(Finding("channel_busy", "warning", "The Wi-Fi channel is busy most of the time.", {"channel utilisation": f["channel utilisation"]},
                                "Other networks or devices share the channel; a different channel on the router may help."))
    if t and t.get("responsiveness") and 60000 / t["responsiveness"] > 100:
        findings.append(Finding("latency_under_load", "warning", "Latency rises a lot while the connection is busy (queues in the router).",
                                {"latency under load": f["latency under load"], "latency to the internet": f.get("latency to the internet", "")},
                                "During a call or a game, pause large downloads and uploads (cloud backup, updates)."))
    # Against this Mac's usual values on this network.
    if baseline:
        usual = baseline.get("router_median")
        if usual is not None and ro.get("median_ms") is not None and ro["median_ms"] > 3 * usual + 5:
            f["usual latency to the router"] = f"median {usual:.1f} ms"
            findings.append(Finding("worse_than_usual", "warning", "The Wi-Fi is slower than usual on this network.",
                                    {"latency to the router": f["latency to the router"], "usual latency to the router": f["usual latency to the router"]},
                                    "Something changed: another device using the network, interference, or the router."))
        usual_signal = baseline.get("rssi")
        if usual_signal is not None and signal < usual_signal - 6:
            f["usual signal"] = f"{usual_signal:.1f} dBm"
            findings.append(Finding("signal_below_usual", "info", "The signal is weaker than usual here.",
                                    {"signal": f["signal"], "usual signal": f["usual signal"]}, "The Mac is probably further from the router than usual."))

    # Uses.
    for use in uses_from_question(question):
        verdict, why = _verdict(use, m)
        f[f"verdict for {USES[use]}"] = f"{verdict} ({why})"
        code = {"yes": "use_yes", "with care": "use_care", "not now": "use_not_now", "not measured": "use_not_measured"}[verdict]
        advice = {"yes": "Fine now.", "with care": "It works, but expect occasional stutters.",
                  "not now": "Not reliable now.", "not measured": "Ask about speed to measure it (about 20 s)."}[verdict]
        if verdict == "with care" and use in ("game", "video_call") and any(x.code == "awdl_spikes" for x in findings):
            advice += " Turning AirDrop and Handoff off should remove the spikes."
        findings.append(Finding(code, "info" if verdict == "yes" else "warning", f"{USES[use][0].upper() + USES[use][1:]}: {verdict}.",
                                {f"verdict for {USES[use]}": f[f"verdict for {USES[use]}"]}, advice))

    # Nearby networks and Bluetooth, when asked.
    if m.scan:
        same = [n for n in m.scan if n.get("channel") == first.get("channel") and n.get("band_ghz") == first.get("band_ghz")]
        others = sorted((n["rssi_dbm"] for n in same), reverse=True)[1:]
        f["networks seen"] = f"{len(m.scan)} ({sum(n.get('band_ghz') == '2.4' for n in m.scan)} on 2.4 GHz, {sum(n.get('band_ghz') == '5' for n in m.scan)} on 5 GHz, {sum(n.get('band_ghz') == '6' for n in m.scan)} on 6 GHz)"
        f["other networks on this channel"] = ", ".join(f"{v} dBm" for v in others) if others else "none"
        strong = [v for v in others if v > signal - 20]
        findings.append(Finding("channel_shared" if strong else "channel_clear", "warning" if strong else "info",
                                "Another strong network shares this channel." if strong else "No strong network shares this channel.",
                                {"other networks on this channel": f["other networks on this channel"], "signal": f["signal"]},
                                "A different channel on the router would help." if strong else "No channel change needed."))
    if m.bluetooth is not None:
        if not m.bluetooth:
            f["Bluetooth devices connected"] = "none"
        for dev in m.bluetooth:
            value = "signal not given by macOS" if dev["rssi_dbm"] is None else f"{dev['rssi_dbm']} dBm"
            f[f"Bluetooth {dev['kind'] or 'device'} '{dev['name']}'"] = value
            if dev["rssi_dbm"] is not None and dev["rssi_dbm"] < -80:
                findings.append(Finding("bt_weak", "warning", f"The Bluetooth {dev['kind'] or 'device'} has a weak signal and may cut out.",
                                        {f"Bluetooth {dev['kind'] or 'device'} '{dev['name']}'": value}, "Bring it closer to the Mac or remove obstacles."))
    for note in m.notes:
        f.setdefault("not measured", note)
    if not [x for x in findings if x.severity in ("warning", "problem")]:
        findings.append(Finding("network_ok", "info", "The Wi-Fi and the internet connection are fine.",
                                {"signal": f["signal"], "latency to the internet": f.get("latency to the internet", "")}, "No action needed."))
    order = {"problem": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda x: order[x.severity])
    return r


def baseline_from_store(store) -> dict | None:
    """This Mac's usual values on its network: medians over the last 7 days of the Wi-Fi log (at least 30 rounds)."""
    if store is None:
        return None
    out = {}
    for key, name in (("router_median", "net.router_median"), ("rssi", "wifi.rssi"), ("internet_median", "net.internet_median")):
        values = [v for _, v in store.series(name, 7 * 24 * 60)]
        if len(values) >= 30:
            out[key] = statistics.median(values)
    return out or None
