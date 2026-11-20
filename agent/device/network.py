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
| online games | no rise of 20 ms or more above the player's usual ping in 30 s, median <= 50 ms, loss <= 0.5 % | in fast games a short rise, not the average, loses fights; see agent/device/game_watch.py and experiment G1 |
| video calls | round trip <= 100 ms, jitter <= 30 ms, loss <= 1 %, 1.5 Mb/s up and down | Microsoft Teams network requirements (client to service, including Wi-Fi; recommended video 1.5 Mb/s, best 4 Mb/s) |
| 4K streaming | download >= 25 Mb/s; 15-25 "with care" | Netflix asks 15 Mb/s for 4K; one measurement varies (73 against 150 Mb/s at one point on two days), hence headroom |
| large downloads and uploads | the time for 10 GB each way; "with care" above 30 minutes | the speed decides how long, not whether |
| browsing | median <= 100 ms, loss <= 2 % | |
| messaging | loss <= 5 % | |

Every verdict comes from what the application feels (latency, spikes, loss, speed). The radio values (signal, SNR
and SINR, modulation, link rate) explain why, locate the bottleneck (the Wi-Fi link or the line beyond the
router) and rank the other networks heard here (agent/device/wifi_choice.py).
"""

from __future__ import annotations

import json
import re
import statistics
import threading
import time
from dataclasses import dataclass, field

from . import wifi_choice
from .diagnosis import Finding, Report
from .sources import bluetooth, wifi

USES = {
    "game": "online games",
    "video_call": "video calls",
    "streaming": "4K streaming",
    "browsing": "browsing",
    "messaging": "messaging",
    "download": "large downloads and uploads",
}
USE_WORDS = [
    ("game", r"게임|(?<![a-z])gam(e|es|ing)(?![a-z])|(?<![가-힣])롤(?!백|러|링|케)|리그\s*오브\s*레전드|배그|배틀\s*그라운드|발로란트|오버워치"
             r"|(?<![a-z])lol(?![a-z])|league of legends|valorant|(?<![a-z])pubg(?![a-z])|overwatch"),
    ("video_call", r"화상\s*(통화|회의)|줌|zoom|facetime|페이스타임|video call|meeting|통화"),
    ("streaming", r"스트리밍|유튜브|넷플릭스|4k|영상\s*(시청|보기)|youtube|netflix|stream"),
    ("browsing", r"웹\s*서핑|검색|브라우징|browsing|web"),
    ("messaging", r"메신저|카톡|카카오톡|메시지|messag|chat|imessage"),
    ("download", r"다운로드|다운\s*받|업로드|큰\s*파일|대용량|파일\s*(전송|올리|받)|download|upload|large files?"),
]
OVERVIEW = (r"뭘\s*할\s*수|뭐\s*할\s*수|어떤\s*(것|거|작업)|가능한\s*작업|할\s*수\s*있는\s*(거|것|작업)|what can i do"
            r"|(어떤|어느|무슨)\s*와이파이|와이파이.{0,12}(바꿔|바꿀|추천|골라)|which (wi-?fi|network)|best (wi-?fi|network)|switch (wi-?fi|network)")
SPEED_WORDS = r"속도|빠르|다운로드|업로드|대역폭|몇\s*메가|speed|download|upload|mbps|throughput|4k|스트리밍|stream"
SCAN_WORDS = (r"채널|혼잡|붐비|주변\s*(와이파이|네트워크)|다른\s*와이파이|(어떤|어느|무슨)\s*와이파이|와이파이.{0,12}(바꿔|바꿀|추천|골라)"
              r"|channel|crowded|nearby networks|which (wi-?fi|network)|best (wi-?fi|network)|switch (wi-?fi|network)")
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
    known: set[str] = field(default_factory=set)     # networks this Mac has joined before
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
    interval = 0.1 if "game" in uses else 0.2          # 10 pings a second catch the short spikes that matter in games
    count = int(seconds / interval)
    m.awdl.append(awdl_active(shell.run("awdl", ["ifconfig", "awdl0"]).text))
    results: dict = {}

    def ping(name, host):
        out = shell.run(name, ["ping", "-c", str(count), "-i", str(interval), "-W", "1000", host], timeout=seconds + 15)
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
    if re.search(SPEED_WORDS, q) or {"streaming", "download", "video_call"} & set(uses):
        nq = shell.run("networkquality", ["networkQuality", "-c"], timeout=90)
        try:
            data = json.loads(nq.text)
            m.throughput = {"down_mbps": round(data.get("dl_throughput", 0) / 1e6, 1), "up_mbps": round(data.get("ul_throughput", 0) / 1e6, 1),
                            "responsiveness": round(data.get("responsiveness", 0), 1), "base_rtt_ms": round(data.get("base_rtt", 0), 1)}
        except ValueError:
            m.notes.append("throughput test failed")
    if re.search(SCAN_WORDS, q) or re.search(OVERVIEW, q):
        # Through the Swift interpreter: the compiled helper's scan has no network names (walk 1).
        m.scan = [n for n in wifi.parse_lines(shell.run("wifi_scan", ["swift", str(wifi.HELPER_SOURCE), "scan"], timeout=120).text)
                  if "error" not in n]
        m.known = wifi_choice.parse_preferred(shell.run("preferred", ["networksetup", "-listpreferredwirelessnetworks", "en0"]).text)
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
        rises, risen = i.get("rise_events", 0), i.get("rise_share", 0)
        where = _rise_where(m)
        if loss > 2 or med > 80 or risen > 0.05:
            return "not now", f"usual ping {med} ms, {rises} rises of 20 ms or more in {m.seconds:.0f} s, loss {loss}%{where}"
        if rises or loss > 0.5 or med > 50:
            return "with care", f"usual ping {med} ms, {rises} rises of 20 ms or more in {m.seconds:.0f} s, loss {loss}%{where}"
        return "yes", f"usual ping {med} ms, no rise of 20 ms or more in {m.seconds:.0f} s, loss {loss}%"
    t = m.throughput or {}
    down, up = t.get("down_mbps"), t.get("up_mbps")
    if use == "video_call":
        speed = f", {down} / {up} Mb/s down / up" if down is not None else ", speed not measured"
        why = f"round trip {med} ms, jitter {jitter} ms, loss {loss}%{speed}"
        if loss > 3 or med > 200 or (down is not None and (down < 0.2 or up < 0.15)):
            return "not now", why
        if med > 100 or jitter > 30 or loss > 1 or (down is not None and (down < 1.5 or up < 1.5)):
            return "with care", why
        return "yes", why
    if use == "streaming":
        if down is None:
            return "not measured", "throughput not measured"
        if down < 15:
            return "not now", f"download {down} Mb/s"
        return ("yes" if down >= 25 else "with care"), f"download {down} Mb/s"
    if use == "download":
        if down is None:
            return "not measured", "throughput not measured"
        t_down, t_up = transfer_minutes(10, down), transfer_minutes(10, up)
        why = f"10 GB in about {t_down} min down, {t_up} min up ({down} / {up} Mb/s)"
        if not down:
            return "not now", why
        return ("yes" if t_down <= 30 else "with care"), why
    if use == "browsing":
        if loss > 5 or med > 300:
            return "not now", f"median {med} ms, loss {loss}%"
        return ("yes" if med <= 100 and loss <= 2 else "with care"), f"median {med} ms, loss {loss}%"
    return ("yes" if loss <= 5 else "with care"), f"loss {loss}%"


def transfer_minutes(gigabytes: float, mbps: float | None) -> float | None:
    """Minutes to move `gigabytes` (10^9 bytes) at `mbps`."""
    if not mbps:
        return None
    minutes = gigabytes * 8000 / mbps / 60
    return round(minutes, 1) if minutes < 10 else round(minutes)


def bottleneck(m: Measurement, link_rate: float | None, snr: float | None) -> tuple[str | None, str, str]:
    """Where the connection is limited: the Wi-Fi link (between the Mac and the router) or beyond the router.
    Returns (where, reason in English, reason in Korean)."""
    ro, it, t = m.router or {}, m.internet or {}, m.throughput or {}
    if (ro.get("loss_percent") or 0) > 1:
        return "wifi", "packets are lost between the Mac and the router", "맥과 공유기 사이에서 패킷 손실"
    if it.get("rise_events") and ro.get("rise_events", 0) >= max(1, it["rise_events"] // 2):
        return "wifi", "the latency spikes start on the router hop", "공유기까지 구간에서 이미 핑이 튐"
    down = t.get("down_mbps")
    if down and link_rate:
        if link_rate <= 263 or (snr is not None and snr < 25):
            return ("wifi", f"the link runs at {link_rate:.0f} Mb/s: the signal is too weak for the fastest modulation",
                    f"신호가 약해 변조가 내려가 링크 {link_rate:.0f} Mb/s")
        if down < 0.3 * link_rate:
            return ("line", f"the link runs at {link_rate:.0f} Mb/s but the download reaches only {down:.0f} Mb/s",
                    f"링크는 {link_rate:.0f} Mb/s인데 다운로드는 {down:.0f} Mb/s뿐 → 와이파이를 바꿔도 소용없음")
    if (it.get("loss_percent") or 0) > max(1.0, (ro.get("loss_percent") or 0) + 1):
        return "line", "packets are lost beyond the router", "공유기 너머에서 패킷 손실"
    return None, "", ""


VERDICT_MARK = {"yes": "✅", "with care": "⚠️", "not now": "❌", "not measured": "–"}
CARD_USES = [("game", "게임", "Games"), ("video_call", "화상회의", "Calls"), ("messaging", "메신저", "Messaging"),
             ("streaming", "4K", "4K")]
VERDICT_KO = {"yes": "가능", "with care": "주의", "not now": "불가", "not measured": "측정 안 함"}


def card(m: Measurement, r: Report, korean: bool, choice: wifi_choice.Choice | None = None) -> str:
    """Fixed-format summary: the radio chain, what was measured, a verdict per use, the bottleneck, other networks."""
    rssi = [s["rssi_dbm"] for s in m.link if s.get("rssi_dbm")]
    if not rssi:
        return ""
    first, d = m.link[0], m.driver or {}
    signal = statistics.fmean(rssi)
    noise = first.get("noise_dbm")
    snr = signal - noise if noise else None
    current = next((c for c in (choice.candidates if choice else []) if c.current), None)
    mcs = d.get("mcs")
    rate = d.get("tx_mbps") or first.get("tx_mbps")
    name = d.get("ssid") or (current.ssid if current else None) or ("연결된 와이파이" if korean else "joined network")
    chain = [f"{signal:.0f} dBm"]
    if snr is not None:
        chain.append(f"SNR {snr:.0f} dB" + (f" (SINR {current.sinr:.0f})" if current and abs(current.sinr - current.snr) >= 1 else ""))
    if mcs is not None:
        chain.append(f"{wifi_choice.modulation(mcs)} (MCS {int(mcs)})")
    if rate:
        chain.append((f"링크 {rate:.0f} Mb/s" if korean else f"link {rate:.0f} Mb/s"))
    lines = [(f"지금: {name}, 신호 " if korean else f"Now: {name}, signal ") + " → ".join(chain)]

    it, t = m.internet or {}, m.throughput or {}
    measured = []
    if t.get("down_mbps") is not None:
        measured.append((f"다운 {t['down_mbps']:.0f} / 업 {t['up_mbps']:.0f} Mb/s" if korean else f"down {t['down_mbps']:.0f} / up {t['up_mbps']:.0f} Mb/s"))
    if it.get("received"):
        rises = it.get("rise_events", 0)
        where = _rise_where(m)
        place = ""
        if rises:
            place = ("와이파이 구간" if "Wi-Fi link" in where else "공유기 너머") if korean else ("Wi-Fi link" if "Wi-Fi link" in where else "beyond the router")
            place = f"({place})"
        measured.append((f"평소 핑 {it['median_ms']:.0f} ms, 스파이크 {rises}회{place}, 손실 {it.get('loss_percent', 0):.0f}%" if korean
                         else f"usual ping {it['median_ms']:.0f} ms, {rises} spikes{(' ' + place) if place else ''}, loss {it.get('loss_percent', 0):.0f}%"))
    if measured:
        lines.append(("측정: " if korean else "Measured: ") + ", ".join(measured))

    verdicts = []
    for use, ko, en in CARD_USES:
        v, _ = _verdict(use, m)
        if v == "not measured":
            continue
        note = ""
        if use == "game" and v != "yes" and it.get("rise_events"):
            note = (" (와이파이 구간에서 튐)" if korean else " (spikes on the Wi-Fi link)") if "Wi-Fi link" in _rise_where(m) else \
                   (" (공유기 너머에서 튐)" if korean else " (spikes beyond the router)")
        verdicts.append(f"{ko if korean else en} {VERDICT_MARK[v]}{note}")
    if t.get("down_mbps"):
        minutes = transfer_minutes(10, t["down_mbps"])
        verdicts.append(f"10 GB 다운 약 {minutes}분" if korean else f"10 GB download about {minutes} min")
    if verdicts:
        lines.append("   ".join(verdicts))

    where, why_en, why_ko = bottleneck(m, rate, snr)
    if where:
        label = {"wifi": ("병목: 와이파이 구간", "Bottleneck: the Wi-Fi link"), "line": ("병목: 공유기 너머 (회선·다른 트래픽)", "Bottleneck: beyond the router")}[where]
        lines.append(f"{label[0]} ({why_ko})" if korean else f"{label[1]} ({why_en})")

    if choice and choice.candidates:
        others = [c for c in choice.candidates if not c.current][:3]
        if others:
            lines.append("다른 와이파이:" if korean else "Other networks here:")
            for c in others:
                lines.append(f"  {c.ssid} ({c.band_ghz} GHz ch {c.channel}): {c.signal:.0f} dBm, SINR {c.sinr:.0f} dB, "
                             + (f"예상 {wifi_choice.modulation(c.mcs)}, 링크 약 {c.rate:.0f} Mb/s" if korean
                                else f"expected {wifi_choice.modulation(c.mcs)}, link about {c.rate:.0f} Mb/s"))
        b = choice.best
        if choice.action == "switch" and b:
            lines.append(f"→ \"{b.ssid}\"로 바꾸면 신호 {b.signal:.0f} dBm, 예상 {wifi_choice.modulation(b.mcs)}, 링크 약 {b.rate:.0f} Mb/s" if korean
                         else f"→ Switching to \"{b.ssid}\": signal {b.signal:.0f} dBm, expected {wifi_choice.modulation(b.mcs)}, link about {b.rate:.0f} Mb/s")
        elif choice.action == "try" and b:
            lines.append(f"→ \"{b.ssid}\"와 비슷함: 직접 붙어서 비교 (python scripts/wifi_here.py)" if korean
                         else f"→ About equal to \"{b.ssid}\": compare by joining both (python scripts/wifi_here.py)")
        elif choice.action == "stay":
            lines.append("→ 지금 와이파이 유지" if korean else "→ Stay on the current network")
    return "\n".join(lines)


def _rise_where(m: Measurement) -> str:
    """Whether the internet's rises showed on the router hop too (the Wi-Fi link) or not (beyond the router)."""
    ro, it = m.router, m.internet
    if not ro or not it or not it.get("rise_events"):
        return ""
    if ro.get("rise_events", 0) >= max(1, it["rise_events"] // 2):
        awdl = [a for a in m.awdl if a is not None]
        return "; the router hop rose too: the Wi-Fi link" + (", with AWDL active" if awdl and max(awdl) == 1 else "")
    return "; the router hop stayed steady: beyond the router"


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
                                      f"{(ro.get('spike_share') or 0) * 100:.0f}% of replies above 50 ms, {ro.get('rise_events', 0)} rises of 20 ms "
                                      f"or more, loss {ro.get('loss_percent')}% ({span})")
    if it:
        f["latency to the internet"] = (f"median {it.get('median_ms')} ms, p95 {it.get('p95_ms')} ms, jitter {it.get('jitter_ms')} ms, "
                                        f"{it.get('rise_events', 0)} rises of 20 ms or more, loss {it.get('loss_percent')}% ({span})")
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
        if spikes >= 0.03 or (ro.get("rise_share") or 0) >= 0.03:
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
        if verdict in ("with care", "not now") and use in ("game", "video_call") and (
                any(x.code == "awdl_spikes" for x in findings) or "with AWDL active" in why):
            advice += " Turning AirDrop and Handoff off should remove the spikes."
        findings.append(Finding(code, "info" if verdict == "yes" else "warning", f"{USES[use][0].upper() + USES[use][1:]}: {verdict}.",
                                {f"verdict for {USES[use]}": f[f"verdict for {USES[use]}"]}, advice))

    # Nearby networks and Bluetooth, when asked.
    choice = None
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
        choice = _network_choice(m, first, findings, f)
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
    if uses_from_question(question) or m.throughput or choice:
        r.card = card(m, r, bool(re.search(r"[가-힣]", question)), choice)
    return r


