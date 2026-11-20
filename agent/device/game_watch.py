"""Latency spikes while playing a real-time game, and where each one came from (Stage 8).

In a fast game the average ping is not what loses a fight; a short rise above the player's usual ping is. A player
at 10-15 ms who jumps to 40-50 ms for a second sees the world 30 ms late (several server updates) and can be hit
before seeing the opponent. So the rule is relative to the player's own baseline, not an absolute limit:

- baseline: the median ping of the last 30 s (follows slow changes, ignores single spikes);
- spike:    replies more than `rise_ms` (20 ms) above the baseline, or lost; replies less than 0.5 s apart join one event;
- where:    the router is pinged at the same moment. If the router's ping rose too (by at least half the rise), the
            delay was on the Wi-Fi link (AWDL, the shared channel, the signal); otherwise beyond the router (the
            internet line, other traffic in the home, the game server's route).
- why:      AWDL (AirDrop's radio) state and link signal are sampled during the game; on this Mac AWDL caused the
            latency spikes of experiment W2.

Verdict for a game session (thresholds to be calibrated with experiment G1):
  smooth: at most one spike per 5 minutes and loss <= 0.5%; occasional: up to one per minute; spiky: more.
"""

from __future__ import annotations

import bisect
import re
import statistics
from dataclasses import dataclass, field

RISE_MS = 20.0
WINDOW_S = 30.0
MERGE_S = 0.5
REPLY = re.compile(r"icmp_seq=(\d+) .*?time=([\d.]+) ms")
TIMEOUT = re.compile(r"Request timeout for icmp_seq (\d+)")


def parse_line(line: str) -> tuple[int, float | None] | None:
    """(sequence, round-trip ms) from one line of `ping`; ms None for a timeout."""
    m = REPLY.search(line)
    if m:
        return int(m.group(1)), float(m.group(2))
    m = TIMEOUT.search(line)
    return (int(m.group(1)), None) if m else None


@dataclass
class Spike:
    start: float
    end: float
    peak_ms: float | None        # None: only lost replies
    baseline_ms: float
    lost: int = 0
    router_rise_ms: float | None = None
    segment: str = "unknown"     # wifi | beyond router | unknown
    awdl: bool | None = None
    rssi_dbm: float | None = None

    @property
    def rise_ms(self) -> float | None:
        return None if self.peak_ms is None else round(self.peak_ms - self.baseline_ms, 1)


@dataclass
class Series:
    """Replies by send time: (t, ms or None for lost)."""
    samples: list[tuple[float, float | None]] = field(default_factory=list)

    def add(self, t: float, ms: float | None) -> None:
        self.samples.append((t, ms))

    def baselines(self, window_s: float = WINDOW_S) -> list[float | None]:
        out, times = [], [t for t, _ in self.samples]
        for i, (t, _) in enumerate(self.samples):
            lo = bisect.bisect_left(times, t - window_s)
            past = [ms for _, ms in self.samples[lo:i + 1] if ms is not None]
            out.append(statistics.median(past) if past else None)
        return out

    def peak_between(self, a: float, b: float) -> float | None:
        values = [ms for t, ms in self.samples if a - 0.2 <= t <= b + 0.2 and ms is not None]
        return max(values) if values else None

    def baseline_at(self, t: float, window_s: float = WINDOW_S) -> float | None:
        values = [ms for s, ms in self.samples if t - window_s <= s <= t and ms is not None]
        return statistics.median(values) if values else None


def spikes(series: Series, rise_ms: float = RISE_MS, window_s: float = WINDOW_S, merge_s: float = MERGE_S) -> list[Spike]:
    events: list[Spike] = []
    base = series.baselines(window_s)
    for (t, ms), b in zip(series.samples, base):
        if b is None:
            continue
        high = ms is None or ms > b + rise_ms
        if not high:
            continue
        if events and t - events[-1].end <= merge_s:
            e = events[-1]
            e.end = t
            if ms is None:
                e.lost += 1
            elif e.peak_ms is None or ms > e.peak_ms:
                e.peak_ms = ms
        else:
            events.append(Spike(t, t, ms, round(b, 1), lost=int(ms is None)))
    return events


