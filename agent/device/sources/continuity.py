"""Apple Continuity settings that can wake AWDL (AirDrop's peer-to-peer radio) and so cause Wi-Fi latency spikes.

Read from the preference domains with `defaults`. The keys below are the known ones; experiment C1 records whole
domains before and after each setting is switched, so a wrong or missing key shows up as a diff and can be fixed.

| Feature | System Settings | Key read |
|---|---|---|
| AirDrop | General > AirDrop & Handoff > AirDrop (No One / Contacts Only / Everyone) | com.apple.sharingd DiscoverableMode |
| Handoff | ... > Allow Handoff between this Mac and your iCloud devices | (currentHost) com.apple.coreservices.useractivityd ActivityAdvertisingAllowed, ActivityReceivingAllowed |
| AirPlay Receiver | ... > AirPlay Receiver | (currentHost) com.apple.controlcenter AirplayReceiverEnabled |
| iPhone widgets | ... > iPhone Widgets | com.apple.chronod remoteWidgetsEnabled |

All four keys were confirmed by experiment C1 (2026-11-20): each switch changed exactly these keys.
"""

from __future__ import annotations

import re

DOMAINS = {
    "sharingd": ["defaults", "read", "com.apple.sharingd"],
    "useractivityd": ["defaults", "-currentHost", "read", "com.apple.coreservices.useractivityd"],
    "controlcenter": ["defaults", "-currentHost", "read", "com.apple.controlcenter"],
    "chronod": ["defaults", "read", "com.apple.chronod"],
    "screencontinuity": ["defaults", "read", "com.apple.ScreenContinuity"],
}
FEATURES = {"airdrop": "AirDrop", "handoff": "Handoff", "widgets": "iPhone widgets", "airplay": "AirPlay Receiver",
            "airdrop_everyone": "AirDrop set to Everyone"}
FEATURES_KO = {"airdrop": "AirDrop", "handoff": "Handoff", "widgets": "iPhone 위젯", "airplay": "AirPlay 수신 모드",
               "airdrop_everyone": "AirDrop '모든 사람'"}
SETTINGS_PATH = "System Settings > General > AirDrop & Handoff"
SETTINGS_PATH_KO = "시스템 설정 → 일반 → AirDrop 및 연속성"
LINE = re.compile(r'^ {4}"?([^"=]+?)"?\s*=\s*(.*?);?\s*$')


def parse_defaults(text: str) -> dict[str, str]:
    """Top-level `key = value;` pairs of a `defaults read` dump (nested dictionaries and arrays are skipped)."""
    out = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m and not m.group(2).endswith(("{", "(")):
            out[m.group(1).strip()] = m.group(2).strip().strip('"')
    return out


def read(shell) -> dict[str, dict[str, str]]:
    """Every domain as a dict of its top-level keys (empty when the domain does not exist)."""
    return {name: parse_defaults(shell.run(f"defaults_{name}", command, timeout=10).text) for name, command in DOMAINS.items()}


def _flag(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in ("1", "true", "yes")


def features(dumps: dict[str, dict[str, str]]) -> dict[str, bool | None]:
    """On / off / None (not readable) for each feature."""
    mode = dumps.get("sharingd", {}).get("DiscoverableMode")
    adv = dumps.get("useractivityd", {}).get("ActivityAdvertisingAllowed")
    rcv = dumps.get("useractivityd", {}).get("ActivityReceivingAllowed")
    handoff = None if adv is None and rcv is None else bool(_flag(adv) or _flag(rcv))
    return {"airdrop": None if mode is None else mode.lower() not in ("off", "no one"),
            "airdrop_everyone": None if mode is None else mode.lower() == "everyone",
            "handoff": handoff,
            "widgets": _flag(dumps.get("chronod", {}).get("remoteWidgetsEnabled")),
            "airplay": _flag(dumps.get("controlcenter", {}).get("AirplayReceiverEnabled",
                                                                dumps.get("controlcenter", {}).get("AirplayRecieverEnabled")))}


def on_list(states: dict[str, bool | None] | None) -> list[str]:
    """The features that are on, with AirDrop named once (as 'Everyone' when it is)."""
    on = [k for k, v in (states or {}).items() if v]
    return [k for k in on if not (k == "airdrop" and "airdrop_everyone" in on)]


def diff(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]]) -> list[tuple[str, str, str | None, str | None]]:
    """Keys that changed between two reads: (domain, key, old, new)."""
    out = []
    for domain in sorted(set(before) | set(after)):
        a, b = before.get(domain, {}), after.get(domain, {})
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                out.append((domain, key, a.get(key), b.get(key)))
    return out


def awdl_packets(netstat_text: str) -> int | None:
    """Packets in plus out on awdl0 so far (`netstat -I awdl0`): AWDL's interface stays up most of the time, so
    how busy it is shows in its packet counters, not in its up/down state (C1: active 100% of every round).
    Columns are found from the header (macOS prints Ipkts and Opkts, with byte columns only under -b)."""
    header = None
    for line in netstat_text.splitlines():
        cols = line.split()
        if cols and cols[0] == "Name":
            header = cols
        elif header and len(cols) == len(header) and cols[0] == "awdl0" and cols[2].startswith("<Link"):
            try:
                return int(cols[header.index("Ipkts")]) + int(cols[header.index("Opkts")])
            except (ValueError, IndexError):
                return None
    return None


def awdl_wakes(timeline: list[tuple[float, bool]]) -> int:
    """Times AWDL went from inactive to active."""
    return sum(1 for (_, a), (_, b) in zip(timeline, timeline[1:]) if b and not a)
