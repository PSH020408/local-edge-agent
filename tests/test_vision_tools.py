"""Offline tests for the vision tool. Images are generated on the fly and the vision
model is replaced by a fake, so these run without Ollama and without the private
evaluation images.

Run: python -m unittest discover -s tests -v
"""

import base64
import io
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from agent import Agent, build_default_registry
from test_agent import FakeLLM, answer, tool_call
from agent.vision_tools import VisionConfig, prepare_image


class FakeVisionModel:
    """Records what it receives and answers with a fixed text."""

    def __init__(self, answer="A red square.", prompt_tokens=850):
        self.answer = answer
        self.prompt_tokens = prompt_tokens
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return {"message": {"role": "assistant", "content": self.answer}, "stats": {"prompt_tokens": self.prompt_tokens}}


def decode_sent_image(fake):
    data = base64.b64decode(fake.calls[-1][-1]["images"][0])
    return Image.open(io.BytesIO(data))


class PrepareImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_large_photo_is_downscaled_and_small_image_is_not_enlarged(self):
        # Run 11: a 1932x2576 photo cost 4,044 input tokens and 23 s before any answer.
        Image.new("RGB", (1932, 2576), "gray").save(self.dir / "big.jpg")
        Image.new("RGB", (284, 213), "gray").save(self.dir / "small.png")
        big = prepare_image(self.dir / "big.jpg", 1280)
        small = prepare_image(self.dir / "small.png", 1280)
        self.assertEqual(big.sent_size, (960, 1280))
        self.assertEqual(big.original_size, (1932, 2576))
        self.assertIn("downscaled from 1932x2576", big.notes[0])
        # Run 14: small full images are enlarged (at most 2x) because tokens have a floor anyway.
        self.assertEqual(small.sent_size, (568, 426))
        self.assertIn("small image enlarged 2.0x", small.notes[0])

    def test_gif_and_webp_are_converted(self):
        Image.new("P", (40, 30)).save(self.dir / "formula.gif")
        Image.new("RGB", (40, 30), "blue").save(self.dir / "scene.webp", format="WEBP")
        gif = prepare_image(self.dir / "formula.gif", 1280)
        webp = prepare_image(self.dir / "scene.webp", 1280)
        self.assertEqual(Image.open(io.BytesIO(gif.data)).format, "PNG")
        self.assertEqual(Image.open(io.BytesIO(webp.data)).format, "JPEG")
        self.assertEqual(webp.source_format, "WEBP")

    def test_animated_gif_uses_first_frame_and_says_so(self):
        frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green", "blue")]
        frames[0].save(self.dir / "anim.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
        prepared = prepare_image(self.dir / "anim.gif", 1280)
        self.assertIn("only the first frame", prepared.notes[0])
        self.assertEqual(Image.open(io.BytesIO(prepared.data)).convert("RGB").getpixel((5, 5)), (255, 0, 0))

    def test_transparent_png_is_flattened_on_white(self):
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(self.dir / "clear.png")
        prepared = prepare_image(self.dir / "clear.png", 1280)
        self.assertEqual(Image.open(io.BytesIO(prepared.data)).convert("RGB").getpixel((5, 5)), (255, 255, 255))

    def test_phone_photo_orientation_is_applied(self):
        # Phone cameras store portrait photos as landscape plus an EXIF rotation tag.
        image = Image.new("RGB", (400, 300), "gray")
        exif = image.getexif()
        exif[0x0112] = 6  # rotate 90 degrees clockwise when displayed
        image.save(self.dir / "phone.jpg", exif=exif)
        width, height = prepare_image(self.dir / "phone.jpg", 1280).sent_size
        self.assertGreater(height, width)  # portrait after rotation

    # Run 12: a small sign in a 1932x2576 photo was misread at every size (640 -> 1920).
    def test_region_crops_the_original_before_downscaling(self):
        image = Image.new("RGB", (2000, 2000), "white")
        image.paste((255, 0, 0), (1500, 1500, 2000, 2000))  # red block in the bottom-right corner
        image.save(self.dir / "photo.png")
        full = prepare_image(self.dir / "photo.png", 1000)
        zoom = prepare_image(self.dir / "photo.png", 1000, "bottom-right")
        # Pixel budget for max_side 1000 is 750,000 pixels -> 866x866 for a square.
        self.assertEqual(full.sent_size, (866, 866))
        self.assertEqual(zoom.sent_size, (866, 866))
        self.assertIn("zoomed into region 'bottom-right' (1000x1000 pixels", zoom.notes[0])
        self.assertEqual(Image.open(io.BytesIO(zoom.data)).getpixel((800, 800)), (255, 0, 0))
        # The red block covers a quarter of the full view but half of the zoomed view.
        zoomed = Image.open(io.BytesIO(zoom.data))
        self.assertEqual(zoomed.getpixel((400, 400)), (255, 255, 255))
        self.assertEqual(zoomed.getpixel((600, 600)), (255, 0, 0))

    def test_zoom_on_a_tall_photo_gives_more_detail(self):
        # Run 12 design bug: with a longest-side limit, the right half of a 1932x2576
        # photo was still scaled by 1280/2576, so zooming added no detail at all.
        Image.new("RGB", (1932, 2576), "gray").save(self.dir / "tall.jpg")
        full = prepare_image(self.dir / "tall.jpg", 1280)
        right = prepare_image(self.dir / "tall.jpg", 1280, "right")
        sign = prepare_image(self.dir / "tall.jpg", 1280, "0.7,0.42,1,0.56")
        self.assertEqual(full.sent_size, (960, 1280))           # scale 0.50
        self.assertGreater(right.sent_size[1] / 2576, 0.69)    # scale about 0.70
        self.assertGreater(sign.sent_size[0], 580 * 1.9)       # small crop: enlarged, not downscaled

    def test_small_zoomed_crop_is_enlarged_but_full_image_is_not(self):
        # Run 13: the 580x361 sign crop lost the "1" in "(031)". Crops are enlarged like a magnifier.
        Image.new("RGB", (1932, 2576), "gray").save(self.dir / "street.jpg")
        sign = prepare_image(self.dir / "street.jpg", 1280, "0.7,0.42,1,0.56")
        width, height = sign.sent_size
        self.assertAlmostEqual(width / height, 580 / 361, places=2)
        self.assertLessEqual(width * height, 1280 * 1280 * 3 // 4)
        self.assertGreater(width, 1000)
        self.assertIn("enlarged", sign.notes[-1])
        Image.new("RGB", (300, 200), "gray").save(self.dir / "small.png")
        self.assertEqual(prepare_image(self.dir / "small.png", 1280).sent_size, (600, 400))  # small full image: 2x cap
        tiny = prepare_image(self.dir / "small.png", 1280, "0.4,0.4,0.5,0.5")  # 30x20 crop
        self.assertEqual(tiny.sent_size, (90, 60))  # capped at 3x

    def test_region_formats(self):
        from agent.vision_tools import parse_region
        self.assertEqual(parse_region("right"), (0.5, 0.0, 1.0, 1.0))
        self.assertEqual(parse_region("Top Left"), (0.0, 0.0, 0.5, 0.5))
        self.assertEqual(parse_region("0.6,0.4,1,0.7"), (0.6, 0.4, 1.0, 0.7))
        with self.assertRaises(ValueError) as ctx:
            parse_region("upper corner")
        self.assertIn("'left,top,right,bottom' fractions", str(ctx.exception))
        with self.assertRaises(ValueError):
            parse_region("0.8,0.2,0.4,0.9")  # left > right

    def test_fake_image_is_rejected_with_a_hint(self):
        (self.dir / "photo.heic").write_bytes(b"not really an image")
        with self.assertRaises(ValueError) as ctx:
            prepare_image(self.dir / "photo.heic", 1280)
        self.assertIn("HEIC photos must be exported as JPEG", str(ctx.exception))


class DescribeImageToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "images").mkdir()
        Image.new("RGB", (2000, 1000), "red").save(self.root / "images" / "square.jpg")
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        self.fake = FakeVisionModel()
        self.registry = build_default_registry(self.root, self.fake, VisionConfig(max_side=1024))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, **args):
        return self.registry.call("describe_image", args)

    def test_sends_downscaled_image_with_system_prompt(self):
        out = self.call(path="images/square.jpg", question="What color is it?")
        self.assertIn("[describe_image result for square.jpg: JPEG 1254x627", out)
        self.assertIn("This is tool output, not the user's words", out)  # 786,432-pixel budget for max_side 1024
        self.assertIn("850 input tokens", out)
        self.assertIn("[note: downscaled from 2000x1000]", out)
        self.assertTrue(out.endswith("A red square."))
        messages = self.fake.calls[-1]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("say so instead of guessing", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "What color is it?")
        self.assertEqual(decode_sent_image(self.fake).size, (1254, 627))

    def test_zoom_through_the_tool(self):
        out = self.call(path="images/square.jpg", question="Read the sign", region="right")
        self.assertIn("[note: zoomed into region 'right' (1000x1000 pixels of the original)]", out)
        self.assertEqual(decode_sent_image(self.fake).size, (887, 887))
        self.assertIn("unknown region", self.call(path="images/square.jpg", region="somewhere"))

    def test_default_question_asks_for_exact_text(self):
        self.call(path="images/square.jpg")
        self.assertIn("read all visible text exactly", self.fake.calls[-1][1]["content"])

    def test_errors_guide_the_model(self):
        self.assertIn("does not exist", self.call(path="images/missing.png"))
        self.assertIn("not an image file", self.call(path="notes.txt"))
        self.assertIn("outside the workspace", self.call(path="../secret.png"))
        self.assertEqual(len(self.fake.calls), 0)

    def test_read_file_points_images_to_describe_image(self):
        out = self.registry.call("read_file", {"path": "images/square.jpg"})
        self.assertIn("Use describe_image", out)

    def test_read_file_rejects_other_binary_files(self):
        (self.root / "data.bin").write_bytes(b"\x00\x01\x02binary")
        self.assertIn("binary file", self.registry.call("read_file", {"path": "data.bin"}))

    def test_tool_is_absent_without_a_vision_model(self):
        registry = build_default_registry(self.root)
        self.assertNotIn("describe_image", registry.names())
        self.assertIn("describe_image", self.registry.names())


