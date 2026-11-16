"""Offline tests for the Stage 7 store, sampler, capture, diagnosis, router, answer writer and agent."""

import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals" / "device"))

from agent.device import answer as writer  # noqa: E402
from agent.device.agent import DeviceAgent  # noqa: E402
from agent.device.capture import capture  # noqa: E402
from agent.device.diagnosis import Finding, Report, battery_report, job_from_question  # noqa: E402
from agent.device.readings import reading  # noqa: E402
from agent.device.router import route  # noqa: E402
from agent.device.sampler import Sampler  # noqa: E402
from agent.device.shell import FixtureShell  # noqa: E402
from agent.device.sources import chip, storage  # noqa: E402
from agent.device.store import Store  # noqa: E402
from scenarios import FIXTURES, SCENARIOS  # noqa: E402

CASES = tomllib.loads((ROOT / "evals" / "device" / "cases.toml").read_text(encoding="utf-8"))["case"]
NO_SLEEP = lambda seconds: None  # noqa: E731


class FakeLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.model = "fake"

    def chat(self, messages, tools=None, format=None):
        self.calls.append(messages)
        return {"message": {"role": "assistant", "content": self.replies.pop(0)}, "stats": {}}


class StoreTests(unittest.TestCase):
    def test_write_latest_window_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "device.db", keep_days=7)
            store.write([reading("battery.charge", 80 - i, "%", f"2026-11-16T10:0{i}:00") for i in range(5)])
            store.write([reading("power.source", "Battery", "text", "2026-11-16T10:04:00")])
            self.assertEqual(store.latest("battery.charge").value, 76)
            self.assertEqual(store.latest("power.source").value, "Battery")
            window = store.window("battery.charge", 10, until="2026-11-16T10:05:00")
            self.assertEqual((window.count, window.maximum, window.minimum), (5, 80, 76))
            self.assertAlmostEqual(window.slope_per_minute, -1.0)  # one percent a minute
            self.assertEqual(store.prune(until="2026-11-24T10:00:00"), 6)  # older than 7 days


class SamplerAndCaptureTests(unittest.TestCase):
    def test_a_round_reads_every_fast_source_and_measures_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "device.db")
            sampler = Sampler(FixtureShell(FIXTURES), store, period=10)
            result = sampler.sample_once()
            names = {r.name for r in result.readings}
            for name in ("battery.voltage", "power.mode_now", "thermal.pressure_level", "cpu.cores", "memory.available",
                         "storage.free", "sampler.cpu_share"):
                self.assertIn(name, names)
            self.assertEqual(store.count(), len(result.readings))
            second = sampler.sample_once()  # storage is read every 10 minutes, not every round
            self.assertNotIn("storage.free", {r.name for r in second.readings})

    def test_capture_has_features_and_chip_samples(self):
        view = capture(FixtureShell(FIXTURES), seconds=3, sleep=NO_SLEEP)
        self.assertEqual(view.samples, 3)
        self.assertEqual(view.chip_samples, 1)
        self.assertEqual(view.mean("chip.gpu_frequency"), 338)
        self.assertEqual(view.features["battery.voltage"].count, 3)

    def test_several_powermetrics_samples_in_one_output(self):
        text = (FIXTURES / "powermetrics.txt").read_text(encoding="utf-8")
        samples = chip.parse(text + "\n" + text.replace("GPU HW active frequency: 338 MHz", "GPU HW active frequency: 618 MHz"))
        self.assertEqual([next(r.value for r in s if r.name == "chip.gpu_frequency") for s in samples], [338, 618])

    def test_free_space_comes_from_the_container_not_df(self):
        values = {r.name: r.value for r in storage.read(FixtureShell(FIXTURES))}
        self.assertEqual(values["storage.free"], 558634065920)  # df reports the sealed system volume instead
        self.assertEqual(values["storage.health"], "Verified")


class DiagnosisTests(unittest.TestCase):
    def test_every_scenario_case_gets_its_expected_findings(self):
        for case in CASES:
            if case.get("scenario") in (None, "live") or case.get("route", "none") == "none":
                continue
            with self.subTest(case=case["id"]):
                agent = DeviceAgent(FixtureShell(FIXTURES, overrides=SCENARIOS[case["scenario"]]), sleep=NO_SLEEP, capture_seconds=2)
                codes = agent.diagnose(case["question"], topic=case["route"]).report.codes()
                for code in case.get("expect", []):
                    self.assertIn(code, codes)
                for code in case.get("forbid", []):
                    self.assertNotIn(code, codes)

    def test_the_replacement_limit_is_80_percent_as_macos_shows_it(self):
        view = capture(FixtureShell(FIXTURES), seconds=1, with_chip=False, sleep=NO_SLEEP)
        self.assertIn("battery_replace", battery_report(view, {"battery.macos_maximum_capacity": 79.9}).codes())
        self.assertIn("battery_aging", battery_report(view, {"battery.macos_maximum_capacity": 80.0}).codes())
        self.assertIn("battery_ok", battery_report(view, {"battery.macos_maximum_capacity": 85.0}).codes())

    def test_jobs_are_recognised_only_in_can_i_run_questions(self):
        self.assertEqual(job_from_question("지금 긴 평가 돌려도 돼?"), "long_run")
        self.assertEqual(job_from_question("지금 이미지 분석 돌려도 돼?"), "vision")
        self.assertEqual(job_from_question("Can I run a document question now?"), "document")
        self.assertIsNone(job_from_question("맥이 왜 느려?"))


