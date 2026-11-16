"""Battery, charger and system input power, from the battery registry (`ioreg -rn AppleSmartBattery -a`)
and the power profile (`system_profiler SPPowerDataType -json`).

This is a driver: it only measures and converts units. Health, remaining time and advice are
computed in the diagnosis layer (agent/agents/battery_agent.py), so every computed value can be
traced to the readings it came from.

Units: the registry reports millivolts, milliamps, milliwatts and hundredths of a degree; these
become V, A, W and °C here. Currents are signed: negative while the battery discharges.
"""

from __future__ import annotations

import json
import plistlib
import re

from ..readings import Reading, now, reading

_NOT_AVAILABLE = 65535  # the registry's value for "no estimate" (time to empty, time to full)


def _signed(value):
    """The registry stores negative currents as unsigned 64-bit integers."""
    if isinstance(value, int) and value >= 2**63:
        return value - 2**64
    return value


def _scaled(value, factor: float):
    value = _signed(value)
    return None if value is None else round(value / factor, 4)


def _minutes(value):
    return None if value in (None, _NOT_AVAILABLE) else value


def _flag(value):
    return None if value is None else int(bool(value))


def parse_registry(text: str, time: str | None = None) -> list[Reading]:
    """Readings from the battery registry. Keys that are absent become missing readings."""
    time = time or now()
    try:
        data = plistlib.loads(text.encode("utf-8"))
        battery = data[0] if isinstance(data, list) else data
        if not isinstance(battery, dict):
            raise ValueError("unexpected registry layout")
    except Exception:  # noqa: BLE001 - unreadable output: every reading missing
        battery = {}
    telemetry = battery.get("PowerTelemetryData") or {}
    adapter = battery.get("AdapterDetails") or {}
    charger = battery.get("ChargerData") or {}
    cells = (battery.get("BatteryData") or {}).get("CellVoltage") or []
    external = battery.get("ExternalConnected")

    values = [
        ("battery.charge", battery.get("CurrentCapacity"), "%"),
        ("battery.cycle_count", battery.get("CycleCount"), "count"),
        ("battery.design_cycle_count", battery.get("DesignCycleCount9C"), "count"),
        ("battery.design_capacity", battery.get("DesignCapacity"), "mAh"),
        ("battery.full_charge_capacity", battery.get("AppleRawMaxCapacity"), "mAh"),
        ("battery.nominal_capacity", battery.get("NominalChargeCapacity"), "mAh"),
        ("battery.present_capacity", battery.get("AppleRawCurrentCapacity"), "mAh"),
        ("battery.voltage", _scaled(battery.get("Voltage"), 1000), "V"),
        ("battery.current", _scaled(battery.get("Amperage"), 1000), "A"),
        ("battery.temperature", _scaled(battery.get("Temperature"), 100), "°C"),
        ("battery.is_charging", _flag(battery.get("IsCharging")), "flag"),
        ("battery.fully_charged", _flag(battery.get("FullyCharged")), "flag"),
        ("battery.time_to_empty", _minutes(battery.get("AvgTimeToEmpty")), "min"),
        ("battery.time_to_full", _minutes(battery.get("AvgTimeToFull")), "min"),
        ("battery.charging_current", _scaled(charger.get("ChargingCurrent"), 1000), "A"),
        ("battery.not_charging_reason", charger.get("NotChargingReason"), "code"),
        ("power.external", _flag(external), "flag"),
        ("power.adapter_watts", adapter.get("Watts") if external else None, "W"),
        ("power.adapter_voltage", _scaled(adapter.get("AdapterVoltage"), 1000) if external else None, "V"),
        ("power.adapter_current", _scaled(adapter.get("Current"), 1000) if external else None, "A"),
        ("power.system_input", _scaled(telemetry.get("SystemPowerIn"), 1000) if external else None, "W"),
        ("power.system_input_voltage", _scaled(telemetry.get("SystemVoltageIn"), 1000) if external else None, "V"),
        ("power.system_input_current", _scaled(telemetry.get("SystemCurrentIn"), 1000) if external else None, "A"),
        ("power.adapter_loss", _scaled(telemetry.get("AdapterEfficiencyLoss"), 1000) if external else None, "W"),
    ]
    readings = [reading(name, value, unit, time) for name, value, unit in values]
    readings += [reading(f"battery.cell{i}_voltage", _scaled(v, 1000), "V", time) for i, v in enumerate(cells, start=1)]
    return readings


def parse_profile(text: str, time: str | None = None) -> list[Reading]:
    """Battery health as macOS shows it in System Settings, and the power-mode switches it reports."""
    time = time or now()
    try:
        sections = json.loads(text).get("SPPowerDataType", [])
    except (ValueError, AttributeError):
        sections = []
    info = next((s for s in sections if s.get("_name") == "spbattery_information"), {})
    power = next((s for s in sections if s.get("_name") == "sppower_information"), {})
    health = info.get("sppower_battery_health_info", {})
    maximum = re.match(r"(\d+(?:\.\d+)?)\s*%", str(health.get("sppower_battery_health_maximum_capacity", "")))

    def switch(source: str, key: str):
        value = (power.get(source) or {}).get(key)
        return None if value is None else int(str(value).lower() in ("yes", "true", "1"))

    return [
        reading("battery.macos_maximum_capacity", float(maximum.group(1)) if maximum else None, "%", time),
        reading("battery.macos_condition", health.get("sppower_battery_health"), "text", time),
        reading("power.profile_ac_low_power_mode", switch("AC Power", "LowPowerMode"), "flag", time),
        reading("power.profile_ac_high_power_mode", switch("AC Power", "HighPowerMode"), "flag", time),
        reading("power.profile_battery_low_power_mode", switch("Battery Power", "LowPowerMode"), "flag", time),
        reading("power.profile_battery_high_power_mode", switch("Battery Power", "HighPowerMode"), "flag", time),
    ]


def read(shell) -> list[Reading]:
    """Fast readings for the background sampler (the registry only, about 20 ms)."""
    output = shell.run("battery_ioreg")
    return parse_registry(output.text if output.ok else "")


def read_profile(shell) -> list[Reading]:
    """Slower readings for questions (system_profiler, about 100 ms)."""
    output = shell.run("power_profile")
    return parse_profile(output.text if output.ok else "")