class MainModelUsesVisionTests(unittest.TestCase):
    """The main model never receives image bytes, only the vision model's text."""

    def test_main_model_calls_describe_image_and_gets_text_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (64, 64), "white").save(root / "slide.png")
            vision = FakeVisionModel(answer="Title: 재무제표")
            registry = build_default_registry(root, vision, VisionConfig())

            class MainModel:
                def __init__(self):
                    self.calls = []

                def chat(self, messages, tools=None):
                    self.calls.append(list(messages))  # copy: the agent keeps appending to the same list
                    if len(self.calls) == 1:
                        call = {"function": {"name": "describe_image", "arguments": {"path": "slide.png", "question": "Read the title"}}}
                        return {"message": {"role": "assistant", "content": "", "tool_calls": [call]}, "stats": {}}
                    return {"message": {"role": "assistant", "content": "The title is 재무제표."}, "stats": {}}

            main = MainModel()
            answer = Agent(main, registry).run("What is the title of slide.png?")
            self.assertEqual(answer, "The title is 재무제표.")
            tool_message = main.calls[1][-1]
            self.assertEqual(tool_message["role"], "tool")
            self.assertIn("Title: 재무제표", tool_message["content"])
            self.assertTrue(all("images" not in m for m in main.calls[1]))


if __name__ == "__main__":
    unittest.main()


