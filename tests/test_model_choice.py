"""Model per question: the difficulty judged from the question, and escalation when the light model fails."""

import sys
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.loop import Agent
from agent.model_choice import ModelChooser, assess, needs_escalation
from agent.tools import ToolRegistry

ROOT = Path(__file__).resolve().parent.parent


class FakeModel:
    """Answers with a fixed text, or never stops calling a tool (to hit the step limit)."""

    def __init__(self, model, answer=None):
        self.model, self.answer, self.calls = model, answer, 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.answer is None:
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "missing_tool", "arguments": {"n": self.calls}}}]}}
        return {"message": {"content": self.answer}}


class AssessTests(unittest.TestCase):
    def test_case_set_levels(self):
        cases = tomllib.loads((ROOT / "evals" / "general" / "cases.toml").read_text(encoding="utf-8"))["case"]
        for c in cases:
            self.assertEqual(assess(c["question"]).level, c["level"], c["id"])

    def test_signals(self):
        self.assertEqual(assess("What time is it in New York?").level, "light")
        self.assertEqual(assess("Derive the Shannon capacity formula and compare it with the Nyquist rate.").level, "heavy")
        self.assertEqual(assess("RC 회로의 원리를 단계별로 유도해줘").level, "heavy")
        self.assertIn("a lookup", assess("What date is 2026-03-03 plus 10 days?").reasons)

    def test_escalation_signal(self):
        self.assertTrue(needs_escalation("[Stopped after 8 steps without a final answer.]"))
        self.assertFalse(needs_escalation("The force is 9,375 N."))


class ChooserTests(unittest.TestCase):
    def make(self, light_answer, loaded=None):
        light, heavy = FakeModel("light-8b", light_answer), FakeModel("heavy-14b", "heavy answer")
        agent = Agent(light, ToolRegistry(), max_steps=3)
        events = []
        return ModelChooser(agent, light, heavy, on_event=events.append, loaded=loaded), light, heavy, agent, events

    def test_light_question_kept_on_loaded_heavy(self):
        chooser, light, heavy, _, events = self.make("20 m/s", loaded=lambda: {"heavy-14b"})
        self.assertEqual(chooser.run("Convert 72 km/h to m/s."), "heavy answer")
        self.assertEqual((light.calls, heavy.calls), (0, 1))
        self.assertTrue(chooser.last.kept_loaded)
        self.assertIn("no reload", events[0])

    def test_both_loaded_or_none_known_uses_judgement(self):
        for loaded in (lambda: {"heavy-14b", "light-8b"}, lambda: set(), lambda: {"light-8b"}):
            chooser, light, heavy, _, _ = self.make("20 m/s", loaded=loaded)
            self.assertEqual(chooser.run("Convert 72 km/h to m/s."), "20 m/s")
            self.assertFalse(chooser.last.kept_loaded)

    def test_light_question_stays_light(self):
        chooser, light, heavy, agent, _ = self.make("20 m/s")
        self.assertEqual(chooser.run("Convert 72 km/h to m/s."), "20 m/s")
        self.assertEqual((light.calls, heavy.calls), (1, 0))
        self.assertIs(agent.llm, light)                 # the agent keeps its light model afterwards

    def test_heavy_question_goes_heavy(self):
        chooser, light, heavy, _, events = self.make("unused")
        chooser.run("A 1,200 kg car brakes from 90 km/h to 0 in 40 m. What is the braking force?")
        self.assertEqual((light.calls, heavy.calls), (0, 1))
        self.assertIn("heavy-14b (heavy: 4 quantities)", events[0])

    def test_escalates_when_the_light_model_does_not_finish(self):
        chooser, light, heavy, agent, events = self.make(None)
        answer = chooser.run("What is 15% of 240?")
        self.assertEqual(answer, "heavy answer")
        self.assertTrue(chooser.last.escalated)
        self.assertEqual(chooser.last.model, "heavy-14b")
        # the failed light attempt is not left in the conversation
        self.assertEqual([m["role"] for m in agent.messages], ["system", "user", "assistant"])


if __name__ == "__main__":
    unittest.main()


class SessionTests(unittest.TestCase):
    def test_auto_on_by_default_off_with_a_fixed_model(self):
        import main
        cfg = main.load_config(ROOT / "config.toml")
        args = SimpleNamespace(model=None, profile=None, accurate=False, fast=False)
        self.assertEqual(main.auto_models(cfg, args, {}), ("qwen3:8b", "qwen3:14b"))
        args.fast = True
        self.assertEqual(main.auto_models(cfg, args, main.resolve_profile(cfg, "fast")), ("qwen3:8b", "qwen3:14b"))
        args.fast, args.model = False, "qwen3:14b"
        self.assertIsNone(main.auto_models(cfg, args, {}))
        args.model, args.accurate = None, True
        self.assertIsNone(main.auto_models(cfg, args, main.resolve_profile(cfg, "accurate")))
