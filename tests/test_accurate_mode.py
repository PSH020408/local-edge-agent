"""Offline tests for accurate mode: second looks with a majority vote, tile scan, thinking model.

Run: python -m unittest discover -s tests -v
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from agent import build_default_registry
from agent.image_planner import ImageQuestionPlanner, PlannerOptions
from agent.llm import LLMError
from agent.vision_tools import VisionConfig, parse_brief, same_answer


class Planner:
    def __init__(self, plan, think=False, fail_with_think=False):
        self.plan = json.dumps(plan, ensure_ascii=False)
        self.think = think
        self.fail_with_think = fail_with_think
        self.calls = 0

    def chat(self, messages, tools=None, format=None):
        self.calls += 1
        if self.think and self.fail_with_think:
            raise LLMError("think and format together are not supported")
        return {"message": {"role": "assistant", "content": self.plan}, "stats": {}}


class Vision:
    """Answers by prompt type, so tests do not depend on the exact call order."""

    def __init__(self, describe="", briefs=(), tiles=(), locate='[{"bbox_2d": [100, 100, 400, 400], "label": "U5"}]', fail=False):
        self.describe, self.briefs, self.tiles, self.locate, self.fail = describe, list(briefs), list(tiles), locate, fail
        self.calls = []

    def chat(self, messages, tools=None):
        if self.fail:
            raise LLMError("model 'qwen3-vl:8b' not found")
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "0-1000 scale" in prompt:
            content = self.locate
        elif prompt.startswith("Answer each question about this image in a few words"):
            content = self.briefs.pop(0)
        elif prompt.startswith("This is one zoomed part"):
            content = self.tiles.pop(0)
        else:
            content = self.describe
        return {"message": {"role": "assistant", "content": content}, "stats": {}}


class SameAnswerTests(unittest.TestCase):
    def test_same_answer(self):
        self.assertTrue(same_answer("BPSK", "BPSK"))
        self.assertTrue(same_answer("BPSK", "BPSK, QPSK and 4-QAM overlap"))
        self.assertFalse(same_answer("64-QAM", "32-PSK"))
        self.assertFalse(same_answer("7", "about 12"))
        self.assertTrue(same_answer("CS G05, MOSI G23, SCK G18, MISO G19", "CS: G05, MOSI: G23, SCK: G18, MISO: G19"))
        self.assertFalse(same_answer("yawning, tired", "in pain, holding his knee"))
        self.assertTrue(same_answer("South Korea, at night", "at night in South Korea"))

    def test_parse_brief(self):
        self.assertEqual(parse_brief("1: BPSK\n2: **32-PSK**\n", 2), ["BPSK", "32-PSK"])
        self.assertEqual(parse_brief("1. ESP-WROOM-32", 2), ["ESP-WROOM-32", ""])


class AccurateModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (767, 633), "white").save(self.root / "chart.png")   # fits the pixel budget
        Image.new("RGB", (2324, 1139), "white").save(self.root / "tank.jpg")  # must be downscaled
        self.events, self.tool_calls = [], []

    def tearDown(self):
        self.tmp.cleanup()

    def planner(self, plan, vision, options, reasoning=None, llm=None):
        registry = build_default_registry(self.root, vision, VisionConfig(), reasoning)
        return ImageQuestionPlanner(
            llm or Planner(plan), registry, self.root,
            on_tool_call=lambda n, a, r: self.tool_calls.append((n, a, r)), on_event=self.events.append,
            options=options,
        )

    CHART_PLAN = {"parts": [{"item": "Chart", "kind": "describe", "focus": "", "question": "Which modulation needs the highest Eb/N0?"}]}

    def test_agreeing_looks_confirm_the_answer(self):
        vision = Vision(describe="64-QAM needs the most.", briefs=["1: 32-PSK", "1: 32-PSK"])
        answer = self.planner(self.CHART_PLAN, vision, PlannerOptions(verify=True)).run("chart.png highest?")
        self.assertIn("- ✔ Which modulation needs the highest Eb/N0? → 32-PSK", answer)
        self.assertIn("verify 'Chart': 1 agree, 0 by majority, 0 disagree (2 looks", self.events[-2])

    # Run 23, case 06: "64-QAM" was stated with confidence; a second look can expose it.
    def test_disagreement_gets_a_third_look_and_a_majority(self):
        vision = Vision(describe="64-QAM needs the most.", briefs=["1: 64-QAM", "1: 32-PSK", "1: 32-PSK"])
        answer = self.planner(self.CHART_PLAN, vision, PlannerOptions(verify=True)).run("chart.png highest?")
        self.assertIn("→ 32-PSK (two of three looks agree) ⚠ this may differ from the description above", answer)
        self.assertIn("1 not confirmed", self.events[-1])  # the prose said 64-QAM: not confirmed

    def test_three_different_answers_are_not_confirmed(self):
        vision = Vision(describe="About 7 fish.", briefs=["1: 7", "1: 12", "1: 10"])
        plan = {"parts": [{"item": "Fish", "kind": "describe", "focus": "", "question": "How many fish can you see?"}]}
        answer = self.planner(plan, vision, PlannerOptions(verify=True)).run("chart.png how many fish?")
        self.assertIn("⚠ How many fish can you see? → the answer changed between looks, so it is not confirmed: 7 / 12 / 10", answer)

    def test_open_questions_are_not_compared(self):
        vision = Vision(describe="A conversation about a fight.")
        plan = {"parts": [{"item": "Summary", "kind": "describe", "focus": "", "question": "Summarize this conversation."}]}
        answer = self.planner(plan, vision, PlannerOptions(verify=True)).run("chart.png summarize")
        self.assertEqual(answer, "**Summary**\nA conversation about a fight.")
        self.assertEqual(len(vision.calls), 1)

    def test_zoomed_answer_is_checked_on_a_wider_view(self):
        vision = Vision(describe="CS G05, MOSI G23", briefs=["1: CS G05, MOSI G23", "1: CS G05, MOSI G23"])
        plan = {"parts": [{"item": "SD", "kind": "describe", "focus": "Micro SD Card U5", "question": "Which GPIO pins connect to the SD card?"}]}
        answer = self.planner(plan, vision, PlannerOptions(verify=True)).run("chart.png SD pins?")
        self.assertIn("✔ Which GPIO pins connect to the SD card? → CS G05, MOSI G23", answer)

    def test_fast_mode_makes_no_extra_looks(self):
        vision = Vision(describe="64-QAM.")
        self.planner(self.CHART_PLAN, vision, PlannerOptions()).run("chart.png highest?")
        self.assertEqual(len(vision.calls), 1)

    def test_tile_scan_notes_go_to_whole_image_questions(self):
        vision = Vision(describe="A planted tank.", tiles=["Fluval", "[no text]", "[no text]", "Fluval\nCO2"])
        plan = {"parts": [{"item": "Tank", "kind": "describe", "focus": "", "question": "Describe this aquarium."}]}
        self.planner(plan, vision, PlannerOptions(scan_tiles=True)).run("tank.jpg describe")
        self.assertIn("tile scan: 2 text line(s) from 4 zoomed tiles", " ".join(self.events))
        question = vision.calls[-1]
        self.assertIn("Text read from zoomed parts of this image", question)
        self.assertIn("(top left) Fluval", question)
        self.assertIn("(bottom right) CO2", question)
        self.assertNotIn("(bottom right) Fluval", question)  # duplicates are dropped

    def test_tile_scan_is_skipped_for_images_that_fit(self):
        vision = Vision(describe="A chart.")
        self.planner(self.CHART_PLAN, vision, PlannerOptions(scan_tiles=True)).run("chart.png highest?")
        self.assertIn("tile scan skipped: the whole image already fits the pixel budget", self.events)

    def test_thinking_model_answers_comparisons(self):
        standard, thinking = Vision(describe="standard"), Vision(describe="32-PSK, after comparing the curves.")
        answer = self.planner(self.CHART_PLAN, standard, PlannerOptions(reasoning_vision=True), reasoning=thinking).run("chart.png highest?")
        self.assertIn("32-PSK, after comparing the curves.", answer)
        self.assertIn("answered by the thinking model", self.tool_calls[0][2])

    def test_missing_thinking_model_falls_back(self):
        standard, thinking = Vision(describe="64-QAM."), Vision(fail=True)
        answer = self.planner(self.CHART_PLAN, standard, PlannerOptions(reasoning_vision=True), reasoning=thinking).run("chart.png highest?")
        self.assertIn("64-QAM.", answer)
        self.assertIn("the thinking model failed (model 'qwen3-vl:8b' not found)", self.tool_calls[0][2])

    def test_planning_with_thinking_falls_back_without_it(self):
        llm = Planner(self.CHART_PLAN, think=True, fail_with_think=True)
        answer = self.planner(self.CHART_PLAN, Vision(describe="64-QAM."), PlannerOptions(), llm=llm).run("chart.png highest?")
        self.assertIn("64-QAM.", answer)
        self.assertIn("planning with thinking failed; planning without it", self.events)
        self.assertFalse(llm.think)


class ProfileTests(unittest.TestCase):
    def test_profiles_in_config(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from main import load_config, resolve_profile
        cfg = load_config(Path(__file__).resolve().parent.parent / "config.toml")
        fast, accurate = resolve_profile(cfg, "fast"), resolve_profile(cfg, "accurate")
        self.assertEqual(fast["model"], "qwen3:8b")
        self.assertTrue(accurate["verify"] and accurate["scan_tiles"])
        self.assertEqual(accurate["reasoning_vision_model"], "qwen3-vl:8b")
        for name in ("small", "large", "small-accurate", "large-accurate"):
            self.assertIn(name, cfg["profiles"])
        self.assertEqual(resolve_profile(cfg, "small")["planner_model"], "qwen3:8b")  # 8B plans too: a clean comparison
        self.assertEqual(resolve_profile(cfg, "large-accurate")["planner_model"], "qwen3:14b")
        self.assertEqual(resolve_profile(cfg, "small-accurate")["verify"], resolve_profile(cfg, "large-accurate")["verify"])
        with self.assertRaises(SystemExit):
            resolve_profile(cfg, "nope")


if __name__ == "__main__":
    unittest.main()
