"""Offline tests for the Stage 7 device layer, on outputs recorded from the Mac (tests/fixtures/device/)."""

import plistlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.readings import Reading, by_name, reading  # noqa: E402
from agent.device.shell import COMMANDS, FixtureShell  # noqa: E402
from agent.device.sources import battery, load, memory, power, thermal  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "device"


class ReadingTests(unittest.TestCase):
    def test_names_units_and_quality_are_checked(self):
        self.assertEqual(reading("battery.voltage", 12.5, "V").quality, "ok")
        self.assertEqual(reading("battery.voltage", None, "V").quality, "missing")
        with self.assertRaises(ValueError):
            reading("voltage", 12.5, "V")            # no source prefix
        with self.assertRaises(ValueError):
            reading("battery.voltage", 12500, "mV")  # readers convert to SI units
        with self.assertRaises(ValueError):
            Reading("battery.voltage", None, "V", "2026-11-16T16:30:00")  # no value but not marked missing


class ShellTests(unittest.TestCase):
    def test_a_missing_recording_is_a_failed_command(self):
        shell = FixtureShell(Path("/nonexistent"))
        output = shell.run("battery_ioreg")
        self.assertFalse(output.ok)
        self.assertEqual(shell.calls, ["battery_ioreg"])

    def test_every_command_has_a_recording(self):
        recorded = {p.stem for p in FIXTURES.glob("*.txt")}
        self.assertEqual(set(COMMANDS) - recorded, set())


class BatteryTests(unittest.TestCase):
    """Values recorded from this Mac on 2026-11-16 at 16:23, on the 100 W adapter, charging paused at 90%."""

    def setUp(self):
        self.shell = FixtureShell(FIXTURES)
        self.values = by_name(battery.read(self.shell) + battery.read_profile(self.shell))

    def value(self, name):
        return self.values[name].value

    def test_registry_values_in_si_units(self):
        self.assertEqual(self.value("battery.cycle_count"), 286)
        self.assertEqual(self.value("battery.design_capacity"), 6249)
        self.assertEqual(self.value("battery.full_charge_capacity"), 5372)
        self.assertAlmostEqual(self.value("battery.voltage"), 12.537)      # 12537 mV
        self.assertAlmostEqual(self.value("battery.temperature"), 30.47)   # 3047 hundredths of a degree
        self.assertEqual(self.value("battery.charge"), 90)

    def test_three_cells_in_series_add_up_to_the_pack_voltage(self):
        cells = [self.value(f"battery.cell{i}_voltage") for i in (1, 2, 3)]
        self.assertAlmostEqual(sum(cells), self.value("battery.voltage"), delta=0.05)
        self.assertNotIn("battery.cell4_voltage", self.values)

    def test_system_input_power_is_voltage_times_current(self):
        self.assertAlmostEqual(self.value("power.system_input"), 15.88)
        self.assertAlmostEqual(self.value("power.system_input_voltage") * self.value("power.system_input_current"),
                               self.value("power.system_input"), delta=0.05)
        self.assertEqual(self.value("power.adapter_watts"), 100)

    def test_no_estimate_is_missing_not_65535(self):
        self.assertFalse(self.values["battery.time_to_empty"].ok)

    def test_health_as_macos_shows_it(self):
        self.assertEqual(self.value("battery.macos_maximum_capacity"), 90.0)
        self.assertEqual(self.value("battery.macos_condition"), "Good")

    def test_a_discharge_current_is_negative(self):
        # The registry stores -1,520 mA as an unsigned 64-bit integer.
        text = plistlib.dumps([{"Amperage": 2**64 - 1520, "Voltage": 11800, "ExternalConnected": False}]).decode()
        values = by_name(battery.parse_registry(text))
        self.assertAlmostEqual(values["battery.current"].value, -1.52)
        self.assertFalse(values["power.system_input"].ok)  # not on the adapter: no input power reading

    def test_unreadable_output_gives_missing_readings_not_an_error(self):
        values = battery.parse_registry("not a plist")
        self.assertTrue(values)
        self.assertTrue(all(not r.ok for r in values))
        shell = FixtureShell(FIXTURES, overrides={"power_profile": "{}"})
        self.assertTrue(all(not r.ok for r in battery.read_profile(shell)))


