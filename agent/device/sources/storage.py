"""SSD: size, free space, health status and current throughput; Thunderbolt, USB and NVMe links.

Free space is taken from the APFS container (`diskutil info -plist /`), not from `df`: on macOS the
system volume is a sealed snapshot, and `df /` reports only its own few gigabytes as used.
The health status is the drive's SMART self-assessment ("Verified" or "Failing").
`iostat` samples twice one second apart; the second line is the current throughput.
"""

from __future__ import annotations

import json
import plistlib
import re

from ..readings import Reading, now, reading


def parse_diskutil(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    try:
        info = plistlib.loads(text.encode("utf-8"))
    except Exception:  # noqa: BLE001
        info = {}
    return [
        reading("storage.total", info.get("APFSContainerSize") or info.get("TotalSize"), "bytes", time),
        reading("storage.free", info.get("APFSContainerFree"), "bytes", time),
        reading("storage.health", info.get("SMARTStatus"), "text", time),
        reading("storage.solid_state", None if "SolidState" not in info else int(bool(info["SolidState"])), "flag", time),
    ]


def parse_iostat(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    rows = re.findall(r"^\s*([\d.]+)\s+(\d+)\s+([\d.]+)\s*$", text, re.M)
    if not rows:
        return [reading("storage.throughput", None, "bytes/s", time), reading("storage.transfers", None, "count", time)]
    _, transfers, megabytes = rows[-1]
    return [
        reading("storage.throughput", round(float(megabytes) * 1024 * 1024), "bytes/s", time),
        reading("storage.transfers", int(transfers), "count", time),
    ]


def _count_items(node) -> int:
    if isinstance(node, dict):
        return sum(_count_items(v) for v in node.get("_items", []) or []) + (1 if "_name" in node and "_items" not in node else 0)
    if isinstance(node, list):
        return sum(_count_items(item) for item in node)
    return 0


def parse_buses(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    nvme = [item for controller in data.get("SPNVMeDataType", []) for item in controller.get("_items", [])]
    return [
        reading("buses.thunderbolt_buses", len(data["SPThunderboltDataType"]) if "SPThunderboltDataType" in data else None, "count", time),
        reading("buses.usb_devices", _count_items(data["SPUSBDataType"]) if "SPUSBDataType" in data else None, "count", time),
        reading("buses.ssd_model", nvme[0].get("device_model") or nvme[0].get("_name") if nvme else None, "text", time),
    ]


def read(shell) -> list[Reading]:
    """Space and health (about 0.1 s): for the sampler every 10 minutes."""
    output = shell.run("diskutil")
    return parse_diskutil(output.text if output.ok else "")


def read_activity(shell) -> list[Reading]:
    """Current throughput (iostat takes about 1 s)."""
    output = shell.run("iostat")
    return parse_iostat(output.text if output.ok else "")


def read_buses(shell) -> list[Reading]:
    output = shell.run("buses")
    return parse_buses(output.text if output.ok else "")


def _names(node, depth: int = 0) -> list[str]:
    """Names of the devices in a system_profiler tree (hubs and the devices behind them)."""
    out = []
    for item in node.get("_items", []) if isinstance(node, dict) else node:
        if isinstance(item, dict):
            if item.get("_name"):
                out.append(("  " * depth) + item["_name"])
            out += _names(item, depth + 1)
    return out


def parse_ports(text: str) -> dict:
    """Ports, what is connected to them and the internal SSD, for questions about buses (added 2026-11-17).

    {"ports": [(port id, speed, connected?, [device names])], "usb": [names], "ssd": {...}}. On this Mac the
    three USB-C ports are Thunderbolt 5 / USB4 buses, "up to 120 Gb/s" each."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    ports = []
    for bus in data.get("SPThunderboltDataType", []):
        tag = bus.get("receptacle_1_tag") or {}
        status = tag.get("receptacle_status_key", "")
        devices = [i.get("_name") for i in bus.get("_items", []) if isinstance(i, dict) and i.get("_name")]
        ports.append((tag.get("receptacle_id_key") or bus.get("_name"), tag.get("current_speed_key"),
                      bool(devices) or (status != "" and "no_devices" not in status), devices))
    ports.sort(key=lambda p: str(p[0]))
    usb = _names(data.get("SPUSBDataType", []))
    nvme = [item for controller in data.get("SPNVMeDataType", []) for item in controller.get("_items", [])]
    ssd = {}
    if nvme:
        disk = nvme[0]
        ssd = {"model": disk.get("device_model") or disk.get("_name"), "size": disk.get("size"),
               "health": disk.get("smart_status"), "trim": disk.get("spnvme_trim_support")}
    return {"ports": ports, "usb": usb, "ssd": ssd}

