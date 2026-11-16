"""Battery-aware power policy (agent/device/power_policy.py), against a fake Mac that keeps its energy mode."""

import unittest
from pathlib import Path

from agent.device import power_policy as pp
from agent.device.shell import Output
from evals.device.scenarios import _battery, _text

FIXTURES = Path(__file__).parent / "fixtures" / "device"


class FakeMac:
    """Replays the recorded battery and keeps a battery energy mode that `pmset -b powermode N` changes."""

    def __init__(self, mode=0, on_battery=True, charge=70, can_set=True):
        self.mode, self.can_set, self.commands = mode, can_set, []
        changes = dict(ExternalConnected=False, IsCharging=False, CurrentCapacity=charge, Amperage=-1000) if on_battery else {}
        self.battery = _battery(**changes)

    def run(self, name, command=None):
        if name == "pmset_set_mode":
            self.commands.append(command)
            if not self.can_set:
                return Output(name, "", False, 0.0, "sudo: a password is required")
            self.mode = int(command[-1])
            return Output(name, "", True, 0.0)
        if name == "pmset_custom":
            text = _text("pmset_custom").replace("powermode            0", f"powermode            {self.mode}", 1)
            return Output(name, text, True, 0.0)
        if name == "battery_ioreg":
            return Output(name, self.battery, True, 0.0)
        raise AssertionError(f"unexpected command {name}")


class ChooseTests(unittest.TestCase):
    def test_the_table(self):
        self.assertIsNone(pp.choose("heavy", 80, on_battery=False).mode)
        self.assertEqual(pp.choose("light", 80, True).mode, pp.LOW)
        self.assertEqual(pp.choose("medium", 80, True).mode, pp.AUTOMATIC)
        self.assertEqual(pp.choose("heavy", 80, True).mode, pp.HIGH)
        self.assertEqual(pp.choose("heavy", 40, True).mode, pp.AUTOMATIC)
        low = pp.choose("heavy", 15, True)
        self.assertEqual((low.mode, low.defer), (pp.LOW, True))
        self.assertFalse(pp.choose("light", 15, True).defer)


class BatteryModeTests(unittest.TestCase):
    def test_switch_and_restore(self):
        mac = FakeMac(mode=0)
        with pp.BatteryMode(mac, pp.HIGH) as switch:
            self.assertEqual(mac.mode, pp.HIGH)
        self.assertEqual(mac.mode, 0)
        self.assertTrue(switch.restored)
        self.assertEqual(mac.commands, [pp.SET_COMMANDS[2], pp.SET_COMMANDS[0]])

    def test_only_the_allowed_commands_are_run(self):
        mac = FakeMac(mode=0)
        for target in (pp.LOW, pp.HIGH, pp.AUTOMATIC):
            with pp.BatteryMode(mac, target):
                pass
        allowed = list(pp.SET_COMMANDS.values())
        self.assertTrue(all(c in allowed for c in mac.commands))
        with self.assertRaises(ValueError):
            pp.BatteryMode(mac, 3)

    def test_restored_when_the_job_fails(self):
        mac = FakeMac(mode=0)
        with self.assertRaises(RuntimeError):
            with pp.BatteryMode(mac, pp.LOW):
                raise RuntimeError("job failed")
        self.assertEqual(mac.mode, 0)

    def test_the_users_change_during_the_job_is_kept(self):
        mac = FakeMac(mode=0)
        with pp.BatteryMode(mac, pp.HIGH) as switch:
            mac.mode = pp.LOW  # the user picks Low Power in System Settings meanwhile
        self.assertEqual(mac.mode, pp.LOW)
        self.assertFalse(switch.restored)
        self.assertIn("left as it is", switch.notes[-1])

    def test_no_permission_runs_the_job_unchanged(self):
        mac = FakeMac(mode=0, can_set=False)
        with pp.BatteryMode(mac, pp.HIGH) as switch:
            pass
        self.assertEqual(mac.mode, 0)
        self.assertFalse(switch.changed)
        self.assertEqual(len(mac.commands), 1)  # no restore attempt after a failed switch
        self.assertIn("password", switch.notes[0])

    def test_nothing_to_do(self):
        mac = FakeMac(mode=2)
        with pp.BatteryMode(mac, pp.HIGH), pp.BatteryMode(mac, None):
            pass
        self.assertEqual(mac.commands, [])


class EnergyTests(unittest.TestCase):
    def test_trapezoids(self):
        self.assertAlmostEqual(pp.integrate([(0, 10.0), (360, 10.0)]), 1.0)
        self.assertAlmostEqual(pp.integrate([(0, 0.0), (3600, 20.0)]), 10.0)

    def test_run_with_policy_on_battery(self):
        mac = FakeMac(mode=0, charge=70)
        clock = iter(range(0, 1000, 30))
        meter_clock = lambda: next(clock)  # noqa: E731
        original = pp.EnergyMeter.__init__

        def fast(self, shell, period=1.0, clock=None):
            original(self, shell, period=0.001, clock=meter_clock)

        pp.EnergyMeter.__init__ = fast
        try:
            record = pp.run_with_policy(mac, "heavy", lambda: "done")
        finally:
            pp.EnergyMeter.__init__ = original
        self.assertEqual((record.decision.mode, record.result, mac.mode), (pp.HIGH, "done", 0))
        self.assertGreater(record.energy.wh_integrated, 0)  # 1 A from about 12.3 V: about 12 W

    def test_deferred_at_low_charge(self):
        mac = FakeMac(charge=15)
        record = pp.run_with_policy(mac, "heavy", lambda: self.fail("must not run"))
        self.assertFalse(record.ran)
        self.assertEqual(mac.commands, [])

    def test_on_the_adapter_nothing_is_switched(self):
        mac = FakeMac(on_battery=False)
        record = pp.run_with_policy(mac, "heavy", lambda: "done")
        self.assertEqual((record.ran, record.energy, mac.commands), (True, None, []))

    def test_an_unplugged_adapter_still_reported_counts_as_battery(self):
        # Run D2: "AC attached" with 0 W in and the battery discharging.
        mac = FakeMac(on_battery=False)
        mac.battery = _battery(Amperage=-6316, SystemPowerIn=0)
        clock = iter(range(0, 1000, 30))
        original = pp.EnergyMeter.__init__
        pp.EnergyMeter.__init__ = lambda self, shell, period=1.0, clock_=None: original(self, shell, 0.001, lambda: next(clock))
        try:
            record = pp.run_with_policy(mac, "heavy", lambda: "done")
        finally:
            pp.EnergyMeter.__init__ = original
        self.assertEqual(record.decision.mode, pp.HIGH)
        self.assertIsNotNone(record.energy)


if __name__ == "__main__":
    unittest.main()
