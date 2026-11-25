"""The terminal front door: menu, mode detection, mode dispatch and files dropped in from outside the workspace."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent import launcher
from agent.launcher import MODES, Session, detect_mode, device_topic, import_files, looks_like_shell, menu

NO = lambda q: False  # noqa: E731


class Recorder:
    """Stands in for an agent, a planner part or the device agent and records what it was asked."""

    def __init__(self, answer="ok", applies=None):
        self.answer, self.asked, self._applies = answer, [], applies
        self.remembered = []

    def run(self, question):
        self.asked.append(question)
        return self.answer

    def applies(self, question):
        return self._applies(question) if self._applies else None

    def diagnose(self, question, topic=None):
        self.asked.append((question, topic))
        return SimpleNamespace(answer=f"{topic}: {self.answer}")

    def remember(self, question, answer):
        self.remembered.append((question, answer))


def session(tmp, **parts):
    agent = Recorder("loop answer")
    planner = SimpleNamespace(device=parts.get("device"), images=parts.get("images"), documents=parts.get("documents"))
    return Session(agent, planner, None, Path(tmp), Path(tmp), {}, "http://localhost:1"), agent


class MenuTests(unittest.TestCase):
    def test_every_mode_listed_with_number(self):
        text = menu()
        for m in MODES:
            self.assertIn(f"{m.number}  {m.title}", text)
        self.assertEqual(len({m.number for m in MODES}), len(MODES))


class ShellTests(unittest.TestCase):
    def test_commands_caught(self):
        for cmd in ("source .venv/bin/activate", "python scripts/run_model_choice.py", "git status", "./scripts/install_shell.sh"):
            self.assertTrue(looks_like_shell(cmd), cmd)

    def test_questions_pass(self):
        for q in ("python으로 피보나치 짜줘", "게임 해도 돼?", "open loop gain이 뭐야?", "What is a git rebase?", "~/Downloads/paper.pdf 요약해줘", "./paper.pdf 요약"):
            self.assertFalse(looks_like_shell(q), q)


class DetectTests(unittest.TestCase):
    def test_topics(self):
        self.assertEqual(detect_mode("배터리 교체해야 해?", NO, NO), "device")
        self.assertEqual(detect_mode("왜 이렇게 뜨거워?", NO, NO), "device")
        self.assertEqual(detect_mode("게임 해도 돼?", NO, NO), "network")
        self.assertEqual(detect_mode("에어팟 자꾸 끊겨", NO, NO), "network")
        self.assertEqual(detect_mode("뉴욕은 지금 몇 시?", NO, NO), "math")

    def test_file_decides_first(self):
        self.assertEqual(detect_mode("a.png 배터리 그래프", lambda q: True, NO), "image")
        self.assertEqual(detect_mode("paper.pdf 요약", NO, lambda q: True), "document")

    def test_device_topic_inside_mode(self):
        self.assertEqual(device_topic("network", "배터리 상태 어때?"), "battery")  # the rules are sure
        self.assertEqual(device_topic("network", "괜찮아?"), "network")           # the mode decides
        self.assertIn(device_topic("device", "괜찮아?"), ("battery", "performance"))


class DispatchTests(unittest.TestCase):
    def test_mode_skips_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = Recorder("fine")
            s, agent = session(tmp, device=device)
            with mock.patch.object(launcher, "warm"):
                s.set_mode("network")
            answer, mode = s.ask("괜찮아?")
            self.assertEqual((answer, mode), ("network: fine", "network"))
            self.assertEqual(agent.remembered, [("괜찮아?", "network: fine")])

    def test_auto_goes_to_loop_for_general(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, agent = session(tmp, device=Recorder())
            answer, mode = s.ask("뉴욕은 지금 몇 시?")
            self.assertEqual((answer, mode), ("loop answer", "math"))

    def test_image_mode_without_file_asks_for_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, _ = session(tmp, images=Recorder("seen"))
            with mock.patch.object(launcher, "warm"):
                s.set_mode("image")
            answer, _ = s.ask("이 사진 설명해줘")
            self.assertIn("경로", answer)

    def test_set_mode_warms_its_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            s, _ = session(tmp)
            s.models = {"planner": "qwen3:14b", "vision": "qwen3-vl:8b-instruct", "light": "qwen3:8b"}
            with mock.patch.object(launcher, "warm") as warm:
                s.set_mode("image")
            warm.assert_called_once_with("http://localhost:1", ["qwen3:14b", "qwen3-vl:8b-instruct"])


class ImportTests(unittest.TestCase):
    def test_outside_file_copied_into_inbox(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
            src = Path(outside) / "My Paper.pdf"
            src.write_bytes(b"%PDF-1.4 test")
            q, copied = import_files(f"{str(src).replace(' ', chr(92) + ' ')} 요약해줘", Path(ws), Path(outside))
            self.assertEqual(copied, ["inbox/My_Paper.pdf"])
            self.assertEqual(q, "inbox/My_Paper.pdf 요약해줘")
            self.assertTrue((Path(ws) / "inbox" / "My_Paper.pdf").exists())

    def test_quoted_and_relative(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "board shot.jpg").write_bytes(b"x")
            q, copied = import_files("'board shot.jpg' MCU는?", Path(ws), Path(outside))
            self.assertEqual(q, "inbox/board_shot.jpg MCU는?")

    def test_file_inside_workspace_not_copied(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / "a.png").write_bytes(b"x")
            q, copied = import_files(f"{ws}/a.png 설명", Path(ws), Path(ws))
            self.assertEqual((q, copied), ("a.png 설명", []))

    def test_missing_file_left_alone(self):
        with tempfile.TemporaryDirectory() as ws:
            q, copied = import_files("nothing.pdf 요약", Path(ws), Path(ws))
            self.assertEqual((q, copied), ("nothing.pdf 요약", []))


if __name__ == "__main__":
    unittest.main()
