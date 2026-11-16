"""Power source, power mode and the macOS time-remaining estimate (`pmset -g custom`, `pmset -g batt`).

The power mode is a setting kept per power source by the power management service: one value for
the adapter, one for the battery, applied by macOS when the source changes. `pmset -g custom` is
the authority for it (it matches System Settings); `system_profiler` reports switches that did not
match on this Mac (docs/devlog.md, 2026-11-16), so they are read in battery.py and compared in the
diagnosis layer.

powermode: 0 automatic, 1 low power, 2 high power. Older Macs have only `lowpowermode` (0 or 1).
"""

from __future__ import annotations

import re

from ..readings import Reading, now, reading

MODES = {0: "automatic", 1: "low power", 2: "high power"}
_SECTION = re.compile(r"^(AC Power|Battery Power|UPS Power):\s*$")


def _sources(text: str) -> dict[str, str]:
    """Splits `pmset -g custom` into {"AC": "...", "Battery": "..."} by its section headers."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        header = _SECTION.match(line.strip())
        if header:
            current = header.group(1).split()[0]  # "AC", "Battery", "UPS"
            sections[current] = []
        elif current:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def _mode(section: str) -> int | None:
    found = re.search(r"^\s*powermode\s+(\d)\s*$", section, re.M)
    if found:
        return int(found.group(1))
    low = re.search(r"^\s*lowpowermode\s+(\d)\s*$", section, re.M)
    if low:
        return 1 if low.group(1) == "1" else 0
    return None


def parse_custom(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    sections = _sources(text)
    return [
        reading("power.mode_ac", _mode(sections.get("AC", "")), "level", time),
        reading("power.mode_battery", _mode(sections.get("Battery", "")), "level", time),
    ]


def parse_batt(text: str, time: str | None = None) -> list[Reading]:
    """`Now drawing from 'AC Power'` and, on battery, `...; discharging; 3:45 remaining present: true`."""
    time = time or now()
    drawing = re.search(r"Now drawing from '([^']+)'", text)
    source = None
    if drawing:
        source = "AC" if drawing.group(1).startswith("AC") else "Battery" if "Battery" in drawing.group(1) else drawing.group(1)
    remaining = re.search(r"(\d+):(\d{2}) remaining", text)
    minutes = int(remaining.group(1)) * 60 + int(remaining.group(2)) if remaining else None
    state = re.search(r"\d+%;\s*([^;]+);", text)
    label = state.group(1).strip() if state else None
    # While charging, "0:58 remaining" is the time to full, not the time left (Run D2, B10).
    charging = label == "charging"
    return [
        reading("power.source", source, "text", time),
        reading("power.charge_state", label, "text", time),
        reading("power.macos_time_remaining", None if charging else minutes, "min", time),
        reading("power.macos_time_to_full", minutes if charging else None, "min", time),
    ]


def read(shell) -> list[Reading]:
    custom, batt = shell.run("pmset_custom"), shell.run("pmset_batt")
    time = now()
    readings = parse_custom(custom.text if custom.ok else "", time) + parse_batt(batt.text if batt.ok else "", time)
    values = {r.name: r.value for r in readings}
    mode_now = values.get("power.mode_ac") if values.get("power.source") == "AC" else \
        values.get("power.mode_battery") if values.get("power.source") == "Battery" else None
    return readings + [reading("power.mode_now", mode_now, "level", time)]
