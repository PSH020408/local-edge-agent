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
from .sources import bluetooth, continuity, wifi

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
             r"|(?<![a-z])lol(?![a-z])|league of legends|valorant|(?<![a-z])pubg(?![a-z])|overwatch"
             r"|피파|fc\s*온라인|메이플|로스트\s*아크|서든\s*어택|스타크래프트|에이펙스|포트나이트|카운터\s*스트라이크|도타|마인크래프트"
             r"|던파|던전\s*앤\s*파이터|이터널\s*리턴|롤토체스|원신|디아블로|철권|(?<![a-z])apex(?![a-z])|fortnite|(?<![a-z])cs2(?![a-z])"
             r"|counter-?strike|(?<![a-z])dota|minecraft|genshin|diablo|tekken|(?<![a-z])play(ing)?\s+(a\s+)?(games?|online)"),
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
    ssid: str | None = None                           # the joined network's name, when wdutil hides it
    awdl_timeline: list[tuple[float, bool]] = field(default_factory=list)   # sampled every 0.5 s during the pings
    continuity: dict[str, bool | None] = field(default_factory=dict)        # AirDrop, Handoff, widgets, AirPlay
    bluetooth: list[dict] | None = None       # connected devices
    bt: dict = field(default_factory=dict)      # on/off, chip, connected and paired devices
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

    stop = threading.Event()

    def awdl_watch():                     # games and calls: count AWDL wakes while the pings run (experiment C1)
        while not stop.is_set():
            state = awdl_active(shell.run("awdl", ["ifconfig", "awdl0"]).text)
            if state is not None:
                m.awdl_timeline.append((time.time(), bool(state)))
            if stop.wait(0.5):
                break

    threads = [threading.Thread(target=ping, args=("ping_internet", "1.1.1.1")), threading.Thread(target=watch)]
    watcher = threading.Thread(target=awdl_watch, daemon=True) if {"game", "video_call"} & set(uses) else None
    if watcher:
        watcher.start()
    if m.gateway:
        threads.append(threading.Thread(target=ping, args=("ping_router", m.gateway)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    if watcher:
        watcher.join(timeout=2)
        m.continuity = continuity.features(continuity.read(shell))
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
        if not (m.driver or {}).get("ssid"):
            # Newer macOS hides the name from wdutil; CoreWLAN gives it to the Swift interpreter (as for the scan).
            named = wifi.parse_lines(shell.run("wifi_link_named", ["swift", str(wifi.HELPER_SOURCE), "link"], timeout=90).text)
            m.ssid = (named[0].get("ssid") or None) if named else None
    if re.search(BT_WORDS, q):
        m.bt = bluetooth.parse_all(shell.run("bluetooth", ["system_profiler", "SPBluetoothDataType", "-json"], timeout=20).text)
        m.bluetooth = m.bt["connected"]
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
        # Spikes alone give "with care", not "not now", until experiment G1 shows how many a game tolerates: the
        # game's own ping display is averaged, and a player at 8 ms with frequent short spikes can still play.
        late = f", {risen * 100:.0f}% of replies late" if risen > 0.02 else ""
        # A steady share of late replies (C1, AirDrop set to Everyone: a quarter of them, for minutes) is reported
        # with the verdict; it stays "with care" until G1 shows how much a game tolerates (the game's own ping
        # display averages: 74% at 4 ms and 26% at about 50 ms reads as 15-20 ms, as the player sees in LoL).
        if loss > 2 or med > 80:
            return "not now", f"usual ping {med} ms, {rises} rises of 20 ms or more in {m.seconds:.0f} s{late}, loss {loss}%{where}"
        if rises or loss > 0.5 or med > 50:
            return "with care", f"usual ping {med} ms, {rises} rises of 20 ms or more in {m.seconds:.0f} s{late}, loss {loss}%{where}"
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


def game_advice(m: Measurement, snr: float | None, korean: bool) -> list[str]:
    """What to change before a game, in the order the evidence supports. Day to day the Continuity features stay on
    (they are what makes the Mac and the iPhone work together), so they are only touched when a game is asked about
    and the Wi-Fi link itself is fine but the ping is not steady.

    Evidence (experiments.md): C1 - AirDrop set to Everyone delayed 26% of the pings to the router for 3 minutes;
    Contacts Only, Handoff, iPhone widgets and AirPlay Receiver showed no effect; W2 and Room A - AWDL kept down
    removed most spikes."""
    it = m.internet or {}
    verdict, _ = _verdict("game", m)
    if verdict == "yes":
        return ["게임 조언: 지금 설정 그대로 괜찮음" if korean else "Game: fine as it is"]
    rose_on_wifi = it_rose_on_wifi(m) or ((it.get("rise_share") or 0) > 0.02 and (m.router or {}).get("rise_events"))
    if not rose_on_wifi:
        if it.get("rise_events"):
            return ["게임 조언: 공유기 너머에서 튐 → 집 안 다른 기기의 큰 다운로드·업로드를 멈추기 (와이파이 설정으로는 해결 안 됨)" if korean
                    else "Game: the spikes are beyond the router; pause large transfers on other devices (Wi-Fi settings will not help)"]
        return []
    if snr is not None and snr < 25:
        return ["게임 조언: 신호가 약함 → 공유기 가까이 가거나 아래의 더 강한 와이파이로" if korean
                else "Game: the signal is weak; move closer to the router or join a stronger network below"]
    states = m.continuity or {}
    path_ko, path_en = continuity.SETTINGS_PATH_KO, continuity.SETTINGS_PATH
    fallback_ko = "그래도 튀면 게임하는 동안만 AWDL 끄기: python scripts/game_watch.py --awdl off (끝나면 다시 켜짐)"
    fallback_en = "if it still spikes, keep AWDL down while playing: python scripts/game_watch.py --awdl off (back on at the end)"
    if states.get("airdrop"):
        keep = [continuity.FEATURES_KO[k] if korean else continuity.FEATURES[k] for k in ("handoff", "widgets", "airplay") if states.get(k)]
        keep_txt = (f" 켜 둬도 되는 것: {', '.join(keep)}." if korean else f" {', '.join(keep)} can stay on.") if keep else ""
        return [f"게임 조언: AirDrop 끄기 ({path_ko}). 실험 C1·G1에서 핑을 늦춘 유일한 원인.{keep_txt}" if korean
                else f"Game: turn AirDrop off ({path_en}); the only cause of late pings in C1 and G1.{keep_txt}",
                ("  " + fallback_ko) if korean else ("  " + fallback_en.capitalize())]
    on = continuity.on_list(states)
    if on:
        names = ", ".join((continuity.FEATURES_KO if korean else continuity.FEATURES)[k] for k in on)
        return [f"게임 조언: 켜진 기능({names})은 실험 C1에서 영향이 안 보였음 → 그대로 두고, {fallback_ko}" if korean
                else f"Game: {names} showed no effect in C1, leave them; {fallback_en}"]
    return [f"게임 조언: 연속성 기능은 다 꺼져 있음 → {fallback_ko}" if korean else f"Game: Continuity features are all off; {fallback_en}"]


DETAIL_WORDS = r"자세히|상세|기술적|전문|detail|technical"


def signal_label(snr: float | None, korean: bool) -> str:
    """The signal in everyday words, from the SNR thresholds measured in the walks (MCS 9 from about 33 dB)."""
    bands = [(40, "매우 좋음", "excellent"), (30, "좋음", "good"), (20, "보통", "fair"), (10, "약함", "weak")]
    for limit, ko, en in bands:
        if snr is not None and snr >= limit:
            return ko if korean else en
    return "매우 약함" if korean else "very weak"


def _one_in(share: float) -> str:
    n = max(2, round(1 / share)) if share > 0 else 0
    return f"{n}번 중 1번"


KIND_KO = {"mouse": "마우스", "keyboard": "키보드", "trackpad": "트랙패드", "headset": "헤드셋", "headphones": "헤드폰",
           "speaker": "스피커", "gamepad": "게임패드", "audio": "오디오"}
BATTERY_KO = {"main": "", "left": "왼쪽 ", "right": "오른쪽 ", "case": "케이스 "}


def bt_lines(m: Measurement, korean: bool, detail: bool = False) -> list[str]:
    """Bluetooth in the card: on or off, what is connected (with battery), what is paired and in range, and why
    audio or input may cut out."""
    if not m.bt:
        return []
    if m.bt.get("on") is False:
        return ["블루투스: 꺼져 있어요 → 제어 센터에서 켜세요" if korean else "Bluetooth: off; turn it on in Control Centre"]

    def describe(d: dict, connected: bool) -> str:
        kind = (KIND_KO.get(d["kind"].lower(), d["kind"]) if korean else d["kind"].lower()) or ("기기" if korean else "device")
        extra = []
        if d.get("battery"):
            extra.append(("배터리 " + " · ".join(f"{BATTERY_KO.get(k, k + ' ')}{v}%" for k, v in d["battery"].items())) if korean
                         else "battery " + ", ".join(f"{k} {v}%" for k, v in d["battery"].items()))
        if not connected and d["rssi_dbm"] is not None:
            extra.append("근처에 있음" if korean else "in range")
        if detail and d["rssi_dbm"] is not None:
            extra.append(f"{d['rssi_dbm']} dBm")
        return f"{d['name']} ({kind}{', ' + ', '.join(extra) if extra else ''})"

    head = "블루투스: 켜짐" if korean else "Bluetooth: on"
    if detail and m.bt.get("chip"):
        head += f" ({m.bt['chip']})"
    lines = [head]
    conn = m.bt.get("connected") or []
    lines.append(("  연결됨: " if korean else "  Connected: ") + (", ".join(describe(d, True) for d in conn) or ("없음" if korean else "none")))
    paired = m.bt.get("paired") or []
    if paired:
        lines.append(("  연결 안 됨: " if korean else "  Paired, not connected: ") + ", ".join(describe(d, False) for d in paired[:5]))
    low = [d["name"] for d in conn if d.get("battery") and min(d["battery"].values()) <= 20]
    if low:
        lines.append(f"끊김 주의: {', '.join(low)} 배터리가 부족해요 → 충전하세요" if korean else f"May cut out: {', '.join(low)} low on battery")
    weak = [d["name"] for d in conn if d["rssi_dbm"] is not None and d["rssi_dbm"] < -80]
    if weak:
        lines.append(f"끊김 주의: {', '.join(weak)} 신호가 약해요 → 맥 가까이 두세요" if korean else f"May cut out: {', '.join(weak)} signal weak; bring it closer")
    sharing = [d for d in conn if d["kind"].lower() in bluetooth.AUDIO | bluetooth.INPUT]
    if sharing and str((m.link[0] if m.link else {}).get("band_ghz")) == "2.4":
        lines.append("끊김 주의: 맥이 2.4 GHz 와이파이를 써서 블루투스와 같은 전파 대역을 나눠 써요 → 5 GHz 와이파이로 바꾸세요" if korean
                     else "May cut out: the Wi-Fi is on 2.4 GHz, the band Bluetooth uses; join the 5 GHz network")
    return lines


def card(m: Measurement, r: Report, korean: bool, choice: wifi_choice.Choice | None = None, game_asked: bool = False,
         detail: bool = False, bt_only: bool = False) -> str:
    """The connection card: everyday words by default, the radio chain and the evidence on request."""
    if bt_only:
        rssi = [x["rssi_dbm"] for x in m.link if x.get("rssi_dbm")]
        noise = (m.link[0] if m.link else {}).get("noise_dbm")
        snr = statistics.fmean(rssi) - noise if rssi and noise else None
        band = (m.link[0] if m.link else {}).get("band_ghz")
        wifi_line = (f"와이파이: {band} GHz · 신호 {signal_label(snr, True)}" if korean else f"Wi-Fi: {band} GHz, signal {signal_label(snr, False)}") if rssi else ""
        return "\n".join(([wifi_line] if wifi_line else []) + bt_lines(m, korean, detail))
    body = card_detail(m, r, korean, choice, game_asked) if detail else card_simple(m, korean, choice, game_asked)
    extra = bt_lines(m, korean, detail)
    return body + ("\n" + "\n".join(extra) if extra else "")


def card_simple(m: Measurement, korean: bool, choice: wifi_choice.Choice | None = None, game_asked: bool = False) -> str:
    """The same content for anyone: what the signal and speed are like, what works, and what to do."""
    rssi = [x["rssi_dbm"] for x in m.link if x.get("rssi_dbm")]
    if not rssi:
        return ""
    first, d, it, t = m.link[0], m.driver or {}, m.internet or {}, m.throughput or {}
    noise = first.get("noise_dbm")
    snr = statistics.fmean(rssi) - noise if noise else None
    current = next((c for c in (choice.candidates if choice else []) if c.current), None)
    name = d.get("ssid") or m.ssid or (current.ssid if current else None)
    lines = []
    head = [f"와이파이: {name}" if korean and name else ("지금 와이파이" if korean else (f"Wi-Fi: {name}" if name else "Current Wi-Fi")),
            (f"신호 {signal_label(snr, True)}" if korean else f"signal {signal_label(snr, False)}")]
    if t.get("down_mbps") is not None:
        head.append(f"인터넷 속도 받기 {t['down_mbps']:.0f} / 보내기 {t['up_mbps']:.0f} Mb/s" if korean
                    else f"speed {t['down_mbps']:.0f} down / {t['up_mbps']:.0f} up Mb/s")
    lines.append(" · ".join(head))
    if it.get("received"):
        late, rises = (it.get("rise_share") or 0), it.get("rise_events", 0)
        if late >= 0.02:
            steady = f"자주 튐 ({_one_in(late)}은 늦게 옴)" if korean else f"often jumps (1 in {max(2, round(1 / late))} late)"
        elif rises:
            steady = f"가끔 튐 ({m.seconds:.0f}초에 {rises}번)" if korean else f"jumps now and then ({rises} in {m.seconds:.0f} s)"
        else:
            steady = "안정적" if korean else "steady"
        lines.append(f"핑: 평소 {it['median_ms']:.0f} ms, {steady}" if korean else f"Ping: usually {it['median_ms']:.0f} ms, {steady}")
    words = {"yes": ("✅", "✅"), "with care": ("⚠️ 가끔 끊길 수 있음", "⚠️ may stutter"), "not now": ("❌ 어려움", "❌ not now")}
    verdicts = []
    for use, ko, en in CARD_USES:
        v, _ = _verdict(use, m)
        if v in words:
            verdicts.append(f"{ko if korean else en} {words[v][0 if korean else 1]}")
    if t.get("down_mbps"):
        minutes = transfer_minutes(10, t["down_mbps"])
        verdicts.append(f"10 GB 받기 약 {minutes}분" if korean else f"10 GB in about {minutes} min")
    if verdicts:
        lines.append("   ".join(verdicts))

    rose_on_wifi = it_rose_on_wifi(m) or ((it.get("rise_share") or 0) > 0.02 and (m.router or {}).get("rise_events"))
    rate = d.get("tx_mbps") or first.get("tx_mbps")
    where, _, _ = bottleneck(m, rate, snr)
    states = m.continuity or {}
    path = continuity.SETTINGS_PATH_KO if korean else continuity.SETTINGS_PATH
    if game_asked and _verdict("game", m)[0] == "yes":
        lines.append("게임: 지금 그대로 괜찮아요" if korean else "Games: fine as it is")
    elif rose_on_wifi and (snr is None or snr >= 25):
        lines.append("핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요" if korean
                     else "Why it jumps: the Mac briefly leaves the Wi-Fi to talk to nearby Apple devices (your iPhone)")
        if game_asked:
            if states.get("airdrop"):
                lines.append(f"게임 팁: AirDrop을 끄세요 ({path})" if korean else f"Game tip: turn AirDrop off ({path})")
            lines.append("그래도 끊기면: 게임할 때만 이 연결을 꺼 두세요 → python scripts/game_watch.py --awdl off (끝나면 다시 켜져요)" if korean
                         else "Still stuttering: switch it off while playing → python scripts/game_watch.py --awdl off (back on afterwards)")
        else:
            lines.append("게임하려면 \"게임 해도 돼?\"처럼 물어보세요. 바꿀 설정을 알려 드려요" if korean
                         else "Ask about a game to get the settings to change")
    elif where == "wifi" and snr is not None and snr < 25:
        lines.append("느린 이유: 공유기와 멀어서 신호가 약해요 → 공유기 가까이 가거나 아래 와이파이로" if korean
                     else "Why it is slow: the router is far, the signal is weak; move closer or join a network below")
    elif where == "line":
        lines.append("느린 이유: 와이파이는 괜찮고, 인터넷 회선이나 집 안 다른 기기 사용 때문이에요 (와이파이를 바꿔도 같아요)" if korean
                     else "Why it is slow: the Wi-Fi is fine; the internet line or other devices at home are the limit")
    elif game_asked and it.get("rise_events"):
        lines.append("게임 팁: 집 안 다른 기기의 큰 다운로드를 잠시 멈추세요 (와이파이 설정 문제는 아니에요)" if korean
                     else "Game tip: pause large downloads on other devices (not a Wi-Fi setting problem)")

    if choice and choice.candidates:
        b = choice.best
        if choice.action == "switch" and b:
            lines.append(f"추천: \"{b.ssid}\"로 바꾸면 더 빨라요 (신호 {signal_label(b.sinr, True)}, 최대 약 {b.rate:.0f} Mb/s)" if korean
                         else f"Tip: \"{b.ssid}\" is faster here (signal {signal_label(b.sinr, False)}, up to about {b.rate:.0f} Mb/s)")
        elif choice.action == "try" and b:
            lines.append(f"추천: \"{b.ssid}\"도 비슷해요. 직접 비교 → python scripts/wifi_here.py" if korean
                         else f"Tip: \"{b.ssid}\" is about as good; compare → python scripts/wifi_here.py")
        elif choice.action == "stay":
            lines.append("추천: 지금 와이파이가 여기서 제일 좋아요" if korean else "Tip: the current Wi-Fi is the best here")
        unsaved = [c.ssid for c in choice.candidates if not c.saved and not c.current and c.sinr >= 20][:3]
        if unsaved:
            lines.append(f"(비밀번호가 저장 안 된 와이파이는 비교에서 빠져요: {', '.join(unsaved)})" if korean
                         else f"(networks without a saved password are left out: {', '.join(unsaved)})")
    return "\n".join(lines)


def card_detail(m: Measurement, r: Report, korean: bool, choice: wifi_choice.Choice | None = None, game_asked: bool = False) -> str:
    """Fixed-format summary for review: the radio chain, what was measured, a verdict per use, the bottleneck,
    other networks with their expected modulation, and the game advice with its evidence."""
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
    name = d.get("ssid") or m.ssid or (current.ssid if current else None) or ("연결된 와이파이" if korean else "joined network")
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
        late = (it.get("rise_share") or 0) * 100
        late_ko = f", 늦게 온 핑 {late:.0f}%" if late >= 2 else ""
        late_en = f", {late:.0f}% of pings late" if late >= 2 else ""
        measured.append((f"평소 핑 {it['median_ms']:.0f} ms, 스파이크 {rises}회{place}{late_ko}, 손실 {it.get('loss_percent', 0):.0f}%" if korean
                         else f"usual ping {it['median_ms']:.0f} ms, {rises} spikes{(' ' + place) if place else ''}{late_en}, loss {it.get('loss_percent', 0):.0f}%"))
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

    if game_asked:
        lines.extend(game_advice(m, snr, korean))
    elif it.get("rise_events") and "with AWDL active" in _rise_where(m):
        lines.append("핑이 튀는 원인: AirDrop 무선(AWDL). 게임하려면 \"게임 해도 돼?\"라고 물어보면 바꿀 설정을 알려 줌" if korean
                     else "Spikes come from AirDrop's radio (AWDL); ask about a game for the settings to change")
    where, why_en, why_ko = bottleneck(m, rate, snr)
    if where:
        label = {"wifi": ("병목: 와이파이 구간", "Bottleneck: the Wi-Fi link"), "line": ("병목: 공유기 너머 (회선·다른 트래픽)", "Bottleneck: beyond the router")}[where]
        lines.append(f"{label[0]} ({why_ko})" if korean else f"{label[1]} ({why_en})")

    if choice and choice.candidates:
        others = [c for c in choice.candidates if not c.current][:4]
        if others:
            lines.append("다른 와이파이:" if korean else "Other networks here:")
            for c in others:
                unsaved = "" if c.saved else (" (이 맥에 저장 안 됨)" if korean else " (not saved on this Mac)")
                lines.append(f"  {c.ssid} ({c.band_ghz} GHz ch {c.channel}): {c.signal:.0f} dBm, SINR {c.sinr:.0f} dB, "
                             + (f"예상 {wifi_choice.modulation(c.mcs)}, 링크 약 {c.rate:.0f} Mb/s" if korean
                                else f"expected {wifi_choice.modulation(c.mcs)}, link about {c.rate:.0f} Mb/s") + unsaved)
            if any(not c.saved for c in others):
                lines.append("  (저장 안 된 와이파이는 추천에서 빠짐: 한 번 연결해 비밀번호를 저장하면 비교에 들어감)" if korean
                             else "  (networks not saved on this Mac are not recommended: join one once to include it)")
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


def it_rose_on_wifi(m: Measurement) -> bool:
    """The internet's rises showed on the router hop too."""
    return "Wi-Fi link" in _rise_where(m)


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

    # Continuity features that wake AWDL, before a game or a call.
    on = continuity.on_list(m.continuity)
    wakes = continuity.awdl_wakes(m.awdl_timeline) if m.awdl_timeline else None
    if m.continuity:
        f["Continuity features on"] = ", ".join(continuity.FEATURES[k] for k in on) or "none"
    if wakes is not None:
        f["AWDL wakes during the measurement"] = str(wakes)
    # C1 (2026-11-20) could not tie the spikes to any one of the four settings (the all-off round had as many), while
    # keeping AWDL's interface down removed most of them (W2, Room A). So the advice is the proven step; the
    # settings that are on are reported as information.
    if awdl_on and it_rose_on_wifi(m):
        names = ", ".join(continuity.FEATURES[k] for k in on)
        evidence = {"AWDL (AirDrop, Handoff)": "active", "latency to the router": f.get("latency to the router", "")}
        if on:
            evidence["Continuity features on"] = f["Continuity features on"]
        if (m.continuity or {}).get("airdrop"):
            mode = "Everyone" if m.continuity.get("airdrop_everyone") else "Contacts Only"
            findings.append(Finding("airdrop_on", "warning", "AirDrop is on, which keeps AWDL busy.",
                                    {"AirDrop": mode, "latency to the router": f.get("latency to the router", "")},
                                    f"Turn AirDrop off before a game ({continuity.SETTINGS_PATH}): in C1 and in six real LoL "
                                    "matches (G1) it was the only setting that delayed the pings (13-26% late by 20-100 ms)."))
        findings.append(Finding("awdl_game_advice", "warning", "The Wi-Fi spikes start on the router hop while AWDL is up.", evidence,
                                "For a game, keep AWDL down while playing: python scripts/game_watch.py --awdl off "
                                "(it takes AWDL down, watches the ping and brings AWDL back at the end)."
                                + (f" {names} on as well; whether each one matters is not shown yet (C1)." if on else "")))

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
            if dev.get("battery"):
                f[f"battery of '{dev['name']}'"] = ", ".join(f"{k} {v}%" for k, v in dev["battery"].items())
                low = min(dev["battery"].values())
                if low <= 20:
                    findings.append(Finding("bt_battery_low", "warning", f"'{dev['name']}' is low on battery.",
                                            {f"battery of '{dev['name']}'": f[f"battery of '{dev['name']}'"]},
                                            "Charge it: a low battery makes Bluetooth audio and input cut out."))
        if m.bt.get("on") is False:
            f["Bluetooth"] = "off"
            findings.append(Finding("bt_off", "problem", "Bluetooth is off.", {"Bluetooth": "off"},
                                    "Turn it on in Control Centre or System Settings > Bluetooth."))
        paired = m.bt.get("paired") or []
        if paired:
            f["paired, not connected"] = ", ".join(d["name"] + (" (in range)" if d["rssi_dbm"] is not None else "") for d in paired)
        # Bluetooth and 2.4 GHz Wi-Fi share the band; one radio chip takes turns between them, so audio and input
        # devices cut out more when the Mac is on 2.4 GHz Wi-Fi.
        sharing = [d for d in m.bluetooth if d["kind"].lower() in bluetooth.AUDIO | bluetooth.INPUT]
        band = str((m.link[0] if m.link else {}).get("band_ghz"))
        if sharing and band == "2.4":
            f["Wi-Fi band"] = "2.4 GHz (shared with Bluetooth)"
            findings.append(Finding("bt_shares_band", "warning", "The Mac's Wi-Fi is on 2.4 GHz, the band Bluetooth uses.",
                                    {"Wi-Fi band": f["Wi-Fi band"]}, "Join the 5 GHz network of the router: Bluetooth gets the band to itself."))
    for note in m.notes:
        f.setdefault("not measured", note)
    if not [x for x in findings if x.severity in ("warning", "problem")]:
        findings.append(Finding("network_ok", "info", "The Wi-Fi and the internet connection are fine.",
                                {"signal": f["signal"], "latency to the internet": f.get("latency to the internet", "")}, "No action needed."))
    order = {"problem": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda x: order[x.severity])
    if uses_from_question(question) or m.throughput or choice or m.bt:
        asked = [k for k, pattern in USE_WORDS if re.search(pattern, question.lower())]
        bt_only = bool(m.bt) and not asked and not m.throughput and not choice and not re.search(OVERVIEW, question.lower())
        r.card = card(m, r, bool(re.search(r"[가-힣]", question)), choice, game_asked="game" in asked,
                      detail=bool(re.search(DETAIL_WORDS, question.lower())), bt_only=bt_only)
    return r


def _network_choice(m: Measurement, first: dict, findings: list, f: dict) -> wifi_choice.Choice | None:
    """Which of the networks this Mac has joined is best here (agent/device/wifi_choice.py)."""
    named = [n for n in m.scan if (n.get("ssid") or "").strip()]
    if not named:
        return None
    current = (m.driver or {}).get("ssid") or m.ssid
    cands = wifi_choice.candidates(m.scan, first.get("noise_dbm") or -93, first.get("width_mhz") or 80, m.known or None, current)
    if not cands:
        return None
    if not any(c.current for c in cands):
        rssi = [s["rssi_dbm"] for s in m.link if s.get("rssi_dbm")]
        if rssi:
            wifi_choice.mark_current(cands, first.get("channel"), first.get("band_ghz"), statistics.fmean(rssi))
    choice = wifi_choice.decide(cands)
    for c in [c for c in cands if c.saved or c.current][:4]:
        f[f"network '{c.ssid}'"] = (f"{c.band_ghz} GHz channel {c.channel}, signal {c.signal:.0f} dBm, SNR {c.snr:.0f} dB, "
                                    f"SINR {c.sinr:.0f} dB, expected link rate {c.rate:.0f} Mb/s" + (" (joined)" if c.current else ""))
    keys = dict([(k, v) for k, v in f.items() if k.startswith("network '")][:2])
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