def attribute(events: list[Spike], router: Series, rise_ms: float = RISE_MS,
              awdl: list[tuple[float, bool]] | None = None, rssi: list[tuple[float, float]] | None = None) -> None:
    """Mark each spike as on the Wi-Fi link or beyond the router, with the AWDL state and signal at that moment."""
    for e in events:
        peak, base = router.peak_between(e.start, e.end), router.baseline_at(e.start)
        if peak is not None and base is not None:
            e.router_rise_ms = round(peak - base, 1)
            e.segment = "wifi" if e.router_rise_ms >= rise_ms / 2 else "beyond router"
        e.awdl = _state_at(awdl, e.start)
        e.rssi_dbm = _state_at(rssi, e.start)


def _state_at(timeline, t):
    if not timeline:
        return None
    times = [s for s, _ in timeline]
    i = bisect.bisect_right(times, t) - 1
    return timeline[i][1] if i >= 0 else timeline[0][1]


def summary(internet: Series, events: list[Spike]) -> dict:
    if not internet.samples:
        return {"minutes": 0}
    t0, t1 = internet.samples[0][0], internet.samples[-1][0]
    minutes = max((t1 - t0) / 60, 1e-9)
    got = [ms for _, ms in internet.samples if ms is not None]
    lost = len(internet.samples) - len(got)
    rises = [e.rise_ms for e in events if e.rise_ms is not None]
    per_min = len(events) / minutes
    loss = 100 * lost / len(internet.samples)
    verdict = "smooth" if per_min <= 0.2 and loss <= 0.5 else ("occasional" if per_min <= 1 else "spiky")
    return {"minutes": round(minutes, 1), "replies": len(internet.samples), "median_ms": round(statistics.median(got), 1) if got else None,
            "loss_percent": round(loss, 2), "spikes": len(events), "spikes_per_min": round(per_min, 2),
            "largest_rise_ms": max(rises) if rises else None,
            "seconds_in_spikes": round(sum(e.end - e.start + 0.1 for e in events), 1),
            "on_wifi": sum(e.segment == "wifi" for e in events),
            "beyond_router": sum(e.segment == "beyond router" for e in events),
            "with_awdl_active": sum(bool(e.awdl) for e in events),
            "verdict": verdict}


def explain(s: dict) -> str:
    """One paragraph for the player."""
    if not s.get("replies"):
        return "No replies were recorded."
    parts = [f"{s['minutes']} min, usual ping {s['median_ms']} ms, {s['spikes']} spikes (+{RISE_MS:.0f} ms or more), "
             f"{s['spikes_per_min']} per minute: {s['verdict']}."]
    if s["spikes"]:
        parts.append(f"Largest rise +{s['largest_rise_ms']} ms. On the Wi-Fi link: {s['on_wifi']}; beyond the router: "
                     f"{s['beyond_router']}; while AWDL was active: {s['with_awdl_active']}.")
        if s["on_wifi"] >= max(1, s["spikes"] // 2) and s["with_awdl_active"] >= max(1, s["on_wifi"] // 2):
            parts.append("Most spikes were on the Wi-Fi link while AWDL was active: play with AWDL off "
                         "(sudo ifconfig awdl0 down; AirDrop, AirPlay to this Mac and Sidecar stop until it is up again).")
        elif s["on_wifi"] >= max(1, s["spikes"] // 2):
            parts.append("Most spikes were on the Wi-Fi link: a stronger network here, or a channel not shared with another router, would help.")
        elif s["beyond_router"]:
            parts.append("Most spikes were beyond the router: other traffic in the home or the internet line, not the Wi-Fi.")
    return " ".join(parts)
