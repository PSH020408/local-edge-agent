"""Which of the home's Wi-Fi networks to use here (Stage 8).

Two steps, so the connection is not dropped unless it has to be:

1. Passive ranking (no disconnection). One scan gives the beacon signal of every network nearby. For each network
   the Mac has joined before:
   - SNR  = signal - noise.
   - SINR = signal - (noise + interference). Other networks on the same channel are split by the CCA level
     (-82 dBm on the primary 20 MHz channel, IEEE 802.11):
       heard above -82 dBm -> radios hear each other and take turns (CSMA/CA): the cost is shared airtime,
                              not a lower SINR, so they are counted as "shared", not added to the noise;
       heard below -82 dBm -> they cannot defer to it, so it adds to the noise.
     The worst case (every co-channel network added to the noise) is reported too.
   - Expected link rate from the SINR, through the rate-against-SNR table measured on this Mac in walks 1 and 2.
   Comparing scan values with scan values keeps one source for every network (the link's own reading differs
   from its beacon by a few dB).

2. Decision.
   - stay:   the current network is the best, or the best one would not be meaningfully faster.
   - switch: another network is clearly better: SINR higher by more than the measurement spread (5 dB; the same
             points measured on two days differed by 3 dB RMS) and a faster expected rate.
   - try:    the difference is within the spread: join each candidate for a short test (scripts/wifi_trial.py)
             and keep the one whose measured rate, latency and throughput are best. The test also sees what the
             passive step cannot: the router's own modulation for what it sends (in the download speed) and the
             link behind the router.

Limits: the rate table was measured on 5 GHz, 80 MHz, one stream to one router model; other widths are scaled by
their number of data subcarriers and 2.4 GHz is capped at 64-QAM 5/6 (802.11n). Noise for other bands and widths
is the link's noise scaled by bandwidth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

CCA_DBM = -82.0
MARGIN_DB = 5.0
MIN_GAIN = 1.10          # a switch must promise at least 10% more rate
# SNR (dB) -> link rate (Mb/s): medians of 5 dB bins, walks 1 and 2 (48 points), 5 GHz, 80 MHz, 1 stream;
# made monotonic (the 10-20 dB bins merged). MCS 1 below about 15 dB, MCS 9 from about 35 dB.
RATE_TABLE = [(7.5, 30.0), (15.0, 58.0), (22.5, 263.0), (27.5, 325.0), (32.5, 390.0), (37.5, 433.0)]
SUBCARRIERS = {20: 52, 40: 108, 80: 234, 160: 468}
RATE_MCS7_80 = 325.0     # 64-QAM 5/6, the highest 802.11n modulation, at 80 MHz


def to_mw(dbm: float) -> float:
    return 10 ** (dbm / 10)


def to_dbm(mw: float) -> float:
    return 10 * math.log10(mw)


def sinr(signal: float, noise: float, cochannel: list[float], cca: float = CCA_DBM) -> dict:
    """SNR, SINR (two regimes) and worst-case SINR in dB; `cochannel` are other networks' signals on the channel."""
    below = [i for i in cochannel if i < cca]
    shared = [i for i in cochannel if i >= cca]
    return {"snr": round(signal - noise, 1),
            "sinr": round(signal - to_dbm(to_mw(noise) + sum(map(to_mw, below))), 1),
            "sinr_worst": round(signal - to_dbm(to_mw(noise) + sum(map(to_mw, cochannel))), 1),
            "shared": len(shared)}


def expected_rate(snr_db: float, width_mhz: int = 80, band_ghz: str = "5") -> float:
    """Link rate expected at this SNR/SINR, from the table measured on this Mac."""
    pts = RATE_TABLE
    if snr_db <= pts[0][0]:
        rate = pts[0][1] * max(snr_db, 0) / pts[0][0]
    elif snr_db >= pts[-1][0]:
        rate = pts[-1][1]
    else:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= snr_db <= x1:
                rate = y0 + (y1 - y0) * (snr_db - x0) / (x1 - x0)
                break
    scale = SUBCARRIERS.get(width_mhz, 234) / SUBCARRIERS[80]
    rate *= scale
    if band_ghz == "2.4":
        rate = min(rate, RATE_MCS7_80 * scale)
    return round(rate, 1)