class PowerTests(unittest.TestCase):
    def test_mode_per_source_and_the_mode_in_use(self):
        # Recorded on the adapter: adapter High Power (2), battery Automatic (0), as System Settings shows.
        values = {r.name: r.value for r in power.read(FixtureShell(FIXTURES))}
        self.assertEqual((values["power.mode_ac"], values["power.mode_battery"]), (2, 0))
        self.assertEqual(values["power.source"], "AC")
        self.assertEqual(values["power.mode_now"], 2)
        self.assertEqual(values["power.charge_state"], "AC attached")
        self.assertIsNone(values["power.macos_time_remaining"])  # no estimate on the adapter

    def test_on_battery_the_battery_mode_applies_and_the_estimate_is_read(self):
        batt = ("Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t54%; discharging; 3:45 remaining present: true\n")
        shell = FixtureShell(FIXTURES, overrides={"pmset_batt": batt})
        values = {r.name: r.value for r in power.read(shell)}
        self.assertEqual((values["power.source"], values["power.mode_now"]), ("Battery", 0))
        self.assertEqual(values["power.macos_time_remaining"], 225)
        self.assertEqual(values["power.charge_state"], "discharging")

    def test_older_macs_with_only_lowpowermode(self):
        values = {r.name: r.value for r in power.parse_custom("Battery Power:\n lowpowermode 1\nAC Power:\n lowpowermode 0\n")}
        self.assertEqual((values["power.mode_battery"], values["power.mode_ac"]), (1, 0))


class ThermalTests(unittest.TestCase):
    def test_recorded_state_nominal_and_no_cap(self):
        values = by_name(thermal.read(FixtureShell(FIXTURES)))
        self.assertEqual((values["thermal.pressure_level"].value, values["thermal.pressure"].value), (0, "nominal"))
        speed = values["thermal.cpu_speed_limit"]
        self.assertEqual((speed.value, speed.quality), (100, "estimated"))  # absence of a record, not a measurement
        self.assertFalse(values["thermal.cpu_available"].ok)

    def test_a_recorded_cap_and_a_moderate_level(self):
        limits = "CPU_Scheduler_Limit \t= 100\nCPU_Available_CPUs \t= 14\nCPU_Speed_Limit \t= 70\n"
        values = by_name(thermal.parse_limits(limits) + thermal.parse_pressure("com.apple.system.thermalpressurelevel 1"))
        self.assertEqual((values["thermal.cpu_speed_limit"].value, values["thermal.cpu_speed_limit"].quality), (70, "ok"))
        self.assertEqual(values["thermal.cpu_available"].value, 14)
        self.assertEqual(values["thermal.pressure"].value, "moderate")


class LoadTests(unittest.TestCase):
    """Recorded at 16:23 on 2026-11-16: M4 Pro, 10 performance and 4 efficiency cores, 20 GPU cores."""

    def test_cores_load_busiest_process_and_gpu(self):
        values = by_name(load.read(FixtureShell(FIXTURES)))
        self.assertEqual([values[f"cpu.{k}"].value for k in ("cores", "performance_cores", "efficiency_cores")], [14, 10, 4])
        self.assertEqual(values["cpu.load_1m"].value, 3.24)
        self.assertEqual((values["process.max_cpu"].value, values["process.max_cpu_name"].value), (42.8, "process-39"))
        self.assertEqual((values["gpu.usage"].value, values["gpu.cores"].value), (27, 20))
        self.assertEqual(values["gpu.memory_in_use"].value, 754810880)

    def test_cpu_use_is_taken_from_the_second_sample(self):
        values = by_name(load.read_top(FixtureShell(FIXTURES)))
        self.assertAlmostEqual(values["cpu.usage"].value, 25.37)  # 19.87% user + 5.50% sys, not the first sample
        self.assertEqual((values["process.energy1_name"].value, values["process.energy1_impact"].value), ("process-5", 118.5))


class MemoryTests(unittest.TestCase):
    def test_pages_become_bytes_and_swap_is_read(self):
        values = by_name(memory.read(FixtureShell(FIXTURES)))
        self.assertEqual(values["memory.total"].value, 24 * 1024**3)
        self.assertEqual(values["memory.free"].value, 20808 * 16384)  # 16 KB pages
        self.assertEqual(values["memory.compressed"].value, 24140 * 16384)
        self.assertEqual(values["memory.swap_used"].value, round(358.5 * 1024 * 1024))
        self.assertEqual(values["memory.swapouts"].value, 2526537)
        self.assertEqual(values["memory.available"].value, 88)

    def test_free_memory_is_small_but_memory_is_available(self):
        # macOS fills unused memory with caches: free is about 1% while 88% is available.
        values = by_name(memory.read(FixtureShell(FIXTURES)))
        self.assertLess(values["memory.free"].value / values["memory.total"].value, 0.02)
        self.assertGreater(values["memory.file_cache"].value, values["memory.free"].value)


if __name__ == "__main__":
    unittest.main()
