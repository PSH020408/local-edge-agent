"""Device states for the test set, built from the outputs recorded on this Mac (tests/fixtures/device/).

Each scenario changes only the readings it is about, so a case tests one diagnosis on otherwise
real data. The changes follow states seen or plausible on this machine: the GPU held at its lowest
clocks (readings of 2026-11-16, 05:04), heavy work on battery, an aged battery, a full SSD.
Outputs are returned as {command name: text}, for FixtureShell(overrides=...).
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "device"


def _text(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def _battery(**changes) -> str:
    data = plistlib.loads(_text("battery_ioreg").encode())
    battery = data[0]
    for key, value in changes.items():
        if key == "CellVoltage":
            battery["BatteryData"]["CellVoltage"] = value
        elif key in ("Watts",):
            battery["AdapterDetails"]["Watts"] = value
        elif key == "ChargingCurrent":
            battery["ChargerData"]["ChargingCurrent"] = value
        elif key == "SystemPowerIn":
            battery["PowerTelemetryData"]["SystemPowerIn"] = value
        else:
            battery[key] = value if not (key == "Amperage" and value < 0) else value + 2**64
    return plistlib.dumps(data).decode()


def _on_battery(charge: int, amps: float, remaining: str | None, mode: int = 0) -> dict:
    present = round(5372 * charge / 100)
    milliamps = round(amps * 1000)
    return {
        "battery_ioreg": _battery(ExternalConnected=False, IsCharging=False, CurrentCapacity=charge,
                                  AppleRawCurrentCapacity=present, Amperage=milliamps, InstantAmperage=milliamps,
                                  Voltage=11600 + 10 * charge, AvgTimeToEmpty=65535),
        "pmset_batt": "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t"
                      f"{charge}%; discharging; {remaining + ' remaining' if remaining else '(no estimate)'} present: true\n",
        "pmset_custom": _text("pmset_custom").replace("powermode            0", f"powermode            {mode}", 1),
    }


def _ps(total_busy: float, top: tuple[str, float] | None = None) -> str:
    """A process list whose CPU adds up to `total_busy` percent of one core."""
    lines = []
    if top:
        lines.append(f" {top[1]:5.1f}  2.0 {top[0]}")
        total_busy -= top[1]
    per = 40.0
    i = 900
    while total_busy > 0:
        share = min(per, total_busy)
        lines.append(f" {share:5.1f}  1.0 process-{i}")
        total_busy -= share
        i += 1
    return "\n".join(lines + ["  0.0  0.1 process-1"]) + "\n"


def _gpu(usage: int) -> str:
    return re.sub(r'"Device Utilization %"=\d+', f'"Device Utilization %"={usage}', _text("gpu_ioreg"))


def _powermetrics(gpu_mhz: int, gpu_active: float, gpu_mw: int, pressure: str, cpu_mw: int = 475) -> str:
    text = _text("powermetrics")
    text = re.sub(r"GPU HW active frequency: \d+ MHz", f"GPU HW active frequency: {gpu_mhz} MHz", text)
    text = re.sub(r"GPU HW active residency:\s*[\d.]+%", f"GPU HW active residency: {gpu_active:6.2f}%", text)
    text = re.sub(r"GPU Power: \d+ mW", f"GPU Power: {gpu_mw} mW", text)
    text = re.sub(r"CPU Power: \d+ mW", f"CPU Power: {cpu_mw} mW", text)
    text = re.sub(r"Combined Power \(CPU \+ GPU \+ ANE\): \d+ mW", f"Combined Power (CPU + GPU + ANE): {cpu_mw + gpu_mw + 3} mW", text)
    return re.sub(r"Current pressure level: \w+", f"Current pressure level: {pressure}", text)


def _heavy() -> dict:
    """A local model running: CPU about 82% of all cores, GPU 86%, about 37 W on the chip."""
    return {"ps_cpu": _ps(1150, ("process-ollama", 560.0)), "gpu_ioreg": _gpu(86),
            "powermetrics": _powermetrics(1310, 86.0, 12200, "Nominal", cpu_mw=24500)}


def _profile(maximum: str, condition: str) -> str:
    text = _text("power_profile")
    text = re.sub(r'"sppower_battery_health_maximum_capacity" : "[^"]*"', f'"sppower_battery_health_maximum_capacity" : "{maximum}"', text)
    return re.sub(r'"sppower_battery_health" : "[^"]*"', f'"sppower_battery_health" : "{condition}"', text)


def _diskutil(free_share: float | None = None, smart: str | None = None) -> str:
    info = plistlib.loads(_text("diskutil").encode())
    if free_share is not None:
        info["APFSContainerFree"] = int(info["APFSContainerSize"] * free_share)
    if smart:
        info["SMARTStatus"] = smart
    return plistlib.dumps(info).decode()


def _memory_short() -> dict:
    return {
        "memory_pressure": re.sub(r"free percentage: \d+%", "free percentage: 7%", _text("memory_pressure")),
        "sysctl": re.sub(r"used = [\d.]+M\s+free = [\d.]+M", "used = 1890.00M  free = 158.00M", _text("sysctl")),
    }


SCENARIOS: dict[str, dict] = {
    "recorded": {},
    "on_battery_light": _on_battery(70, -0.85, "5:10") | {"ps_cpu": _ps(160)},
    "on_battery_heavy": _on_battery(45, -4.6, "0:52") | _heavy(),
    "low_charge_heavy": _on_battery(15, -4.4, "0:16") | _heavy(),
    "aged_battery": {"battery_ioreg": _battery(AppleRawMaxCapacity=4700, CycleCount=1043),
                     "power_profile": _profile("76%", "Service Recommended")},
    "aging_watch": {"battery_ioreg": _battery(AppleRawMaxCapacity=5150, CycleCount=640),
                    "power_profile": _profile("83%", "Normal")},
    "hot_battery": {"battery_ioreg": _battery(Temperature=3850)} | _heavy(),
    "cell_imbalance": {"battery_ioreg": _battery(CellVoltage=[4180, 4090, 4179])},
    "charging": {"battery_ioreg": _battery(IsCharging=True, CurrentCapacity=60, AppleRawCurrentCapacity=3223,
                                           Amperage=2900, ChargingCurrent=2900),
                 "pmset_batt": "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t60%; charging; 0:58 remaining present: true\n"},
    "weak_charger": {"battery_ioreg": _battery(Amperage=-1250, Watts=30, SystemPowerIn=29400)} | _heavy(),
    # Seen live in Run D2 (21:22): adapter reported as connected, 0 W in, the battery carrying about 75 W.
    "adapter_not_supplying": {"battery_ioreg": _battery(Amperage=-6316, Voltage=11807, AppleRawCurrentCapacity=4658,
                                                        CellVoltage=[3935, 3944, 3927], SystemPowerIn=0)} | _heavy(),
    # Seen live in Run D3 (21:35): the adapter gave 72 W of its 100 W and the battery added 3.0 W.
    "adapter_headroom": {"battery_ioreg": _battery(Amperage=-240, SystemPowerIn=72000)},
    "ac_not_high_power_heavy": {"pmset_custom": _text("pmset_custom").replace("powermode            2", "powermode            0")} | _heavy(),
    "gpu_held_low": {"powermetrics": _powermetrics(443, 99.88, 3151, "Moderate"),
                     "thermal_pressure": "com.apple.system.thermalpressurelevel 1\n", "gpu_ioreg": _gpu(99)},
    "thermal_heavy": _heavy() | {"powermetrics": _powermetrics(1180, 95.0, 14800, "Heavy", cpu_mw=26000),
                                 "thermal_pressure": "com.apple.system.thermalpressurelevel 2\n"},
    "runaway": {"ps_cpu": _ps(320, ("process-stuck", 198.0))},
    "memory_short": _memory_short(),
    "storage_low": {"diskutil": _diskutil(free_share=0.04)},
    "storage_failing": {"diskutil": _diskutil(smart="Failing")},
    "busy_cpu": {"ps_cpu": _ps(1300)},
}


def overrides(name: str) -> dict:
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; scenarios: {', '.join(SCENARIOS)}")
    return SCENARIOS[name]
