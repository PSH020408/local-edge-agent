"""Power feedback controller (agent/device/controller.py) on a simulated plant.

The plant follows the measurements of 2026-11-17: power rises to the job's full-speed power within about a
second while the job runs and falls to idle while it rests, and the full-speed power itself decays from a
burst level toward a sustained level with a 12 s time constant. Like testing a controller against a model of
the hardware before running it on the hardware.
"""

import unittest

from agent.device.controller import PI, Trace, run_paced, step_metrics


class Plant:
    def __init__(self, burst=60.0, sustained=34.0, idle=0.5, chunk=0.2):
        self.t, self.power, self.burst, self.sustained, self.idle, self.chunk_s = 0.0, idle, burst, sustained, idle, chunk
        self.budget = burst
        self.raw = self.smooth = None
        self._next_sample, self._acc, self._n = 1.0, 0.0, 0
        self.count = 0

    def clock(self):
        return self.t

    def _advance(self, seconds, busy):
        steps = max(1, int(seconds / 0.01))
        for _ in range(steps):
            dt = seconds / steps
            self.budget += (self.sustained - self.budget) * dt / 12.0          # the burst budget decays (12 s)
            goal = self.budget if busy else self.idle
            self.power += (goal - self.power) * min(1.0, dt / 0.3)             # power follows the load quickly
            self.t += dt
            self._acc += self.power * dt
            self._n += dt
            if self.t >= self._next_sample:                                     # powermetrics: one mean per second
                watts = self._acc / self._n
                self.raw = watts
                self.smooth = watts if self.smooth is None else 0.4 * watts + 0.6 * self.smooth
                self.count += 1
                self._acc = self._n = 0.0
                self._next_sample += 1.0

    def chunk(self):
        self._advance(self.chunk_s, busy=True)

    def sleep(self, seconds):
        self._advance(seconds, busy=False)


class ControllerTests(unittest.TestCase):
    def run_steps(self, targets, seconds=90, feedforward=True):
        plant = Plant()
        pi = PI.tuned(targets[0], full_watts=45, idle_watts=0.5, feedforward=feedforward)
        trace = Trace()
        for k, target in enumerate(targets):
            pi.target = target
            run_paced(plant.chunk, seconds, plant, pi, trace, f"target {target}", clock=plant.clock, sleep=plant.sleep, start=0.0)
        return trace

    def test_holds_the_target_and_follows_a_step(self):
        trace = self.run_steps([20.0, 12.0])
        for target in (20.0, 12.0):
            m = step_metrics([r for r in trace.rows if r["phase"] == f"target {target}"], target)
            self.assertIsNotNone(m["settling_s"])
            self.assertLess(m["settling_s"], 30)
            self.assertLess(abs(m["steady_error_w"]), 0.1 * target)

    def test_feedforward_settles_faster(self):
        # Hardware test 1: without feedforward each step started from the old duty (15 s to settle at 18.6 W).
        with_ff = step_metrics([r for r in self.run_steps([20.0, 12.0]).rows if r["phase"] == "target 12.0"], 12.0)
        without = step_metrics([r for r in self.run_steps([20.0, 12.0], feedforward=False).rows if r["phase"] == "target 12.0"], 12.0)
        self.assertLess(with_ff["first_in_band_s"], without["first_in_band_s"])

    def test_no_windup_when_the_target_is_out_of_reach(self):
        # A target above what the job can draw: the duty sits at 1. When the target drops, the loop must react
        # at once instead of first unwinding a huge integral.
        trace = self.run_steps([80.0, 15.0], seconds=60)
        later = [r for r in trace.rows if r["phase"] == "target 15.0"]
        self.assertTrue(all(r["duty"] == 1.0 for r in trace.rows if r["phase"] == "target 80.0" and r["t"] > 5))
        reached = next(r["t"] - later[0]["t"] for r in later if r["smooth"] <= 15 * 1.1)
        self.assertLess(reached, 20)

    def test_full_speed_without_a_controller(self):
        plant, trace = Plant(), Trace()
        done = run_paced(plant.chunk, 30, plant, None, trace, "open", clock=plant.clock, sleep=plant.sleep)
        self.assertEqual(done, 150)  # 0.2 s chunks, no rests
        self.assertTrue(all(r["duty"] == 1.0 for r in trace.rows))


if __name__ == "__main__":
    unittest.main()
