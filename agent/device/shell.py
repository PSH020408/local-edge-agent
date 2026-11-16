"""Runs the macOS commands the readers need, or replays recorded outputs in tests.

Readers never call subprocess themselves: they ask a shell for a named command. LiveShell runs it
on the Mac with a timeout; FixtureShell returns the output recorded by scripts/probe_device.py
(tests/fixtures/device/<name>.txt). The same reader code is tested without the hardware, the way a
driver is tested against a mock of its device.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# Command names match the probe (scripts/probe_device.py) and the fixture file names.
COMMANDS: dict[str, list[str]] = {
    "battery_ioreg": ["ioreg", "-rn", "AppleSmartBattery", "-a"],
    "pmset_batt": ["pmset", "-g", "batt"],
    "pmset_ac": ["pmset", "-g", "ac"],
    "pmset_settings": ["pmset", "-g"],
    "pmset_custom": ["pmset", "-g", "custom"],  # settings per power source: the authority for the power mode
    "pmset_therm": ["pmset", "-g", "therm"],
    "power_profile": ["system_profiler", "SPPowerDataType", "-json"],
    "thermal_pressure": ["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
    "sysctl": ["sysctl", "hw.ncpu", "hw.perflevel0.physicalcpu", "hw.perflevel1.physicalcpu", "hw.memsize",
               "machdep.cpu.brand_string", "vm.loadavg", "vm.swapusage"],
    "ps_cpu": ["ps", "-A", "-o", "%cpu=,%mem=,comm="],
    "top_power": ["top", "-l", "2", "-s", "1", "-n", "5", "-o", "power", "-stats", "pid,command,cpu,power"],
    "gpu_ioreg": ["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
    "vm_stat": ["vm_stat"],
    "memory_pressure": ["memory_pressure"],
    "df": ["df", "-k", "/"],
    "diskutil": ["diskutil", "info", "-plist", "/"],
    "iostat": ["iostat", "-d", "-c", "2", "-w", "1"],
    "buses": ["system_profiler", "SPThunderboltDataType", "SPUSBDataType", "SPNVMeDataType", "-json"],
    "hardware": ["system_profiler", "SPHardwareDataType", "-json"],
    "powermetrics": ["sudo", "-n", "/usr/bin/powermetrics", "-n", "1", "-i", "1000",
                     "-s", "cpu_power,gpu_power,ane_power,thermal"],
}


@dataclass
class Output:
    name: str
    text: str
    ok: bool
    seconds: float
    error: str = ""


class LiveShell:
    """Runs the commands on this Mac."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def run(self, name: str, command: list[str] | None = None) -> Output:
        """Runs COMMANDS[name], or `command` when a reader needs other arguments (a capture of n seconds)."""
        command = command or COMMANDS[name]
        started = time.monotonic()
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout)
        except FileNotFoundError:
            return Output(name, "", False, time.monotonic() - started, "command not found")
        except subprocess.TimeoutExpired:
            return Output(name, "", False, time.monotonic() - started, f"timed out after {self.timeout:.0f} s")
        seconds = time.monotonic() - started
        if done.returncode != 0:
            return Output(name, done.stdout, False, seconds, done.stderr.strip()[:200] or f"exit code {done.returncode}")
        return Output(name, done.stdout, True, seconds)


class FixtureShell:
    """Replays recorded outputs; a missing recording behaves like a command that failed."""

    def __init__(self, folder: Path, overrides: dict[str, str] | None = None) -> None:
        self.folder = Path(folder)
        self.overrides = overrides or {}  # name -> text, to test unusual outputs
        self.calls: list[str] = []

    def run(self, name: str, command: list[str] | None = None) -> Output:
        self.calls.append(name)
        if name in self.overrides:
            text = self.overrides[name]
            if text is None:  # a command that fails, for tests of missing readings
                return Output(name, "", False, 0.0, "failed in test")
            return Output(name, text, True, 0.0)
        path = self.folder / f"{name}.txt"
        if not path.exists():
            return Output(name, "", False, 0.0, "no recording")
        return Output(name, path.read_text(encoding="utf-8"), True, 0.0)
