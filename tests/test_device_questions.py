"""Every example question in docs/device_questions.md reaches the agent its table names, decided by the rules.

The guide is the user's reference for what can be asked; this test keeps it true when the routing rules change.
"""

import re
import unittest
from pathlib import Path

from agent.device.router import route

GUIDE = Path(__file__).resolve().parent.parent / "docs" / "device_questions.md"
MARK = re.compile(r"<!-- agent: (battery|performance|network|none) -->")
QUESTION = re.compile(r"^- `([^`]+)`", re.M)


def examples() -> list[tuple[str, str]]:
    """(question, agent) for every example: each "<!-- agent: x -->" mark applies to the questions after it."""
    text = GUIDE.read_text(encoding="utf-8")
    marks = list(MARK.finditer(text))
    out = []
    for k, mark in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out += [(q, mark.group(1)) for q in QUESTION.findall(text[mark.end():end])]
    return out


class GuideTests(unittest.TestCase):
    def test_every_example_routes_as_the_guide_says(self):
        rows = examples()
        self.assertGreater(len(rows), 45)
        wrong = []
        for question, agent in rows:
            result = route(question)  # no model: the rules alone must decide
            got = result.topic or "none"
            if got != agent or result.method not in ("rules", "rules-general", "rules-work", "rules-network"):
                wrong.append(f"{question!r}: {got} by {result.method}, guide says {agent}")
        self.assertEqual(wrong, [])


class GuideFindingTests(unittest.TestCase):
    """A few guide examples against the recorded outputs: the answer is built on the finding the guide describes."""

    def test_key_examples(self):
        from agent.device.agent import DeviceAgent
        from agent.device.shell import FixtureShell
        fixtures = Path(__file__).parent / "fixtures" / "device"
        agent = DeviceAgent(FixtureShell(fixtures), sleep=lambda s: None, capture_seconds=1, battery_seconds=1)
        expected = {
            "What is connected to my USB ports?": "buses",
            "What is my CPU temperature?": "not_measured",
            "Is my screen brightness right?": "not_measured",
            "Why did my Mac stop charging at 90%?": "charging_paused",
            "Should I turn on High Power Mode?": "mode_not_needed",
            "How long will my battery last?": "on_adapter_time",
            "Which app is using the most memory?": "memory_by_app",
            "What can I do on this Mac right now?": "work_overview",
            "Can I edit 4K video now?": "work_yes",
            "Can I train a deep-learning model now?": "work_yes",
            "Can I run an image analysis now?": "admit_run",
        }
        for question, code in expected.items():
            self.assertIn(code, agent.diagnose(question).report.codes(), question)
        ports = agent.diagnose("What is connected to my USB ports?").report.facts
        self.assertIn("Up to 120 Gb/s", ports["USB-C ports (Thunderbolt / USB4)"])
