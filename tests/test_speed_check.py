"""Speed check before long runs (agent/device/speed_check.py)."""

import unittest

from agent.device import speed_check as sc


def ollama(tokens_per_s, count=100, load=0.0):
    return lambda model: {"eval_count": count, "eval_duration": int(count / tokens_per_s * 1e9), "load_duration": int(load * 1e9)}


class SpeedCheckTests(unittest.TestCase):
    def test_normal_speed(self):
        result = sc.check(ollama(25.0), "qwen3:14b", 0, diagnose=lambda: self.fail("no diagnosis needed"))
        self.assertEqual(result.verdict, "normal")
        self.assertAlmostEqual(result.ratio, 25.0 / 25.3, places=3)

    def test_low_power_has_its_own_normal(self):
        # Energy runs E1-E3: 14.1-14.2 tokens/s in Low Power is normal for that mode, not a fault.
        self.assertEqual(sc.check(ollama(14.0), "qwen3:14b", 1).verdict, "normal")
        self.assertEqual(sc.check(ollama(14.0), "qwen3:14b", 0, diagnose=lambda: []).verdict, "much slower")

    def test_much_slower_runs_the_diagnosis(self):
        # The state of Run 45: the GPU held at its lowest clocks.
        held = ["The GPU is busy but held at its lowest clocks by thermal management (fan speed is not measured)"]
        result = sc.check(ollama(9.0), "qwen3:14b", 2, diagnose=lambda: held)
        self.assertEqual(result.verdict, "much slower")
        self.assertIn("lowest clocks", result.message)
        self.assertIn("2.8 times as long", result.message)

    def test_slow_but_not_much(self):
        self.assertEqual(sc.check(ollama(18.0), "qwen3:14b", 0, diagnose=lambda: []).verdict, "slow")

    def test_unknown_model_and_failure(self):
        self.assertEqual(sc.check(ollama(40.0), "qwen3:8b", 0).verdict, "no normal known")

        def broken(model):
            raise ConnectionError("Ollama is not running")
        self.assertEqual(sc.check(broken, "qwen3:14b", 0).verdict, "failed")


if __name__ == "__main__":
    unittest.main()
