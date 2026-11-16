"""Sensor probe: what this Mac lets the agent read, and recorded outputs for offline tests.

Runs each macOS command the Stage 7 readers will use, checks that the output holds what the
reader needs, and prints a table: available, missing, or needs rights. Every output is saved in
logs/probe/ (not committed). Outputs used as test fixtures are also saved in tests/fixtures/device/
after identifiers are removed: serial numbers, hardware UUIDs, MAC addresses, network names, the
user name and the computer name; process names are replaced by numbered placeholders, because a
process list shows which applications are installed and running. Bluetooth and Wi-Fi outputs name nearby devices and networks, so
they are kept in logs/probe/ only (Stage 8 reads them there).

Usage:
    python scripts/probe_device.py
    python scripts/probe_device.py --no-fixtures
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "logs" / "probe"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "device"


@dataclass
class Probe:
    name: str           # file name of the recorded output
    purpose: str        # what the Stage 7 reader takes from it
    command: list[str]
    expect: str         # regular expression the output must match for the reading to be usable
    fixture: bool = True  # False: may name other people's devices or networks; kept in logs/probe/ only
    timeout: float = 20
    processes: bool = False  # the output lists processes: names are replaced in the fixture


PROBES = [
    Probe("battery_ioreg", "battery cycle count, capacities, voltage, current, temperature",
          ["ioreg", "-rn", "AppleSmartBattery", "-a"], r"CycleCount"),
    Probe("pmset_batt", "power source, charge, macOS time remaining", ["pmset", "-g", "batt"], r"\d+%"),
    Probe("pmset_ac", "adapter watts", ["pmset", "-g", "ac"], r"Wattage|No adapter"),
    Probe("pmset_settings", "power mode (low / automatic / high)", ["pmset", "-g"], r"powermode|lowpowermode"),
    Probe("pmset_custom", "power mode per power source (adapter and battery)", ["pmset", "-g", "custom"],
          r"AC Power|Battery Power"),
    Probe("pmset_therm", "thermal and performance warnings", ["pmset", "-g", "therm"], r"thermal|performance"),
    Probe("power_profile", "battery condition and maximum capacity as macOS reports it",
          ["system_profiler", "SPPowerDataType", "-json"], r"sppower"),
    Probe("thermal_pressure", "thermal pressure level without rights",
          ["notifyutil", "-g", "com.apple.system.thermalpressurelevel"], r"thermalpressurelevel\s+\d"),
    Probe("sysctl", "core counts, memory size, load average, swap",
          ["sysctl", "hw.ncpu", "hw.perflevel0.physicalcpu", "hw.perflevel1.physicalcpu", "hw.memsize",
           "machdep.cpu.brand_string", "vm.loadavg", "vm.swapusage"], r"hw\.ncpu"),
    Probe("ps_cpu", "CPU use per process", ["ps", "-A", "-o", "%cpu=,%mem=,comm="], r"\d+\.\d", processes=True),
    Probe("top_power", "energy impact per process", ["top", "-l", "2", "-s", "1", "-n", "5", "-o", "power",
                                                     "-stats", "pid,command,cpu,power"], r"POWER", processes=True),
    Probe("gpu_ioreg", "GPU utilisation without rights", ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
          r"Device Utilization"),
    Probe("vm_stat", "memory pages: free, active, compressed, swapped", ["vm_stat"], r"Pages free"),
    Probe("memory_pressure", "system-wide memory free percentage", ["memory_pressure"], r"free percentage"),
    Probe("df", "free space of the system volume", ["df", "-k", "/"], r"\d+%"),
    Probe("diskutil", "disk health status and capacity", ["diskutil", "info", "-plist", "/"], r"SMARTStatus"),
    Probe("iostat", "disk throughput", ["iostat", "-d", "-c", "2", "-w", "1"], r"KB/t|MB/s"),
    Probe("buses", "Thunderbolt, USB and NVMe links", ["system_profiler", "SPThunderboltDataType", "SPUSBDataType",
                                                       "SPNVMeDataType", "-json"], r"SP\w+DataType"),
    Probe("hardware", "model, chip, core counts, memory", ["system_profiler", "SPHardwareDataType", "-json"],
          r"chip_type|machine_model"),
    Probe("powermetrics", "CPU, GPU and Neural Engine frequency, residency and power (needs the sudoers rule)",
          ["sudo", "-n", "/usr/bin/powermetrics", "-n", "1", "-i", "1000", "-s", "cpu_power,gpu_power,ane_power,thermal"],
          r"GPU HW active frequency"),
    Probe("bluetooth", "connected Bluetooth devices and their signal (Stage 8)",
          ["system_profiler", "SPBluetoothDataType", "-json"], r"(?i)rssi", fixture=False),
    Probe("wifi", "Wi-Fi signal, noise, channel, rate (Stage 8)", ["system_profiler", "SPAirPortDataType", "-json"],
          r"spairport_signal_noise|spairport_current_network", fixture=False),
]

_ID_KEYS = (r"[^\"<]*(?:serial|uuid|udid|mac_address|macaddress|address|ssid|bssid|network_name|hostname|computername"
            r"|_name_of|mfgdata|manufacturerdata|manufacturedate|dateoffirstuse)[^\"<]*")


def scrub(text: str, user: str | None = None, host: str | None = None) -> str:
    """Removes identifiers so a recorded output can be committed as a test fixture."""
    # plist: <key>BatterySerialNumber</key> <string>F8Y...</string>
    # The replacement keeps the plist valid: a string becomes REMOVED, a number 0, binary data empty.
    blank = {"string": "REMOVED", "integer": "0", "data": ""}
    text = re.sub(rf"(?is)(<key>{_ID_KEYS}</key>\s*<(string|data|integer)>).*?(</\2>)",
                  lambda m: m.group(1) + blank[m.group(2).lower()] + m.group(3), text)
    # JSON: "serial_number" : "C02..."
    text = re.sub(rf"(?i)(\"{_ID_KEYS}\"\s*:\s*)\"[^\"]*\"", r'\1"REMOVED"', text)
    # ioreg text: "Serial" = "F8Y..."
    text = re.sub(rf"(?i)(\"{_ID_KEYS}\"\s*=\s*)\"[^\"]*\"", r'\1"REMOVED"', text)
    text = re.sub(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b", "REMOVED-UUID", text)
    text = re.sub(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "REMOVED-MAC", text)
    for value, label in ((user, "USER"), (host, "HOST")):
        if value and len(value) >= 3:
            text = re.sub(re.escape(value), label, text, flags=re.IGNORECASE)
    return text


def anonymize_processes(text: str) -> str:
    """Replaces process names by process-1, process-2, ... (the same name gets the same number).

    Handles `ps -o %cpu=,%mem=,comm=` lines, `top -stats pid,command,cpu,power` rows and the
    "sleep prevented by ..." list of `pmset -g`."""
    names: dict[str, str] = {}

    def label(name: str) -> str:
        return names.setdefault(name, f"process-{len(names) + 1}")

    lines = []
    for line in text.splitlines():
        ps = re.match(r"^(\s*\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+)(\S.*)$", line)
        top = re.match(r"^(\d+\s+)(.+?)(\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s*)$", line)
        if top:
            line = top.group(1) + label(top.group(2).strip()) + top.group(3)
        elif ps:
            line = ps.group(1) + label(ps.group(2).strip().rsplit("/", 1)[-1])
        lines.append(line)
    text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return re.sub(r"\((sleep|displaysleep|disk sleep)? ?prevented by [^)]*\)", r"(\1 prevented by REMOVED)", text)


def make_fixture(probe: Probe, output: str, user: str | None, host: str | None) -> str:
    text = scrub(output, user, host)
    if probe.processes or probe.name == "pmset_settings":
        text = anonymize_processes(text)
    return text


def run(probe: Probe) -> dict:
    started = time.monotonic()
    try:
        done = subprocess.run(probe.command, capture_output=True, text=True, timeout=probe.timeout)
        output, code = done.stdout + done.stderr, done.returncode
    except FileNotFoundError:
        output, code = "command not found", 127
    except subprocess.TimeoutExpired:
        output, code = f"timed out after {probe.timeout:.0f} s", 124
    seconds = time.monotonic() - started
    usable = code == 0 and re.search(probe.expect, output) is not None
    if usable:
        state = "available"
    elif "password is required" in output or "a terminal is required" in output:
        state = "needs rights"
    elif code == 127:
        state = "no command"
    else:
        state = "missing"
    return {"name": probe.name, "state": state, "seconds": round(seconds, 2), "code": code,
            "purpose": probe.purpose, "output": output}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-fixtures", action="store_true", help="save outputs in logs/probe/ only")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not args.no_fixtures:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    user, host = getpass.getuser(), socket.gethostname().split(".")[0]

    results = []
    for probe in PROBES:
        result = run(probe)
        (RAW_DIR / f"{probe.name}.txt").write_text(result["output"], encoding="utf-8")
        if probe.fixture and not args.no_fixtures and result["state"] == "available":
            (FIXTURE_DIR / f"{probe.name}.txt").write_text(make_fixture(probe, result["output"], user, host), encoding="utf-8")
        results.append(result)
        print(f"{result['state']:<12} {result['seconds']:>5.1f} s  {probe.name:<17} {probe.purpose}")

    summary = [{k: v for k, v in r.items() if k != "output"} for r in results]
    (RAW_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    counts = {state: sum(r["state"] == state for r in results) for state in ("available", "needs rights", "missing", "no command")}
    print("\n" + ", ".join(f"{n} {state}" for state, n in counts.items() if n))
    print(f"Outputs: {RAW_DIR.relative_to(ROOT)}/" + ("" if args.no_fixtures else f"  Fixtures: {FIXTURE_DIR.relative_to(ROOT)}/"))


if __name__ == "__main__":
    main()