class RouterTests(unittest.TestCase):
    def test_rule_cases_route_without_a_model(self):
        for case in CASES:
            if case["id"] in ("B15", "R02"):  # no keyword: the small model decides
                continue
            with self.subTest(case=case["id"]):
                self.assertEqual(route(case["question"]).topic or "none", case.get("route", "none"))

    def test_general_questions_with_a_keyword_are_not_device_questions(self):
        # Run D1: qwen3:1.7b sent R04 to the battery agent; the rules decide this now, without the model.
        llm = FakeLLM(json.dumps({"topic": "battery"}))
        result = route("리튬이온 배터리의 화학 원리를 설명해줘", llm)
        self.assertEqual((result.topic, result.method), (None, "rules-general"))
        self.assertEqual(llm.calls, [])
        self.assertEqual(route("내 맥 배터리 원리상 괜찮아?").topic, "battery")  # points at this machine

    def test_high_power_mode_is_not_a_performance_word(self):
        # Run D1, B12: "성능" inside "고성능" made a tie, and the model chose performance.
        result = route("고성능 모드 켜야 돼?")
        self.assertEqual((result.topic, result.method), ("battery", "rules"))

    def test_english_words_next_to_korean_particles(self):
        self.assertEqual(route("CPU를 계속 잡아먹는 프로그램 있어?").topic, "performance")
        self.assertIsNone(route("이 프로그램 뭐야").topic)  # "program" does not contain the word "ram"


class RunD2FixTests(unittest.TestCase):
    def test_the_macos_estimate_while_charging_is_the_time_to_full(self):
        from agent.device.sources import power
        values = {r.name: r.value for r in power.parse_batt(
            "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t60%; charging; 0:58 remaining present: true\n")}
        self.assertEqual((values["power.macos_time_to_full"], values["power.macos_time_remaining"]), (58, None))

    def test_an_adapter_that_supplies_nothing(self):
        agent = DeviceAgent(FixtureShell(FIXTURES, overrides=SCENARIOS["adapter_not_supplying"]), sleep=NO_SLEEP, battery_seconds=1)
        report = agent.diagnose("충전기 꽂혀 있는데 배터리 얼마나 버텨?").report
        self.assertIn("adapter_not_supplying", report.codes())
        self.assertNotIn("charger_weak", report.codes())
        self.assertEqual(report.facts["time left at the present power (own estimate)"], "44 min (0 h 44 min)")

    def test_the_answer_language_is_stated_by_code(self):
        llm = FakeLLM("Battery health is good: 286 cycles.")
        writer.write(AnswerTests.REPORT, "How is my battery?", llm)
        self.assertTrue(llm.calls[0][1]["content"].endswith("Answer in English."))


class AnswerTests(unittest.TestCase):
    REPORT = Report("battery", {"charge": "90%", "charge cycles": "286 of 1,000 rated"},
                    [Finding("battery_ok", "info", "Battery health is good", {"charge cycles": "286 of 1,000 rated"}, "No action needed.")])

    def test_numbers_not_in_the_facts_are_found(self):
        self.assertEqual(writer.unsupported("충전 횟수는 286회, 충전량 90%입니다.", self.REPORT, "배터리 어때?"), [])
        self.assertEqual(writer.unsupported("충전 횟수는 268회입니다.", self.REPORT, "배터리 어때?"), ["268"])

    def test_reasoning_written_as_the_answer_is_rejected(self):
        # Run D1: the thinking model wrote "Okay, let me tackle this..." as its answer.
        result = writer.write(self.REPORT, "배터리 어때?", FakeLLM("Okay, let me tackle this. The user asks...", "배터리 상태는 양호하고 충전 횟수는 286회입니다."))
        self.assertEqual(result.method, "model-retry")
        self.assertIn("reasoning", result.reason)
        self.assertEqual(writer.clean("<think>계산 중</think>답: 286회"), "답: 286회")

    def test_a_wrong_number_is_rewritten_once_then_the_template_is_used(self):
        fixed = writer.write(self.REPORT, "배터리 어때?", FakeLLM("충전 횟수 268회.", "충전 횟수 286회, 상태 양호."))
        self.assertEqual((fixed.method, fixed.unsupported), ("model-retry", ["268"]))
        failed = writer.write(self.REPORT, "배터리 어때?", FakeLLM("268회.", "268회라니까요."))
        self.assertEqual(failed.method, "template")
        self.assertIn("286", failed.text)


class AgentTests(unittest.TestCase):
    def test_the_main_router_sends_device_questions_to_the_device_agent(self):
        from main import QuestionRouter

        writer_llm = FakeLLM("배터리 상태는 양호합니다. 최대 용량 90%, 충전 횟수 286회입니다.")
        device = DeviceAgent(FixtureShell(FIXTURES), writer_llm=writer_llm, sleep=NO_SLEEP, battery_seconds=1)
        router = QuestionRouter(None, None, device)
        self.assertIn("286", router.run("배터리 상태 어때?"))
        self.assertIsNone(router.run("오늘 서울 날씨 어때?"))
        self.assertIn("Facts:", writer_llm.calls[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
