"""Bluetooth Low Energy signal of one advertising device, followed through a walk (CoreBluetooth via Swift).

One scanner runs for the whole walk (starting it takes about 10 s); each measurement takes the advertisements
heard in its own time window. The device is found by its advertised name.
"""

from __future__ import annotations

import re
import statistics
import subprocess
import threading
import time
from pathlib import Path

SOURCE = Path(__file__).with_name("ble_monitor.swift")
LINE = re.compile(r"t=([\d.]+) rssi=(-?\d+) id=(\S+) name=(.*)")


def parse(line: str):
    m = LINE.match(line.strip())
    if not m:
        return None
    return float(m.group(1)), int(m.group(2)), m.group(3), m.group(4).strip()


class BleMonitor:
    def __init__(self, name: str, seconds: float = 4 * 3600, command: list[str] | None = None):
        self.name, self.heard, self.state = name.lower(), [], None
        self.command = command or ["swift", str(SOURCE), str(seconds)]

    def start(self) -> "BleMonitor":
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._read, daemon=True).start()
        return self

    def _read(self):
        for line in self.process.stdout:
            if line.startswith("state="):
                self.state = int(line.split("=")[1])
                continue
            item = parse(line)
            if item and item[0] and self.name in item[3].lower():
                self.heard.append((item[0], item[1]))

    def window(self, start: float, end: float) -> list[int]:
        return [rssi for t, rssi in self.heard if start <= t <= end and rssi < 0]   # 127 marks "no reading"

    def wait_ready(self, timeout: float = 40) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self.heard:
                return True
            time.sleep(0.5)
        return False

    def stop(self):
        self.process.terminate()


def summary(values: list[int]) -> dict:
    if not values:
        return {"ble": None, "ble_packets": 0}
    return {"ble": float(statistics.median(values)), "ble_packets": len(values)}