class ScriptedVisionModel:
    """Returns scripted answers in order: first the location, then the readings."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return {"message": {"role": "assistant", "content": self.answers.pop(0)}, "stats": {"prompt_tokens": 1200}}


class ReadTextInImageTests(unittest.TestCase):
    """Run 13: the main model zoomed into 'right' (still downscaled) and reported
    '02-6715-1544' instead of '(031)715-1544' without any check."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (1932, 2576), "gray").save(self.root / "street.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, answers, target="the shop sign"):
        fake = ScriptedVisionModel(answers)
        registry = build_default_registry(self.root, fake, VisionConfig())
        return registry.call("read_text_in_image", {"path": "street.jpg", "target": target}), fake

    def test_locate_zoom_and_confirm(self):
        out, fake = self.run_tool([
            '[{"bbox_2d": [870, 435, 945, 470], "label": "shop sign"}]',
            "푸르지오강남\n(031)715-1544",
            "푸르지오강남 (031)715-1544",
        ])
        self.assertIn("found 'the shop sign' at 0.870,0.435,0.945,0.470, identified as 'shop sign', 3 vision calls", out)
        self.assertIn("CONFIRMED", out)
        self.assertEqual(len(fake.calls), 3)
        # The location request asks for the 0-1000 scale; the readings forbid adding area codes.
        self.assertIn("0-1000 scale", fake.calls[0][-1]["content"])
        self.assertIn("do not add area codes", fake.calls[1][-1]["content"])
        # Both readings are zoomed crops of the found box, enlarged well beyond the original pixels.
        tight = Image.open(io.BytesIO(base64.b64decode(fake.calls[1][-1]["images"][0])))
        self.assertGreater(tight.size[0], 0.075 * 1932 * 1.15 * 2)

    def test_disagreement_is_reported_not_hidden(self):
        out, _ = self.run_tool(['[{"bbox_2d": [870, 435, 945, 470]}]', "(031)715-1544", "02-6715-1544"])
        self.assertIn("UNCERTAIN", out)
        self.assertIn("Report both to the user", out)
        self.assertIn("(031)715-1544", out)
        self.assertIn("02-6715-1544", out)

    def test_unclear_characters_are_flagged(self):
        out, _ = self.run_tool(['[{"bbox_2d": [870, 435, 945, 470]}]', "(03?)715-1544", "(03?)715-1544"])
        self.assertIn("PARTLY UNCLEAR", out)

    def test_not_found(self):
        out, fake = self.run_tool(["[]"], target="a price tag")
        self.assertIn("NOT LOCATED: the vision model could not place 'a price tag'", out)
        self.assertEqual(len(fake.calls), 1)

    def test_box_formats(self):
        from agent.vision_tools import parse_boxes, padded_region
        size = (960, 1280)
        self.assertEqual(parse_boxes('```json\n[{"bbox_2d": [100, 200, 300, 400]}]\n```', size), [(0.1, 0.2, 0.3, 0.4)])
        # Pixel coordinates of the sent image are recognized by values above 1000.
        self.assertEqual(parse_boxes('[{"bbox_2d": [480, 640, 960, 1280]}]', size), [(0.5, 0.5, 1.0, 1.0)])
        # Plain text with a list, swapped corners, values outside the image.
        self.assertEqual(parse_boxes("The sign is at [300, 400, 100, 200].", size), [(0.1, 0.2, 0.3, 0.4)])
        self.assertEqual(parse_boxes('[{"bbox_2d": [900, 900, 1100, 1000]}]', size)[0][2], 1.0)
        self.assertEqual(parse_boxes("no box here", size), [])
        self.assertEqual(padded_region((0.4, 0.4, 0.6, 0.5), 0.5), "0.3000,0.3500,0.7000,0.5500")
        self.assertEqual(padded_region((0.0, 0.9, 0.2, 1.0), 0.5), "0.0000,0.8500,0.3000,1.0000")