@dataclass
class Candidate:
    ssid: str
    band_ghz: str
    channel: int
    width_mhz: int
    signal: float
    snr: float
    sinr: float
    sinr_worst: float
    shared: int
    rate: float
    current: bool = False


@dataclass
class Choice:
    action: str                       # stay | switch | try | rank (joined network unknown) | none
    best: Candidate | None
    current: Candidate | None
    candidates: list[Candidate] = field(default_factory=list)
    reason: str = ""


def candidates(scan: list[dict], noise: float, link_width: int = 80, known: set[str] | None = None,
               current: str | None = None) -> list[Candidate]:
    """Rank the networks in `known` (all named networks if None) heard in `scan`, best first."""
    known_l = {k.lower() for k in known} if known is not None else None
    strongest: dict[str, dict] = {}
    for n in scan:
        name = (n.get("ssid") or "").strip()
        if not name or n.get("rssi_dbm") is None:
            continue
        if name.lower() not in strongest or n["rssi_dbm"] > strongest[name.lower()]["rssi_dbm"]:
            strongest[name.lower()] = n
    out = []
    for key, n in strongest.items():
        if known_l is not None and key not in known_l:
            continue
        band, channel, width = str(n.get("band_ghz")), n.get("channel"), int(n.get("width_mhz") or 20)
        others = [o["rssi_dbm"] for k, o in strongest.items()
                  if k != key and str(o.get("band_ghz")) == band and o.get("channel") == channel]
        # Unnamed networks on the same channel interfere too.
        others += [o["rssi_dbm"] for o in scan if not (o.get("ssid") or "").strip() and o.get("rssi_dbm") is not None
                   and str(o.get("band_ghz")) == band and o.get("channel") == channel]
        floor = noise + 10 * math.log10(width / link_width)
        q = sinr(n["rssi_dbm"], floor, others)
        out.append(Candidate((n.get("ssid") or "").strip(), band, channel, width, n["rssi_dbm"], q["snr"], q["sinr"],
                             q["sinr_worst"], q["shared"], expected_rate(q["sinr"], width, band),
                             current is not None and key == current.lower()))
    out.sort(key=lambda c: (c.rate, c.sinr, -c.shared), reverse=True)
    return out


def decide(cands: list[Candidate], margin: float = MARGIN_DB) -> Choice:
    if not cands:
        return Choice("none", None, None, cands, "none of the known networks was heard")
    best = cands[0]
    cur = next((c for c in cands if c.current), None)
    if cur is None:
        return Choice("rank", best, None, cands, "the joined network is not among those heard, or its name is unknown")
    if best is cur:
        return Choice("stay", best, cur, cands, "the current network has the best expected rate here")
    if best.rate < cur.rate * MIN_GAIN:
        return Choice("stay", best, cur, cands, f"{best.ssid} would not be meaningfully faster "
                                                f"({best.rate:.0f} against {cur.rate:.0f} Mb/s expected)")
    if best.sinr - cur.sinr > margin:
        return Choice("switch", best, cur, cands, f"{best.ssid}: SINR {best.sinr:.0f} dB against {cur.sinr:.0f} dB, "
                                                  f"expected {best.rate:.0f} against {cur.rate:.0f} Mb/s")
    return Choice("try", best, cur, cands, f"{best.ssid} and {cur.ssid} differ by {best.sinr - cur.sinr:.1f} dB, "
                                           f"within the {margin:.0f} dB spread of the measurement; a short test decides")


def parse_preferred(text: str) -> set[str]:
    """`networksetup -listpreferredwirelessnetworks en0`: the networks this Mac has joined (one per indented line)."""
    return {line.strip() for line in text.splitlines()[1:] if line.startswith(("\t", " ")) and line.strip()}
