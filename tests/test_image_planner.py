"""Offline tests for the image question planner (fake main model, fake vision model).

Run: python -m unittest discover -s tests -v
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from agent import build_default_registry
from agent.image_planner import ImageQuestionPlanner, PLAN_SCHEMA, find_image_path, parse_plan
from agent.vision_tools import VisionConfig


class PlannerLLM:
    """Fake main model: returns fixed plans (the last one repeats) and records the format it was asked for."""

    def __init__(self, *plans):
        self.plans = [p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in plans]
        self.calls = []

    def chat(self, messages, tools=None, format=None):
        self.calls.append({"messages": list(messages), "format": format})
        plan = self.plans.pop(0) if len(self.plans) > 1 else self.plans[0]
        return {"message": {"role": "assistant", "content": plan}, "stats": {}}


class ScriptedVision:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return {"message": {"role": "assistant", "content": self.answers.pop(0)}, "stats": {}}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "img").mkdir()
        Image.new("RGB", (1920, 1444), "white").save(self.root / "img" / "board.jpg")
        Image.new("RGB", (960, 1280), "gray").save(self.root / "img" / "street.jpg")
        self.events = []
        self.raw_events = []
        self.tool_calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, message):
        # Timings change from run to run; tests compare the rest of the line.
        self.raw_events.append(message)
        self.events.append(re.sub(r" \(\d+\.\d s\)$| \| total \d+\.\d s$", "", message))

    def planner(self, plan, vision_answers, replan=None):
        vision = ScriptedVision(vision_answers)
        registry = build_default_registry(self.root, vision, VisionConfig())
        llm = PlannerLLM(plan, replan) if replan is not None else PlannerLLM(plan)
        planner = ImageQuestionPlanner(
            llm, registry, self.root,
            on_tool_call=lambda name, args, result: self.tool_calls.append((name, args)),
            on_event=self.record,
        )
        return planner, llm, vision

    # Run 17, case 01: the model looked up MCU and SD card only, and asked about all parts in each call.
    def test_every_part_gets_its_own_call_and_question(self):
        plan = {"parts": [
            {"item": "MCU 모듈", "kind": "describe", "focus": "ESP-WROOM-32", "question": "이 모듈의 이름은?"},
            {"item": "SD 카드 핀", "kind": "describe", "focus": "Micro SD Card U5", "question": "CS, MOSI, SCK, MISO에 연결된 GPIO는?"},
            {"item": "OLED 핀", "kind": "describe", "focus": "SSD1306 OLED U3", "question": "SDA, SCL에 연결된 GPIO는?"},
            {"item": "레귤레이터", "kind": "read_text", "focus": "the part number of the regulator U1", "question": "레귤레이터 부품명은?"},
        ]}
        vision = [
            '[{"bbox_2d": [290, 400, 520, 650], "label": "ESP-WROOM-32"}]', "ESP-WROOM-32",
            '[{"bbox_2d": [680, 740, 790, 850], "label": "Micro SD Card"}]', "CS G05, MOSI G23, SCK G18, MISO G19",
            '[{"bbox_2d": [680, 530, 780, 630], "label": "SSD1306"}]', "SDA G21, SCL G22",
            '[{"bbox_2d": [78, 72, 156, 177], "label": "U1"}]', "AMS1117-3V3", "AMS1117-3V3",
        ]
        planner, llm, fake_vision = self.planner(plan, vision)
        answer = planner.run("img/board.jpg 이 보드의 MCU, SD 카드와 OLED 핀, 레귤레이터 부품명을 알려 줘")

        self.assertEqual(llm.calls[0]["format"], PLAN_SCHEMA)  # structured output is requested
        self.assertNotIn("img/board.jpg", llm.calls[0]["messages"][-1]["content"])
        self.assertEqual(len(self.tool_calls), 4)
        self.assertEqual([a.get("focus") or a.get("target") for _, a in self.tool_calls],
                         ["ESP-WROOM-32", "Micro SD Card U5", "SSD1306 OLED U3", "the part number of the regulator U1"])
        # Each vision question is only about its own part.
        asked = [m[-1]["content"] for m in fake_vision.calls if "images" in m[-1] and "Find this" not in m[-1]["content"]]
        self.assertIn("SDA, SCL에 연결된 GPIO는?", asked)
        self.assertNotIn("레귤레이터", " ".join(asked[:3]))
        for expected in ("**MCU 모듈**\nESP-WROOM-32", "MISO G19", "SDA G21, SCL G22", "**레귤레이터**\nAMS1117-3V3"):
            self.assertIn(expected, answer)
        self.assertIn("plan: 4 part(s) - MCU 모듈 / SD 카드 핀 / OLED 핀 / 레귤레이터", self.events)
        self.assertIn("check: 4/4 parts answered", self.events)

    # Run 17, case 10: the answer stated "031-715-1544" although the readings differed.
    def test_uncertain_reading_is_always_shown_with_both_versions(self):
        plan = {"parts": [
            {"item": "장면", "kind": "describe", "focus": "", "question": "이 사진을 설명해 줘."},
            {"item": "전화번호", "kind": "read_text", "focus": "the phone number on the right sign", "question": "전화번호는?"},
        ]}
        vision = ["밤거리입니다.", '[{"bbox_2d": [873, 454, 932, 470]}]', "030715-1544", "(031)715-1544"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/street.jpg 사진 설명하고 간판 번호 읽어 줘")
        self.assertIn("⚠ 확실하지 않음", answer)
        self.assertIn("읽기 1: 030715-1544", answer)
        self.assertIn("읽기 2: (031)715-1544", answer)
        self.assertIn("check: 2/2 parts answered, 1 not confirmed (shown with both readings or marked)", self.events)

    def test_unlocated_focus_falls_back_to_the_whole_image(self):
        plan = {"parts": [{"item": "MCU", "kind": "describe", "focus": "MCU 모듈", "question": "MCU는?"}]}
        planner, _, _ = self.planner(plan, ["[]", "ESP-WROOM-32"])
        answer = planner.run("img/board.jpg MCU는?")
        self.assertIn("ESP-WROOM-32", answer)
        self.assertTrue(any("retrying on the whole image" in e for e in self.events))
        self.assertEqual(len(self.tool_calls), 2)

    def test_missing_label_stays_not_found(self):
        # R50 does not exist on the board: no fallback that could invite a guessed value.
        plan = {"parts": [{"item": "R50 값", "kind": "read_text", "focus": "resistor R50 value", "question": "R50 값은?"}]}
        planner, _, vision = self.planner(plan, ["[]"])
        answer = planner.run("img/board.jpg 저항 R50의 값은?")
        self.assertIn("이미지에서 찾을 수 없습니다", answer)
        self.assertEqual(len(vision.calls), 1)

    def test_invalid_plan_falls_back_to_one_whole_image_question(self):
        planner, _, _ = self.planner("not json", ["A board."])
        answer = planner.run("img/board.jpg What is this?")
        self.assertEqual(answer, "A board.")
        self.assertTrue(any("plan could not be read" in e for e in self.events))

    def test_english_question_gets_english_labels(self):
        plan = {"parts": [{"item": "Phone", "kind": "read_text", "focus": "the phone number", "question": "Phone?"}]}
        planner, _, _ = self.planner(plan, ['[{"bbox_2d": [1, 1, 50, 50]}]', "123", "128"])
        self.assertIn("Uncertain: the two readings differ", planner.run("img/street.jpg read the phone number"))

    # Run 18, case 01: a zoomed view of "the GPIO pins connected to SD card" said the pins were not shown.
    def test_not_shown_in_zoom_is_retried_with_a_wider_view(self):
        plan = {"parts": [{"item": "SD 카드 핀", "kind": "describe", "focus": "the GPIO pins connected to SD card",
                           "question": "SD 카드에 연결된 GPIO 핀은?"}]}
        vision = ['[{"bbox_2d": [687, 703, 782, 757]}]', "이 이미지는 SD 카드에 연결된 GPIO 핀을 보여주지 않습니다.",
                  "CS G05, MOSI G23, SCK G18, MISO G19"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg SD 카드 핀 알려 줘")
        self.assertIn("CS G05", answer)
        self.assertTrue(any("retrying with a wider view" in e for e in self.events))
        region = self.tool_calls[-1][1]["region"]
        left, top, right, bottom = (float(v) for v in region.split(","))
        self.assertGreaterEqual(right - left, 0.399)
        self.assertGreaterEqual(bottom - top, 0.399)
        # Run 19: an answer that appears only after a miss is shown as not verified.
        self.assertIn("⚠ 확인되지 않음", answer)
        self.assertIn("check: 1/1 parts answered, 1 not confirmed (shown with both readings or marked)", self.events)

    def test_still_not_shown_is_not_counted_as_answered(self):
        plan = {"parts": [
            {"item": "MCU", "kind": "describe", "focus": "ESP-WROOM-32", "question": "MCU는?"},
            {"item": "OLED 핀", "kind": "describe", "focus": "OLED", "question": "OLED 핀은?"},
        ]}
        vision = ['[{"bbox_2d": [290, 400, 520, 650]}]', "ESP-WROOM-32",
                  '[{"bbox_2d": [663, 531, 700, 547]}]', "이미지에는 OLED 핀에 대한 정보가 없습니다.",
                  "OLED가 보이지 않습니다."]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg MCU와 OLED 핀은?")
        self.assertIn("check: 1/2 parts answered, 1 not found in the image", self.events)
        self.assertIn("확대한 화면과 더 넓은 화면 모두에서 찾지 못했습니다", answer)

    def test_not_shown_later_in_an_answer_is_a_normal_answer(self):
        plan = {"parts": [{"item": "시간", "kind": "describe", "focus": "", "question": "언제 찍었어?"}]}
        planner, _, _ = self.planner(plan, ["밤에 찍었습니다. 정확한 날짜는 사진에 표시되지 않았습니다."])
        planner.run("img/street.jpg 언제 찍었어?")
        self.assertIn("check: 1/1 parts answered", self.events)

    # Run 18, case 01: "전압 레귤레이터 부품명" went to describe and came back as "AMS1117-".
    def test_exact_name_request_uses_two_readings(self):
        plan = {"parts": [
            {"item": "전압 레귤레이터", "kind": "describe", "focus": "the voltage regulator", "question": "전압 레귤레이터 부품명은?"},
            {"item": "SD 카드 연결", "kind": "describe", "focus": "Micro SD Card", "question": "SD 카드 핀 부품명과 연결은?"},
        ]}
        vision = ['[{"bbox_2d": [79, 64, 155, 153]}]', "AMS1117-3V3", "AMS1117-3V3",
                  '[{"bbox_2d": [680, 740, 790, 850]}]', "CS G05"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg 레귤레이터 부품명과 SD 카드 연결은?")
        self.assertEqual([name for name, _ in self.tool_calls], ["read_text_in_image", "describe_image"])
        self.assertIn("**전압 레귤레이터**\nAMS1117-3V3", answer)

    # Run 18, case 10: the scene description quoted "푸르지오 건담"; the confirmed reading was "푸르지오강남".
    def test_quoted_text_in_a_description_points_to_the_checked_reading(self):
        plan = {"parts": [
            {"item": "장면", "kind": "describe", "focus": "", "question": "사진을 설명해 줘."},
            {"item": "간판", "kind": "read_text", "focus": "the sign on the right", "question": "간판은?"},
        ]}
        vision = ['밤거리입니다. 간판에 "푸르지오 건담"이라고 쓰여 있습니다.',
                  '[{"bbox_2d": [875, 442, 935, 466]}]', "푸르지오강남", "푸르지오강남"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/street.jpg 사진 설명하고 간판 읽어 줘")
        self.assertIn("정확한 글자는 두 번 읽어 비교한 '간판' 항목을 따르세요", answer)

    # Run 19, 8B: four parts asked about the same SD card module one pin at a time.
    def test_parts_with_the_same_focus_are_asked_together(self):
        plan = {"parts": [{"item": "MCU", "kind": "describe", "focus": "the microcontroller module", "question": "MCU는?"}] + [
            {"item": f"SD 카드 {pin} 핀", "kind": "describe", "focus": "SD card socket", "question": f"SD 카드의 {pin} 핀은 어디에 연결돼 있어?"}
            for pin in ("CS", "MOSI", "SCK", "MISO")
        ]}
        vision = ['[{"bbox_2d": [290, 400, 520, 650]}]', "ESP-WROOM-32",
                  '[{"bbox_2d": [677, 722, 787, 831]}]', "CS G05, MOSI G23, SCK G18, MISO G19"]
        planner, _, fake_vision = self.planner(plan, vision)
        answer = planner.run("img/board.jpg MCU와 SD 카드 CS, MOSI, SCK, MISO 핀은?")
        self.assertEqual(len(self.tool_calls), 2)
        self.assertIn("SD 카드 CS 핀 + SD 카드 MOSI 핀 + SD 카드 SCK 핀 + SD 카드 MISO 핀", answer)
        question = fake_vision.calls[-1][-1]["content"]
        for pin in ("CS", "MOSI", "SCK", "MISO"):
            self.assertIn(f"{pin} 핀", question)
        self.assertEqual(sum("asked together" in e for e in self.events), 3)

    # Run 19, 8B: OLED (SDA, SCL) was asked for but never planned.
    def test_label_missing_from_the_plan_triggers_a_new_plan(self):
        first = {"parts": [{"item": "MCU", "kind": "describe", "focus": "ESP-WROOM-32", "question": "MCU는?"}]}
        second = {"parts": [
            {"item": "MCU", "kind": "describe", "focus": "ESP-WROOM-32", "question": "MCU는?"},
            {"item": "OLED 핀", "kind": "describe", "focus": "OLED display module", "question": "OLED의 SDA, SCL 핀은?"},
        ]}
        vision = ['[{"bbox_2d": [290, 400, 520, 650]}]', "ESP-WROOM-32",
                  '[{"bbox_2d": [680, 530, 780, 630]}]', "SDA G21, SCL G22"]
        planner, llm, _ = self.planner(first, vision, replan=second)
        answer = planner.run("img/board.jpg MCU랑 OLED(SDA, SCL) 핀 알려 줘")
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("OLED, SDA, SCL", llm.calls[1]["messages"][-1]["content"])
        self.assertIn("plan does not cover: OLED, SDA, SCL; asking for a new plan", self.events)
        self.assertIn("SDA G21, SCL G22", answer)
        self.assertNotIn("계획에 들어가지 않아", answer)

    def test_part_still_missing_is_reported(self):
        plan = {"parts": [{"item": "MCU", "kind": "describe", "focus": "ESP-WROOM-32", "question": "MCU는?"}]}
        vision = ['[{"bbox_2d": [290, 400, 520, 650]}]', "ESP-WROOM-32"]
        planner, llm, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg MCU랑 OLED 알려 줘")
        self.assertEqual(len(llm.calls), 2)  # one new plan, then it stops asking
        self.assertIn("check: 1/1 parts answered, not planned: OLED", self.events)
        self.assertIn("계획에 들어가지 않아 확인하지 못했습니다: OLED", answer)

    def test_covered_plan_is_not_asked_again(self):
        plan = {"parts": [{"item": "장면", "kind": "describe", "focus": "", "question": "이 사진은 어떤 장면을 보여줘?"}]}
        planner, llm, _ = self.planner(plan, ["밤거리입니다."])
        planner.run("img/street.jpg 이 사진을 설명해 줘")
        self.assertEqual(len(llm.calls), 1)

    # Run 19, 14B: "031-715-1544" and "(031)715-1544" were marked UNCERTAIN.
    def test_punctuation_only_difference_is_not_uncertain(self):
        plan = {"parts": [{"item": "간판", "kind": "read_text", "focus": "the sign on the right", "question": "간판은?"}]}
        vision = ['[{"bbox_2d": [874, 442, 933, 465]}]', "푸르지오강남\n031-715-1544", "푸르지오강남\n(031)715-1544"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/street.jpg 간판 읽어 줘")
        self.assertNotIn("확실하지 않음", answer)
        self.assertIn("(031)715-1544", answer)
        self.assertIn("다른 표기: 푸르지오강남 031-715-1544", answer)
        self.assertIn("check: 1/1 parts answered", self.events)

    # Run 20: "AMS1117" (tight crop) vs "AMS1117-3V3" (wider crop) was shown as two different readings.
    def test_cut_off_reading_shows_the_longer_one_as_partly_confirmed(self):
        plan = {"parts": [{"item": "레귤레이터", "kind": "read_text", "focus": "the regulator part number", "question": "부품명은?"}]}
        vision = ['[{"bbox_2d": [85, 68, 152, 123], "label": "AMS1117-3V3"}]', "AMS1117", "AMS1117-3V3"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg 레귤레이터 부품명은?")
        self.assertIn("**레귤레이터**\nAMS1117-3V3\n(⚠ 일부만 확인됨: 좁은 화면 읽기는 'AMS1117'까지만", answer)
        self.assertNotIn("확실하지 않음", answer)
        self.assertIn("check: 1/1 parts answered, 1 not confirmed (shown with both readings or marked)", self.events)

    def test_printed_label_matching_the_focus_is_trusted(self):
        plan = {"parts": [{"item": "MCU", "kind": "describe", "focus": "ESP-WROOM-32", "question": "MCU는?"}]}
        vision = ['[{"bbox_2d": [290, 400, 520, 650], "label": "ESP-WROOM-32"}]', "ESP-WROOM-32"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg MCU는?")
        self.assertEqual(answer, "**MCU**\nESP-WROOM-32")

    # Run 21, case 04: "왜 웃긴지 설명해 줘" was taken as a request to describe the whole image.
    def test_explain_why_is_not_a_missing_description(self):
        plan = {"parts": [{"item": "댓글", "kind": "describe", "focus": "", "question": "댓글들을 읽어 주고 흐름과 웃긴 이유를 설명해 줘."}]}
        planner, llm, _ = self.planner(plan, ["네 개의 댓글이 있습니다."])
        answer = planner.run("img/street.jpg 이 댓글들을 읽어 주고, 대화의 흐름과 왜 웃긴지 설명해 줘.")
        self.assertEqual(len(llm.calls), 1)
        self.assertNotIn("계획에 들어가지 않아", answer)

    # Run 21: "how many fish" looked at one fish; "the flow" and "why funny" at the first comment.
    def test_whole_image_questions_are_not_zoomed_and_are_asked_together(self):
        plan = {"parts": [
            {"item": "전체 내용", "kind": "describe", "focus": "", "question": "이 이미지는 어떤 내용이야?"},
            {"item": "대화 흐름", "kind": "describe", "focus": "the conversation flow in the comments", "question": "대화 흐름은?"},
            {"item": "웃긴 이유", "kind": "describe", "focus": "the humor in the comments", "question": "왜 웃겨?"},
        ]}
        planner, _, fake_vision = self.planner(plan, ["네 개의 댓글이 이어지고, 엄마 대결로 끝나서 웃깁니다."])
        answer = planner.run("img/street.jpg 대화 흐름과 왜 웃긴지 알려 줘")
        self.assertEqual(len(fake_vision.calls), 1)  # one look at the whole image, no locate step
        self.assertEqual(self.tool_calls[0][1]["focus"], "")
        self.assertIn("이 이미지는 어떤 내용이야? 대화 흐름은? 왜 웃겨?", fake_vision.calls[0][-1]["content"])
        self.assertIn("**전체 내용 + 대화 흐름 + 웃긴 이유**", answer)
        self.assertTrue(any("is about the whole image" in e for e in self.events))

    def test_counting_and_comparing_use_the_whole_image(self):
        from agent.image_planner import _WHOLE_IMAGE_QUESTION as q
        for text in ("How many fish can you see?", "Which modulation needs the lowest Eb/N0?", "물고기는 몇 마리야?",
                     "How does the character feel?", "What is the style of the drawing?", "가장 큰 건물은?"):
            self.assertTrue(q.search(text), text)
        for text in ("Which GPIO pins connect to the SD card?", "What voltage regulator is used?", "전압 레귤레이터 부품명은?"):
            self.assertFalse(q.search(text), text)

    # Runs 18-21: a small box labelled with the request itself was the wrong place every time.
    def test_small_echo_located_focus_is_asked_on_the_whole_image(self):
        plan = {"parts": [{"item": "OLED 핀", "kind": "describe", "focus": "OLED interface (SDA, SCL)", "question": "OLED SDA, SCL은?"}]}
        vision = ['[{"bbox_2d": [653, 374, 700, 400], "label": "OLED interface"}]', "SDA G21, SCL G22"]
        planner, _, fake_vision = self.planner(plan, vision)
        answer = planner.run("img/board.jpg OLED(SDA, SCL) 핀은?")
        self.assertEqual(self.tool_calls[0][1]["focus"], "OLED interface")  # the bracket list is dropped
        self.assertEqual(self.tool_calls[1][1], {"path": "img/board.jpg", "question": "OLED SDA, SCL은?"})
        self.assertTrue(any("matched no printed label" in e for e in self.events))
        self.assertIn("전체 이미지에서 확인한 내용입니다", answer)  # marked: no zoomed check
        self.assertIn("1 not confirmed", self.events[-1])

    def test_large_echo_located_focus_is_trusted(self):
        # Run 21, cases 07-09: "the first formula", "the character" were placed correctly on large areas.
        plan = {"parts": [{"item": "Pose", "kind": "describe", "focus": "the character in the drawing", "question": "What is the pose?"}]}
        vision = ['[{"bbox_2d": [583, 0, 1000, 852], "label": "the character in the drawing"}]', "One hand raised."]
        planner, _, _ = self.planner(plan, vision)
        self.assertEqual(planner.run("img/board.jpg What is the pose?"), "**Pose**\nOne hand raised.")

    # Run 21, case 02: the reading of a key signature repeated the request as if it were the text.
    def test_reading_that_repeats_the_request_is_no_text(self):
        plan = {"parts": [{"item": "Key signature", "kind": "read_text", "focus": "the key signature at the beginning of the staff", "question": "Key?"}]}
        vision = ['[{"bbox_2d": [65, 260, 100, 278]}]', "?", "the key signature at the beginning of the staff."]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg What is the key signature?")
        self.assertNotIn("the key signature at the beginning", answer.split("**Key signature**")[1])
        self.assertIn("Reading 2: (No readable text.)", answer)

    # Run 21, H4: "Not shown." after a failed locate was marked as an unverified finding.
    def test_not_shown_after_fallback_is_a_plain_answer(self):
        plan = {"parts": [{"item": "Filter brand", "kind": "read_text", "focus": "the brand name on the filter", "question": "What brand is the filter?"}]}
        planner, _, _ = self.planner(plan, ["[]", "Not shown."])
        answer = planner.run("img/street.jpg What brand is the filter?")
        self.assertEqual(answer, "**Filter brand**\nNot shown.\n(The vision model said it is not in the image.)")
        self.assertIn("check: 0/1 parts answered, 1 not found in the image", self.events)

    # Run 22, case 02: the wider crop added the next line ("Guitar/Ukulele") to the title.
    def test_extra_lines_in_the_wider_reading_are_nearby_text(self):
        plan = {"parts": [{"item": "Title", "kind": "read_text", "focus": "the title at the top", "question": "Title?"}]}
        vision = ['[{"bbox_2d": [370, 48, 623, 73]}]', "WONDERWALL", "WONDERWALL\nGuitar/Ukulele"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg What is the title?")
        self.assertEqual(answer, "**Title**\nWONDERWALL\n(The wider view also showed nearby text: Guitar/Ukulele)")
        self.assertIn("check: 1/1 parts answered", self.events)

    # Run 22, case 02: "the artist name" and "the instrument name" both read "Guitar/Ukulele".
    def test_same_text_in_two_parts_is_flagged(self):
        plan = {"parts": [
            {"item": "Artist", "kind": "read_text", "focus": "the artist name below the title", "question": "Artist?"},
            {"item": "Instrument", "kind": "read_text", "focus": "the instrument name in the header", "question": "Instrument?"},
        ]}
        vision = ['[{"bbox_2d": [444, 78, 552, 91]}]', "Guitar/Ukulele", "Guitar/Ukulele",
                  '[{"bbox_2d": [442, 76, 552, 91]}]', "Guitar/Ukulele", "Guitar/Ukulele"]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg Who is the artist and what instrument?")
        self.assertIn("⚠ Check the place: 'Instrument' read the same text", answer)
        self.assertIn("⚠ Check the place: 'Artist' read the same text", answer)
        self.assertIn("2 not confirmed", self.events[-1])

    # Run 22, case 02: a key signature is symbols, so both readings were "[no text]".
    def test_no_text_falls_back_to_the_whole_image(self):
        plan = {"parts": [{"item": "Key", "kind": "read_text", "focus": "the key signature", "question": "What is the key signature?"}]}
        vision = ['[{"bbox_2d": [62, 258, 107, 275]}]', "[no text]", "[no text]", "Three sharps (A major)."]
        planner, _, _ = self.planner(plan, vision)
        answer = planner.run("img/board.jpg What is the key signature?")
        self.assertIn("Three sharps (A major).", answer)
        self.assertIn("answered from the whole image", answer)
        self.assertTrue(any("has no readable text" in e for e in self.events))

    # Run 22, case 04: "the text of the comments" as one short reading returned only the first comment.
    def test_long_text_is_read_from_the_whole_image(self):
        plan = {"parts": [
            {"item": "댓글 내용", "kind": "read_text", "focus": "the text of the comments", "question": "댓글을 읽어 줘."},
            {"item": "웃긴 이유", "kind": "describe", "focus": "", "question": "왜 웃겨?"},
        ]}
        planner, _, fake_vision = self.planner(plan, ["댓글 네 개: ... 엄마 대결로 끝나서 웃깁니다."])
        answer = planner.run("img/street.jpg 댓글들을 읽고 왜 웃긴지 알려 줘")
        self.assertEqual(len(fake_vision.calls), 1)
        self.assertEqual([name for name, _ in self.tool_calls], ["describe_image"])
        self.assertIn("**댓글 내용 + 웃긴 이유**", answer)

    # Run 22, H1: "추천 수가 표시되지 않았습니다" was not recognised as "not shown".
    def test_korean_not_displayed_counts_as_not_shown(self):
        from agent.image_planner import says_not_shown
        self.assertTrue(says_not_shown("이미지에는 댓글의 추천 수가 표시되지 않았습니다. 따라서 확인할 수 없습니다."))

    def test_timings_are_shown(self):
        plan = {"parts": [{"item": "장면", "kind": "describe", "focus": "", "question": "어떤 장면이야?"}]}
        planner, _, _ = self.planner(plan, ["밤거리입니다."])
        planner.run("img/street.jpg 어떤 장면이야?")
        self.assertRegex(self.raw_events[0], r"^plan: 1 part\(s\) - 장면 \(\d+\.\d s\)$")
        self.assertRegex(self.raw_events[-1], r"\| total \d+\.\d s$")

    def test_questions_without_an_image_are_not_planned(self):
        planner, llm, _ = self.planner({"parts": []}, [])
        self.assertIsNone(planner.run("지금 몇 시야?"))
        self.assertIsNone(planner.run("img/missing.jpg 이건 뭐야?"))
        self.assertEqual(llm.calls, [])


class PlanParsingTests(unittest.TestCase):
    def test_parse_and_validate(self):
        raw = json.dumps({"parts": [
            {"item": "a", "kind": "describe", "focus": "", "question": "q1"},
            {"item": "b", "kind": "weird", "focus": "x", "question": "q2"},
            {"item": "", "kind": "describe", "focus": "", "question": "dropped"},
        ] + [{"item": f"p{i}", "kind": "describe", "focus": "", "question": "q"} for i in range(10)]})
        parts, ok = parse_plan(raw, "original")
        self.assertTrue(ok)
        self.assertEqual(len(parts), 7)  # capped at 8 entries, one of them empty
        self.assertEqual(parts[1].kind, "describe")  # unknown kind becomes describe

    def test_plan_misses(self):
        from agent.image_planner import Part, plan_misses
        parts = [Part("SD 카드 핀", "describe", "Micro SD Card U5", "CS, MOSI, SCK, MISO에 연결된 GPIO는?")]
        self.assertEqual(plan_misses("SD 카드(CS, MOSI, SCK, MISO)와 OLED(SDA, SCL) 핀은?", parts), ["OLED", "SDA", "SCL"])
        self.assertEqual(plan_misses("What is this?", parts), [])  # ordinary capitalised words are not labels
        self.assertEqual(plan_misses("SD 카드에 연결된 GPIO 핀은?", [Part("SD 카드 핀", "describe", "SD card", "SD 카드 핀은?")]), [])
        self.assertEqual(plan_misses("AMS1117 부품 번호는?", [Part("레귤레이터", "read_text", "AMS1117 regulator", "?")]), [])

    def test_echo_and_focus_helpers(self):
        from agent.image_planner import clean_focus, located_by_echo
        self.assertEqual(clean_focus("SD card interface (CS, MOSI, SCK, MISO)"), "SD card interface")
        self.assertEqual(clean_focus("(whatever)"), "(whatever)")
        self.assertEqual(clean_focus("the lowest Eb/N0 for log10(Pb) = -6"), "the lowest Eb/N0 for log10(Pb) = -6")
        self.assertTrue(located_by_echo("the lighting and shadows in the scene", "the lighting and shadows in the scene"))
        self.assertFalse(located_by_echo("ESP-WROOM-32", "ESP-WROOM-32"))
        self.assertFalse(located_by_echo("SD card socket", "Micro SD Card"))
        self.assertFalse(located_by_echo("the MCU module", ""))

    def test_find_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (5, 5)).save(root / "a.png")
            self.assertEqual(find_image_path("a.png 이거 뭐야?", root), "a.png")
            self.assertEqual(find_image_path("'a.png'를 봐 줘", root), "a.png")
            (root / "sub").mkdir()
            self.assertIsNone(find_image_path("../a.png", root / "sub"))  # outside the workspace

    def test_find_image_path_through_a_linked_folder(self):
        # macOS: /var/folders/... is a link to /private/var/folders/...
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            Image.new("RGB", (5, 5)).save(real / "a.png")
            linked = Path(tmp) / "linked"
            linked.symlink_to(real, target_is_directory=True)
            self.assertEqual(find_image_path("a.png 이거 뭐야?", linked), "a.png")


if __name__ == "__main__":
    unittest.main()