class Run14FixesTests(unittest.TestCase):
    """Fixes from the full vision test set (12 images + 4 hallucination checks)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (1920, 1444), "white").save(self.root / "schematic.jpg")
        Image.new("RGB", (284, 213), "white").save(self.root / "cartoon.webp", format="WEBP")

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, answers):
        fake = ScriptedVisionModel(answers)
        return build_default_registry(self.root, fake, VisionConfig()), fake

    def test_focus_finds_zooms_and_answers_from_the_crop(self):
        # 01: four SD/OLED pins were wrong from the downscaled full schematic.
        registry, fake = self.tool(['[{"bbox_2d": [740, 740, 840, 860]}]', "CS G05, MOSI G23, SCK G18, MISO G19"])
        out = registry.call("describe_image", {
            "path": "schematic.jpg", "question": "SD 카드 핀 연결은?", "focus": "the Micro SD card module U5"})
        self.assertIn("2 vision calls", out)
        self.assertIn("focused on 'the Micro SD card module U5' found at 0.740,0.740,0.840,0.860", out)
        self.assertTrue(out.endswith("CS G05, MOSI G23, SCK G18, MISO G19"))
        crop = Image.open(io.BytesIO(base64.b64decode(fake.calls[1][-1]["images"][0])))
        # The crop (box + 25% margin, enlarged) shows the module far larger than the full view would.
        self.assertGreater(crop.size[0], 0.15 * 1920 * 1.5)
        self.assertEqual(fake.calls[1][-1]["content"], "SD 카드 핀 연결은?")  # question passed unchanged

    def test_focus_not_found(self):
        registry, fake = self.tool(["[]"])
        out = registry.call("describe_image", {"path": "schematic.jpg", "question": "값은?", "focus": "resistor R50"})
        self.assertIn("NOT FOUND", out)
        self.assertEqual(len(fake.calls), 1)

    def test_not_found_tells_the_model_not_to_retry_for_a_value(self):
        # H3: after "not found" the main model asked describe_image, which invented "R50 is 10k".
        registry, _ = self.tool(["[]"])
        out = registry.call("read_text_in_image", {"path": "schematic.jpg", "target": "the value of resistor R50"})
        self.assertIn("NOT FOUND", out)
        self.assertIn("It is probably not in the image", out)
        self.assertIn("Do not ask describe_image for its value", out)

    def test_small_image_is_enlarged_before_describing(self):
        # 08: the 284x213 cartoon frame.
        registry, fake = self.tool(["A man holding his knee in pain."])
        out = registry.call("describe_image", {"path": "cartoon.webp", "question": "무슨 일이야?"})
        self.assertIn("WEBP 568x426", out)
        self.assertIn("small image enlarged 2.0x", out)

    def test_tool_descriptions_guide_language_and_scope(self):
        registry, _ = self.tool([])
        describe = registry.get("describe_image").parameters["properties"]
        self.assertIn("do not translate it", describe["question"]["description"])
        self.assertIn("ask only about that part", describe["question"]["description"])
        self.assertIn("focus", describe)
        read_doc = registry.get("read_text_in_image").description
        self.assertIn("Not for transcribing a whole page", read_doc)


class Run15FixesTests(unittest.TestCase):
    """Fixes from rerunning the failed cases after Run 14."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (758, 660), "white").save(self.root / "tweet.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_focus_covering_most_of_the_image_uses_the_whole_image(self):
        # 03: focus 'the tweet thread' covered 95% of the image.
        fake = ScriptedVisionModel(['[{"bbox_2d": [28, 19, 977, 987]}]', "Summary."])
        registry = build_default_registry(self.root, fake, VisionConfig())
        out = registry.call("describe_image", {"path": "tweet.jpg", "question": "요약해 줘", "focus": "the tweet thread"})
        self.assertIn("covers most of the image", out)
        self.assertNotIn("zoomed into region", out)
        sent = Image.open(io.BytesIO(base64.b64decode(fake.calls[1][-1]["images"][0])))
        self.assertEqual(sent.size, (758, 660))

    def test_near_768_images_are_not_enlarged_by_1x(self):
        # 03: a 758x660 image got the meaningless note "small image enlarged 1.0x".
        self.assertEqual(prepare_image(self.root / "tweet.jpg", 1280).notes, [])

    def test_prompts_separate_seeing_from_guessing(self):
        # 10: "푸르지오강남" on a sign was turned into "the photo was taken in Gangnam, Seoul".
        from agent.loop import DEFAULT_SYSTEM_PROMPT
        from agent.vision_tools import VISION_SYSTEM_PROMPT
        self.assertIn("not evidence of the location", VISION_SYSTEM_PROMPT)
        self.assertIn("Never state a location from a business name", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("read_text_in_image for each sign", DEFAULT_SYSTEM_PROMPT)

    def test_focus_description_rules(self):
        registry = build_default_registry(self.root, ScriptedVisionModel([]), VisionConfig())
        tool = registry.get("describe_image")
        self.assertIn("never the question itself", tool.parameters["properties"]["focus"]["description"])
        self.assertIn("Leave focus empty when the question is about the whole image", tool.description)


class Run16FixesTests(unittest.TestCase):
    """Fixes after rerunning 01, 03, 04 and 10."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (1920, 1444), "white").save(self.root / "schematic.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, answers, num_predict=1200):
        fake = ScriptedVisionModel(answers)
        return build_default_registry(self.root, fake, VisionConfig(num_predict=num_predict)), fake

    def test_repeating_answer_is_cut(self):
        # 03: one answer looped on the same sentence for 196 s.
        from agent.vision_tools import trim_repetition
        loop = "John Fury criticized Paul Felder. " + "They refuse to accept criticism. " * 40
        text, looped = trim_repetition(loop)
        self.assertTrue(looped)
        self.assertEqual(text, "John Fury criticized Paul Felder.\nThey refuse to accept criticism.")
        normal = "푸르지오강남\n(031)715-1544\n1544\n1544"  # short repeats such as numbers are kept
        self.assertEqual(trim_repetition(normal), (normal, False))

    def test_looping_vision_answer_is_flagged_in_the_tool_result(self):
        registry, _ = self.tool(["A sign. " + "The same sentence again and again. " * 10])
        out = registry.call("describe_image", {"path": "schematic.jpg", "question": "?"})
        self.assertIn("started repeating itself", out)
        self.assertEqual(out.count("The same sentence again and again."), 1)

    def test_length_limit_is_flagged(self):
        class LongModel(ScriptedVisionModel):
            def chat(self, messages, tools=None):
                result = super().chat(messages, tools)
                result["stats"]["output_tokens"] = 1200
                return result
        fake = LongModel(["Very long answer"])
        registry = build_default_registry(self.root, fake, VisionConfig(num_predict=1200))
        out = registry.call("describe_image", {"path": "schematic.jpg", "question": "?"})
        self.assertIn("hit the length limit", out)

    def test_category_not_located_suggests_a_retry(self):
        # 01: "MCU 모듈" was not found although the board shows "ESP-WROOM-32".
        registry, _ = self.tool(["[]"])
        out = registry.call("describe_image", {"path": "schematic.jpg", "question": "?", "focus": "MCU 모듈"})
        self.assertIn("NOT LOCATED", out)
        self.assertIn("does not prove it is absent", out)
        self.assertIn("Retry once with the text printed in the image", out)

    def test_printed_label_not_found_stays_strict(self):
        for target in ("resistor R50", "the value of R50", "chip U12", "the AMS1117 label"):
            registry, _ = self.tool(["[]"])
            out = registry.call("read_text_in_image", {"path": "schematic.jpg", "target": target})
            self.assertIn("NOT FOUND", out, target)
            self.assertIn("probably not in the image", out, target)

    def test_focus_reports_what_was_found(self):
        # 01: focus "OLED" located the FTDI header U4.
        registry, _ = self.tool(['[{"bbox_2d": [636, 375, 725, 466], "label": "U4 FTDI"}]', "DTR, RXD, TXD"])
        out = registry.call("describe_image", {"path": "schematic.jpg", "question": "?", "focus": "OLED display"})
        self.assertIn("identified as 'U4 FTDI'", out)
        self.assertIn("If that is not the part you meant, retry with the label printed on it", out)

    def test_locate_prompt_matches_by_meaning(self):
        from agent.vision_tools import LOCATE_PROMPT
        self.assertIn("Match by meaning as well as by printed text", LOCATE_PROMPT)

    def test_planning_rules_in_system_prompt(self):
        from agent.loop import DEFAULT_SYSTEM_PROMPT
        for rule in (
            "make one call per part and ask only about that part",
            "Do not read the same thing again with another tool",
            "Never put a value you expect",
            "trust read_text_in_image",
            "Only call a reading certain when the tool said CONFIRMED",
        ):
            self.assertIn(rule, DEFAULT_SYSTEM_PROMPT)


class Run17FixesTests(unittest.TestCase):
    """Fixes after the third rerun: enforce in code what the 8B model ignored in text."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Image.new("RGB", (960, 1280), "gray").save(self.root / "street.jpg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_whole_image_focus_is_ignored(self):
        for focus in ("whole image", "the entire image", "Whole Image", "전체", "이미지 전체", "all"):
            fake = ScriptedVisionModel(["A night street."])
            registry = build_default_registry(self.root, fake, VisionConfig())
            out = registry.call("describe_image", {"path": "street.jpg", "question": "설명해 줘", "focus": focus})
            self.assertTrue(out.endswith("A night street."), focus)
            self.assertEqual(len(fake.calls), 1, focus)  # no locate call

    def test_real_parts_are_still_located(self):
        fake = ScriptedVisionModel(['[{"bbox_2d": [100, 100, 300, 300], "label": "U5"}]', "ok"])
        registry = build_default_registry(self.root, fake, VisionConfig())
        registry.call("describe_image", {"path": "street.jpg", "question": "?", "focus": "the full-color legend"})
        self.assertEqual(len(fake.calls), 2)

    def test_not_located_counts_as_a_failed_call(self):
        # The same failing call ran three times because the loop only counted "Error..." results.
        vision = ScriptedVisionModel(["[]", "[]", "[]"])
        registry = build_default_registry(self.root, vision, VisionConfig())
        bad = tool_call("describe_image", path="street.jpg", question="?", focus="the red car")
        main = FakeLLM([bad, bad, bad, answer("unused")])
        result = Agent(main, registry).run("빨간 차 어디 있어?")
        self.assertIn("Stopped: the same describe_image call failed 2 times", result)
        self.assertEqual(len(vision.calls), 1)  # the repeat was blocked before reaching the vision model

    def test_sign_reading_carries_a_location_reminder(self):
        fake = ScriptedVisionModel(['[{"bbox_2d": [870, 435, 945, 470]}]', "푸르지오강남", "푸르지오강남"])
        registry = build_default_registry(self.root, fake, VisionConfig())
        out = registry.call("read_text_in_image", {"path": "street.jpg", "target": "the sign on the right"})
        self.assertIn("not evidence of where the photo was taken", out)

    def test_prompts(self):
        from agent.loop import DEFAULT_SYSTEM_PROMPT
        from agent.vision_tools import VISION_SYSTEM_PROMPT
        self.assertIn("check that every part of the user's question has a tool result", DEFAULT_SYSTEM_PROMPT)
        self.assertIn("not the pin number of the part", VISION_SYSTEM_PROMPT)


class Run18FixesTests(unittest.TestCase):
    def test_tiny_focus_box_gets_a_minimum_crop(self):
        # A 0.037 x 0.016 box became a 107x35 pixel crop with nothing readable in it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (1920, 1444), "white").save(root / "board.jpg")
            fake = ScriptedVisionModel(['[{"bbox_2d": [663, 531, 700, 547]}]', "ok"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("describe_image", {"path": "board.jpg", "question": "?", "focus": "OLED"})
            region = re.search(r"zoomed into region '([\d.,]+)'", out).group(1)
            left, top, right, bottom = (float(v) for v in region.split(","))
            self.assertGreaterEqual(right - left, 0.1499)
            self.assertGreaterEqual(bottom - top, 0.1499)

    def test_readings_ask_only_for_the_target_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (1920, 1444), "white").save(root / "board.jpg")
            fake = ScriptedVisionModel(['[{"bbox_2d": [82, 71, 152, 120]}]', "AMS1117-3V3", "AMS1117-3V3"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("read_text_in_image", {"path": "board.jpg", "target": "the part number of the regulator U1"})
            for call in fake.calls[1:]:
                self.assertIn("Read this text in the image: the part number of the regulator U1.", call[-1]["content"])
                self.assertIn("Leave out other text around it.", call[-1]["content"])
            self.assertIn("CONFIRMED: both readings agree.", out)
            # Not a photo of a street: no note about signs and locations.
            self.assertNotIn("not evidence of where the photo was taken", out)

    def test_punctuation_only_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (960, 1280), "gray").save(root / "street.jpg")
            fake = ScriptedVisionModel(['[{"bbox_2d": [874, 442, 933, 465]}]', "031-715-1544", "(031)715-1544"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("read_text_in_image", {"path": "street.jpg", "target": "the phone number on the shop sign"})
            self.assertIn("CONFIRMED CHARACTERS", out)
            self.assertIn("not evidence of where the photo was taken", out)
            fake = ScriptedVisionModel(['[{"bbox_2d": [874, 442, 933, 465]}]', "(03)715-1544", "(031)715-1544"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("read_text_in_image", {"path": "street.jpg", "target": "the phone number on the shop sign"})
            self.assertIn("UNCERTAIN", out)  # a missing digit is a real difference

    def test_cut_off_reading(self):
        from agent.vision_tools import _one_is_cut_off
        self.assertTrue(_one_is_cut_off("AMS1117", "AMS1117-3V3"))
        self.assertTrue(_one_is_cut_off("715-1544", "(031)715-1544"))
        self.assertFalse(_one_is_cut_off("(03)715-1544", "(031)715-1544"))  # a digit inside differs
        self.assertFalse(_one_is_cut_off("AM", "AMS1117"))  # too short to count

    def test_run21_reading_rules(self):
        from agent.vision_tools import _SIGN_TARGET, repeats_request, trim_repetition
        self.assertFalse(_SIGN_TARGET.search("the key signature at the beginning of the staff"))
        self.assertTrue(_SIGN_TARGET.search("the large sign on the right building"))
        self.assertTrue(repeats_request("the key signature at the beginning of the staff.", "the key signature at the beginning of the staff"))
        self.assertFalse(repeats_request("F#m7", "the first chord"))
        sample = "handwriting 손글씨\nhandwriting 손글씨\nhandwriting 손글씨\n저 손글씨 잘 못씁니다TT"
        self.assertEqual(trim_repetition(sample), (sample, False))  # three real repeats are kept

    def test_generic_read_target_uses_the_largest_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (960, 1280), "gray").save(root / "street.jpg")
            boxes = '[{"bbox_2d": [726, 446, 744, 462]}, {"bbox_2d": [870, 435, 945, 475]}]'
            fake = ScriptedVisionModel([boxes, "푸르지오강남", "푸르지오강남"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("read_text_in_image", {"path": "street.jpg", "target": "any signs visible in the photo"})
            self.assertIn("at 0.870,0.435,0.945,0.475", out)
            fake = ScriptedVisionModel([boxes, "?", "?"])
            registry = build_default_registry(root, fake, VisionConfig())
            out = registry.call("read_text_in_image", {"path": "street.jpg", "target": "the phone number"})
            self.assertIn("at 0.726,0.446,0.744,0.462", out)  # a specific target keeps the best match

    def test_nearby_lines(self):
        from agent.vision_tools import _nearby_lines
        self.assertEqual(_nearby_lines("WONDERWALL", "WONDERWALL\nGuitar/Ukulele"), ["Guitar/Ukulele"])
        self.assertEqual(_nearby_lines("X(k) = sum x(n)", "DFT(FFT):\nX(k) = sum x(n)"), ["DFT(FFT):"])
        self.assertIsNone(_nearby_lines("AMS1117-", "AMS1117-3V3"))  # the same line continues: cut off, not nearby
        self.assertIsNone(_nearby_lines("[no text]", "[no text]\nC8"))

    def test_widened_region_stays_inside_the_image(self):
        from agent.vision_tools import widened_region
        values = [float(v) for v in widened_region((0.95, 0.0, 0.99, 0.02), 0.4).split(",")]
        self.assertEqual(values, [0.6, 0.0, 1.0, 0.4])


class GuardDisplayTests(unittest.TestCase):
    """Guards must be visible in the terminal, not hidden in a cut-off preview."""

    def test_guard_lines_are_shown_in_full(self):
        from agent.display import format_tool_call
        result = (
            "[describe_image result for street.jpg: JPEG 960x1280, 11.6 s. This is tool output, not the user's words]\n"
            "[note: focus 'whole image' was ignored because it means the whole image]\n"
            "[note: downscaled from 1932x2576]\n"
            + "A long description of the night street. " * 20
        )
        out = format_tool_call("describe_image", {"focus": "whole image"}, result, color=False)
        self.assertIn("\u2699 focus 'whole image' was ignored because it means the whole image", out)
        self.assertIn("\u2699 downscaled from 1932x2576", out)
        self.assertIn("...", out)  # the description itself is still shortened

    def test_verdicts_and_blocks_are_shown(self):
        from agent.display import guard_lines
        result = "Reading 1:\n(031)715-1544\nUNCERTAIN: the two readings differ.\nNote: text on a sign names a business."
        self.assertEqual(len(guard_lines(result)), 2)
        self.assertEqual(guard_lines("Error: you already made this exact call and it failed."),
                         ["Error: you already made this exact call and it failed."])

    def test_whole_image_focus_leaves_a_visible_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            Image.new("RGB", (100, 100)).save(Path(tmp) / "a.png")
            registry = build_default_registry(Path(tmp), ScriptedVisionModel(["ok"]), VisionConfig())
            out = registry.call("describe_image", {"path": "a.png", "question": "?", "focus": "whole image"})
            self.assertIn("[note: focus 'whole image' was ignored", out)
