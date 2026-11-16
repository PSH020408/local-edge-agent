"""Battery-aware power policy (agent/device/power_policy.py), against a fake Mac that keeps its energy mode."""

import plistlib
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
        # Energy run E1: High Power gave the same speed as Automatic for qwen3:14b.
        self.assertEqual(pp.choose("heavy", 80, True).mode, pp.AUTOMATIC)
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


class FakeGauge(FakeMac):
    """A battery registry that publishes every 60 s the power controller's running sum of a 1 Hz load."""

    def __init__(self, idle=10.0, busy=40.0, **kwargs):
        super().__init__(**kwargs)
        self.t, self.watts, self.idle, self.busy = 5.0, idle, idle, busy
        self.energy_mj, self.samples = 0, 0
        self.published = (0, 0, 0)  # (update time, running sum in mW*s, samples)

    def clock(self):
        return self.t

    def advance(self, seconds):
        for _ in range(int(round(seconds))):
            self.t += 1
            self.energy_mj += int(self.watts * 1000)
            self.samples += 1
            if int(self.t) % 60 == 0:
                self.published = (int(self.t), self.energy_mj, self.samples)

    def run(self, name, command=None):
        if name == "battery_ioreg":
            data = plistlib.loads(self.battery.encode())
            update, total, count = self.published
            data[0]["UpdateTime"] = update
            data[0]["PowerTelemetryData"].update(AccumulatedSystemLoad=total, SystemLoadAccumulatorCount=count)
            return Output(name, plistlib.dumps(data).decode(), True, 0.0)
        return super().run(name, command)

    def job(self, seconds):
        def run():
            self.watts = self.busy
            self.advance(seconds)
            self.watts = self.idle
            return "done"
        return run


class EnergyTests(unittest.TestCase):
    def test_trapezoids(self):
        self.assertAlmostEqual(pp.integrate([(0, 10.0), (360, 10.0)]), 1.0)
        self.assertAlmostEqual(pp.integrate([(0, 0.0), (3600, 20.0)]), 10.0)

    def test_energy_from_the_running_sum(self):
        # 40 W for 90 s on a 10 W machine: 3,600 J = 1.0 Wh, although the registry publishes only every 60 s.
        gauge = FakeGauge()
        result, energy = pp.measure(gauge, gauge.job(90), sleep=gauge.advance, clock=gauge.clock)
        self.assertEqual(result, "done")
        self.assertAlmostEqual(energy.wh, 1.0, delta=0.02)
        self.assertAlmostEqual(energy.mean_watts, 40.0, delta=1.0)
        self.assertAlmostEqual(energy.idle_watts, 10.0)
        self.assertEqual(energy.check, "ok")

    def test_a_short_job_is_still_measured(self):
        gauge = FakeGauge()
        _, energy = pp.measure(gauge, gauge.job(20), sleep=gauge.advance, clock=gauge.clock)
        self.assertAlmostEqual(energy.wh, 40 * 20 / 3600, delta=0.01)

    def test_a_window_that_missed_the_job_is_flagged(self):
        # Energy run E2: the counter showed less power during a 14B generation than at idle.
        gauge = FakeGauge(busy=10.0)
        gauge.busy = 2.0
        _, energy = pp.measure(gauge, gauge.job(30), sleep=gauge.advance, clock=gauge.clock)
        self.assertIn("missed the job", energy.check)

    def test_run_with_policy_on_battery(self):
        gauge = FakeGauge(charge=70)
        original = pp.measure
        pp.measure = lambda shell, job: original(shell, job, sleep=gauge.advance, clock=gauge.clock)
        try:
            record = pp.run_with_policy(gauge, "light", gauge.job(30), measure_energy=True)
        finally:
            pp.measure = original
        self.assertEqual((record.decision.mode, record.result, gauge.mode), (pp.LOW, "done", 0))
        self.assertAlmostEqual(record.energy.wh, 40 * 30 / 3600, delta=0.01)

    def test_deferred_at_low_charge(self):
        mac = FakeMac(charge=15)
        record = pp.run_with_policy(mac, "heavy", lambda: self.fail("must not run"))
        self.assertFalse(record.ran)
        self.assertEqual(mac.commands, [])

    def test_on_the_adapter_nothing_is_switched(self):
        mac = FakeMac(on_battery=False)
        record = pp.run_with_policy(mac, "heavy", lambda: "done", measure_energy=True)
        self.assertEqual((record.ran, record.energy, mac.commands), (True, None, []))

    def test_an_unplugged_adapter_still_reported_counts_as_battery(self):
        # Run D2: "AC attached" with 0 W in and the battery discharging.
        mac = FakeMac(on_battery=False, mode=2)
        mac.battery = _battery(Amperage=-6316, SystemPowerIn=0)
        record = pp.run_with_policy(mac, "light", lambda: "done")
        self.assertEqual(record.decision.mode, pp.LOW)
        self.assertEqual(mac.commands, [pp.SET_COMMANDS[1], pp.SET_COMMANDS[2]])


if __name__ == "__main__":
    unittest.main()
