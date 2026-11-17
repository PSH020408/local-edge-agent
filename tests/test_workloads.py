"""Workload set W: scenarios with fixed work and seeded fluctuation, and the runner's power summary."""

import importlib.util
import random
import unittest
from pathlib import Path

from agent.device import workloads as wl

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_workloads", ROOT / "scripts" / "run_workloads.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ScenarioTests(unittest.TestCase):
    def test_every_tier_has_scenarios_and_keys_are_unique(self):
        self.assertEqual(sorted({p.tier for p in wl.PROFILES}), [0, 1, 2, 3, 4, 5])
        keys = [p.key for p in wl.PROFILES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_fluctuation_is_the_same_every_time(self):
        # Every mode must get the same pattern of load.
        a = wl.walk(500, 0.45, 1.0, random.Random(wl.SEED))
        b = wl.walk(500, 0.45, 1.0, random.Random(wl.SEED))
        self.assertEqual(a, b)
        self.assertTrue(all(0.45 <= x <= 1.0 for x in a))
        self.assertGreater(max(a) - min(a), 0.2)  # it does rise and fall

    def test_cpu_work_is_a_fixed_amount(self):
        wl._CAL["cpu_iterations"] = 1000
        self.assertEqual(wl.cpu_work(2.5), 2500)

    def test_interactive_ticks_count_missed_deadlines(self):
        ctx = wl.Ctx(Path("."), {"cpu_iterations": 1000})
        import time
        record = ctx.ticks("test", 4, 0.02, lambda i: time.sleep(0.05 if i % 2 else 0))
        self.assertEqual((record["ticks"], record["missed"]), (4, 2))

    def test_the_quick_check_scales_durations_not_the_calibration_record(self):
        calibration = {"cpu_iterations": 1000, "gpu_product_seconds": 0.002, "train_step_seconds": 0.1, "export_fps": 50.0}
        small = runner.quick(calibration)
        ctx = wl.Ctx(Path("."), small)
        self.assertEqual(ctx.n(600), 60)
        self.assertAlmostEqual(ctx.units_for(10), 100)
        self.assertEqual(calibration["export_fps"], 50.0)


class SummaryTests(unittest.TestCase):
    def monitor(self, publications, samples):
        m = runner.Monitor(None, 120)
        m.publications, m.samples, m.t1 = publications, samples, 120.0
        return m

    def test_system_power_on_the_adapter_from_the_counter(self):
        pubs = [(5, {"power.system_energy_sum": 0.0, "power.system_load_samples": 0}),
                (20, {"power.system_energy_sum": 1000.0, "power.system_load_samples": 20}),
                (80, {"power.system_energy_sum": 5200.0, "power.system_load_samples": 80})]
        samples = [{"chip.combined_power": 30.0, "chip.gpu_active": 90.0, "chip.thermal_pressure_level": 0},
                   {"chip.combined_power": 50.0, "chip.gpu_active": 90.0, "chip.thermal_pressure_level": 1}]
        out = self.monitor(pubs, samples).summary(on_battery=False)
        self.assertEqual(out["system_w"], 65.0)  # 5200 J over 80 samples, from the first publication inside the run
        self.assertEqual((out["chip_w"], out["chip_peak_w"], out["thermal_max"]), (40.0, 50.0, 1))

    def test_system_power_on_battery_two_ways(self):
        pubs = [(15, {"battery.voltage": 12.0, "battery.current": -5.0, "battery.present_capacity": 4000}),
                (75, {"battery.voltage": 12.0, "battery.current": -5.0, "battery.present_capacity": 3986})]
        out = self.monitor(pubs, []).summary(on_battery=True)
        self.assertEqual(out["system_w_vi"], 60.0)
        self.assertAlmostEqual(out["system_w_charge"], 14 / 1000 * 12 * 3600 / 60, places=0)


if __name__ == "__main__":
    unittest.main()
