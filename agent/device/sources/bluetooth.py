"""Bluetooth: connected devices and the signal the Mac receives from them (system_profiler, under 0.1 s).

The wireless probe found the signal of a connected mouse in `device_rssi` (-53 dBm); `wdutil` reported 0 dBm
for the same device, so system_profiler is the source.
"""

from __future__ import annotations

import json
import re
import subprocess

AUDIO = {"speaker", "headset", "headphones", "audio"}


INPUT = {"mouse", "keyboard", "trackpad", "gamepad"}


def _device(name: str, props: dict) -> dict:
    m = re.search(r"-?\d+", str(props.get("device_rssi", "")))
    battery = {}
    for key, value in props.items():         # device_batteryLevelMain, ...Left, ...Right, ...Case (Apple devices)
        if key.startswith("device_batteryLevel"):
            level = re.search(r"\d+", str(value))
            if level:
                battery[key[len("device_batteryLevel"):].lower() or "main"] = int(level.group())
    return {"name": name.strip(), "kind": props.get("device_minorType", ""), "rssi_dbm": int(m.group()) if m else None,
            "battery": battery}


def parse_all(text: str) -> dict:
    """Bluetooth on or off, connected devices, and paired devices not connected now. A paired device that macOS
    reports a signal for is in range (the iPhone in the wireless probe: -53 dBm while not connected)."""
    try:
        data = json.loads(text)["SPBluetoothDataType"][0]
    except (ValueError, KeyError, IndexError):
        return {"on": None, "connected": [], "paired": []}
    ctl = data.get("controller_properties", {})
    state = ctl.get("controller_state")
    return {"on": None if state is None else state == "attrib_on", "chip": ctl.get("controller_chipset"),
            "connected": [_device(n, p) for e in data.get("device_connected", []) for n, p in e.items()],
            "paired": [_device(n, p) for e in data.get("device_not_connected", []) for n, p in e.items()]}


def parse(text: str) -> list[dict]:
    """Connected devices: name, kind, signal (None when macOS gives none) and battery levels."""
    return parse_all(text)["connected"]


def connected() -> list[dict]:
    out = subprocess.run(["system_profiler", "SPBluetoothDataType", "-json"], capture_output=True, text=True, timeout=20).stdout
    return parse(out)


def pick(devices: list[dict], name: str | None = None) -> dict | None:
    """The device to follow: the one named, or else the only connected audio device."""
    if name:
        return next((d for d in devices if name.lower() in d["name"].lower()), None)
    audio = [d for d in devices if d["kind"].lower() in AUDIO]
    return audio[0] if len(audio) == 1 else None