def _network_choice(m: Measurement, first: dict, findings: list, f: dict) -> wifi_choice.Choice | None:
    """Which of the networks this Mac has joined is best here (agent/device/wifi_choice.py)."""
    named = [n for n in m.scan if (n.get("ssid") or "").strip()]
    if not named:
        return None
    current = m.driver.get("ssid") if m.driver else None
    cands = wifi_choice.candidates(m.scan, first.get("noise_dbm") or -93, first.get("width_mhz") or 80, m.known or None, current)
    if not cands:
        return None
    choice = wifi_choice.decide(cands)
    for c in cands[:4]:
        f[f"network '{c.ssid}'"] = (f"{c.band_ghz} GHz channel {c.channel}, signal {c.signal:.0f} dBm, SNR {c.snr:.0f} dB, "
                                    f"SINR {c.sinr:.0f} dB, expected link rate {c.rate:.0f} Mb/s" + (" (joined)" if c.current else ""))
    keys = {f"network '{c.ssid}'": f[f"network '{c.ssid}'"] for c in cands[:2]}
    best = choice.best
    if choice.action == "switch":
        findings.append(Finding("network_switch", "warning", f"'{best.ssid}' is clearly better here than the joined network.", keys,
                                f"Join '{best.ssid}' from the Wi-Fi menu ({choice.reason})."))
    elif choice.action == "try":
        findings.append(Finding("network_try", "info", f"'{best.ssid}' and the joined network are about equal here.", keys,
                                "The difference is within the measurement's spread; a short test of both decides "
                                "(scripts/wifi_trial.py, about 1 minute per network, drops the connection briefly)."))
    elif choice.action == "stay":
        findings.append(Finding("network_stay", "info", "The joined network is the best choice here.", keys, choice.reason[0].upper() + choice.reason[1:] + "."))
    elif choice.action == "rank":
        findings.append(Finding("network_rank", "info", f"'{best.ssid}' has the best expected rate here.", keys,
                                "The joined network's name was not readable (wdutil needs the administrator password)."))
    return choice


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
