"""Bluetooth: connected devices and the signal the Mac receives from them (system_profiler, under 0.1 s).

The wireless probe found the signal of a connected mouse in `device_rssi` (-53 dBm); `wdutil` reported 0 dBm
for the same device, so system_profiler is the source.
"""

from __future__ import annotations

import json
import re
import subprocess

AUDIO = {"speaker", "headset", "headphones", "audio"}


def parse(text: str) -> list[dict]:
    """Connected devices: name, kind and signal (None when macOS gives no signal for the device)."""
    try:
        data = json.loads(text)["SPBluetoothDataType"][0]
    except (ValueError, KeyError, IndexError):
        return []
    devices = []
    for entry in data.get("device_connected", []):
        for name, props in entry.items():
            m = re.search(r"-?\d+", str(props.get("device_rssi", "")))
            devices.append({"name": name.strip(), "kind": props.get("device_minorType", ""),
                            "rssi_dbm": int(m.group()) if m else None})
    return devices


def connected() -> list[dict]:
    out = subprocess.run(["system_profiler", "SPBluetoothDataType", "-json"], capture_output=True, text=True, timeout=20).stdout
    return parse(out)


def pick(devices: list[dict], name: str | None = None) -> dict | None:
    """The device to follow: the one named, or else the only connected audio device."""
    if name:
        return next((d for d in devices if name.lower() in d["name"].lower()), None)
    audio = [d for d in devices if d["kind"].lower() in AUDIO]
    return audio[0] if len(audio) == 1 else None
