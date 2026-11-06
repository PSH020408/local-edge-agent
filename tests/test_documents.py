"""Offline tests for reading documents and answering with page citations.

Run: python -m unittest discover -s tests -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from agent import build_default_registry
from agent import document_planner as dp
from agent.document_tools import Document, Page, load_document, looks_like_math, page_references, rank_pages
from agent.vision_tools import VisionConfig

GARBLED = "\n".join(["N −1", "1", "Yˆn , p =", "x", "(", "m", "+", "", ")", "e", "−", "j", "2", "π", "mp", "/", "N", "= Σ X"] * 2)


def make_pptx(path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    for i in range(5):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"Slide title {i + 1}"
        box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1))
        box.text_frame.text = f"Body text {i + 1}\nCourse footer 2026"
        if i == 2:
            table = slide.shapes.add_table(2, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
            table.cell(0, 0).text, table.cell(0, 1).text = "Chip", "RAM"
            table.cell(1, 0).text, table.cell(1, 1).text = "ESP32-C3", "400 KB"
            slide.notes_slide.notes_text_frame.text = "Say the RAM numbers out loud."
    prs.save(path)


class LoadingTests(unittest.TestCase):
    def test_pptx_text_tables_notes_and_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deck.pptx"
            make_pptx(path)
            document = load_document(path)
            self.assertEqual(len(document.pages), 5)
            page = document.page(3)
            self.assertEqual(page.title, "Slide title 3")
            self.assertIn("ESP32-C3 | 400 KB", page.text)
            self.assertIn("[speaker notes] Say the RAM numbers out loud.", page.text)
            self.assertNotIn("Course footer 2026", page.text)  # repeated on every slide: removed
            self.assertFalse(page.math)

    def test_image_only_pdf_needs_vision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            Image.new("RGB", (600, 800), "white").save(path)
            document = load_document(path)
            self.assertEqual(document.kind, "pdf")
            self.assertEqual(document.page(1).text, "")

    def test_garbled_equations_are_detected(self):
        self.assertTrue(looks_like_math(GARBLED))
        self.assertFalse(looks_like_math("Why Synchronization Required?\n• Symbol synchronization\n• Frame synchronization"))

    def test_page_references_and_ranking(self):
        doc = Document(Path("x.pdf"), "pdf", [
            Page(1, "Title page"), Page(2, "Synchronization Signal Block\nPSS SSS PBCH", title="5G SSB"),
            Page(3, "Cyclic prefix correlation", title="Timing estimation"),
        ])
        self.assertEqual(page_references("2페이지와 p.3, slide 9 설명해 줘", doc), [2, 3])  # slide 9 does not exist
        self.assertEqual(rank_pages(doc, "What is in the SSB? PSS")[0][0], 2)

    def test_read_document_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_pptx(root / "deck.pptx")
            registry = build_default_registry(root)
            out = registry.call("read_document", {"path": "deck.pptx", "pages": "2-3"})
            self.assertIn("[p.2] Slide title 2", out)
            self.assertIn("ESP32-C3 | 400 KB", out)
            self.assertNotIn("[p.1]", out)
            self.assertIn("is a document. Use read_document", registry.call("read_file", {"path": "deck.pptx"}))


class FakeLLM:
    """Returns scripted replies in order and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, format=None):
        self.calls.append({"messages": messages, "format": format})
        return {"message": {"role": "assistant", "content": self.replies.pop(0)}, "stats": {}}


class FakeVision:
    def __init__(self, answer="Y = \\frac{N-\\tau}{N} X_{n,p}"):
        self.answer = answer
        self.calls = []

    def describe(self, path, question, focus="", **kwargs):
        self.calls.append((path, question))
        return {"status": "ok", "answer": self.answer, "text": f"[describe_image result]\n{self.answer}"}


DOC = Document(Path("lecture.pdf"), "pdf", [
    Page(1, "Course title", title="Course title"),
    Page(2, "Why Synchronization Required?\nSymbol synchronization\nFrame synchronization", title="Why Synchronization Required?"),
    Page(3, GARBLED, title="Time Synchronization Error", images=1, math=True),
    Page(4, "Synchronization in 5G NR\nSSB: PSS, SSS, PBCH\nCell ID", title="Synchronization in 5G NR"),
])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "lecture.pdf").write_bytes(b"%PDF-1.4 placeholder")
        self.events, self.tools = [], []
        patcher = mock.patch.object(dp, "load_document", lambda path: DOC)
        patcher.start()
        self.addCleanup(patcher.stop)
        image = self.root / "logs" / "cache" / "pages" / "lecture_p3.png"
        image.parent.mkdir(parents=True)
        Image.new("RGB", (100, 80)).save(image)
        patcher = mock.patch.object(dp, "page_image", lambda doc, n, out: image)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def planner(self, llm, vision=None):
        registry = type("R", (), {"vision": vision})()
        return dp.DocumentQuestionPlanner(llm, registry, self.root, on_tool_call=lambda *a: self.tools.append(a), on_event=self.events.append)

    def test_selected_pages_are_answered_with_citations(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [4]}), "The SSB holds PSS, SSS and PBCH [p.4].")
        answer = self.planner(llm).run("lecture.pdf What is in the SSB?")
        self.assertEqual(llm.calls[0]["format"], dp.SELECT_SCHEMA)
        self.assertIn("p.4: Synchronization in 5G NR", llm.calls[0]["messages"][1]["content"])  # the index
        self.assertIn("[p.4] Synchronization in 5G NR", llm.calls[1]["messages"][1]["content"])  # the page text
        self.assertTrue(answer.startswith("The SSB holds PSS, SSS and PBCH [p.4]."))
        self.assertIn("Sources: p.4 (Synchronization in 5G NR)", answer)
        self.assertIn("check: 1 cited page(s)", self.events[-1])

    def test_page_named_in_the_question_skips_selection(self):
        llm = FakeLLM("동기화 종류는 Symbol과 Frame입니다 [p.2].")
        answer = self.planner(llm).run("lecture.pdf 2페이지 내용을 설명해 줘")
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("출처: p.2", answer)
        self.assertIn("pages named in the question: p.2", self.events)

    def test_equation_page_is_read_by_the_vision_model(self):
        vision = FakeVision()
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [3]}), "The desired term is (N-τ)/N X [p.3].")
        self.planner(llm, vision).run("lecture.pdf Write the desired signal term in LaTeX.")
        self.assertEqual(len(vision.calls), 1)
        self.assertIn("Transcribe every equation on it in LaTeX", vision.calls[0][1])
        prompt = llm.calls[1]["messages"][1]["content"]
        self.assertIn("[p.3, read by the vision model]\nY = \\frac{N-\\tau}{N} X_{n,p}", prompt)

    def test_equation_page_without_vision_is_marked_unreliable(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [3]}), "It cannot be read reliably [p.3].")
        self.planner(llm).run("lecture.pdf What is the equation?")
        self.assertIn("extracted as scattered symbols and are not reliable", llm.calls[1]["messages"][1]["content"])

    def test_missing_citations_are_asked_for_once_then_flagged(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [2]}), "Symbol and frame sync.", "Symbol and frame sync.")
        answer = self.planner(llm).run("lecture.pdf Which synchronization types?")
        self.assertEqual(len(llm.calls), 3)
        self.assertIn("answer had no page citations; asking again", self.events)
        self.assertIn("⚠ The answer has no page citations", answer)

    def test_citation_to_a_page_not_given_is_flagged(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [2]}), "Symbol sync [p.2]. Also PBCH [p.4].")
        answer = self.planner(llm).run("lecture.pdf Which synchronization types?")
        self.assertIn("⚠ The answer cites pages that were not given: p.4", answer)

    def test_number_not_in_the_document_is_flagged(self):
        # DH1-style: the lecture never gives a PSS length; "63" is invented.
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [4]}), "1. The PSS length is 63 [p.4].\n2. It has SSS [p.4].")
        answer = self.planner(llm).run("lecture.pdf PSS 길이는?")
        self.assertIn("⚠ 문서에서 찾을 수 없는 숫자가 답에 있습니다: 63", answer)
        self.assertNotIn("숫자가 답에 있습니다: 1", answer)  # list numbering is not a value

    def test_whole_document_is_summarised_in_parts(self):
        llm = FakeLLM(json.dumps({"scope": "whole", "pages": []}), "- Symbol sync [p.2]\n- SSB [p.4]",
                      "1. Q: What is in the SSB? A: PSS, SSS, PBCH [p.4]")
        answer = self.planner(llm).run("lecture.pdf 이 강의로 시험 문제를 만들어 줘")
        self.assertEqual(len(llm.calls), 3)  # select, one part (4 short pages), combine
        self.assertIn("Write practice exam questions", llm.calls[2]["messages"][0]["content"])
        self.assertIn("whole document: 1 part(s) summarised first, then combined", self.events)
        self.assertIn("출처: p.4", answer)

    # Run 25, DH1-DH3: "not in the document" answers were flagged for having no citations.
    def test_not_covered_answer_needs_no_citation(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [4]}), "이 강의에서는 LTE PSS 길이에 대한 정보를 제공하지 않았습니다.")
        answer = self.planner(llm).run("lecture.pdf LTE PSS 길이는?")
        self.assertEqual(len(llm.calls), 2)  # no second request for citations
        self.assertNotIn("⚠", answer)
        self.assertIn("(문서에 없다는 답입니다. 확인한 페이지: p.4)", answer)

    # Run 25, DH2: a question about something absent went to the whole-document path (258 s).
    def test_whole_document_only_for_summaries_and_practice_questions(self):
        llm = FakeLLM(json.dumps({"scope": "whole", "pages": []}), "The slides do not mention STM32.")
        self.planner(llm).run("lecture.pdf What clock speed does the STM32 have?")
        self.assertEqual(len(llm.calls), 2)  # select, answer: no summarising of every part
        self.assertTrue(any("not a summary or practice task" in e for e in self.events))

    # Run 25, D01: p.7 was read by the vision model for a question about plain text.
    def test_equation_pages_are_read_only_for_equation_questions(self):
        vision = FakeVision()
        long_math = Page(3, GARBLED + "\n" + "Case C: the FFT window starts outside the guard interval. " * 10,
                         title="Time Synchronization Error", images=1, math=True)
        doc = Document(DOC.path, "pdf", [DOC.pages[0], DOC.pages[1], long_math, DOC.pages[3]])
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [2, 3]}), "Symbol and frame [p.2].")
        with mock.patch.object(dp, "load_document", lambda path: doc):
            self.planner(llm, vision).run("lecture.pdf Which synchronization types are needed?")
        self.assertEqual(vision.calls, [])
        self.assertIn("Do not write these equations out", llm.calls[1]["messages"][1]["content"])

    # Run 25, D10: a practice answer gave (2/π)·arg γ for an equation that was never read.
    def test_equation_written_without_reading_the_page_is_flagged(self):
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [3]}), "The estimate is $$\\hat{\\epsilon} = \\frac{2}{\\pi} \\arg \\gamma$$ [p.3].")
        answer = self.planner(llm).run("lecture.pdf How is the offset estimated?")
        self.assertIn("⚠ The equations in this answer were written without reading the original page (p.3)", answer)

    # Run 26, D02: "$\\tau$" inside a sentence is a symbol, not an equation written from an unread page.
    def test_a_math_symbol_is_not_an_equation(self):
        self.assertFalse(dp._EQUATION.search("The phase shift is proportional to $ \\tau $ and $p$."))
        self.assertTrue(dp._EQUATION.search("$\\epsilon = f_{off} T_s$"))
        self.assertTrue(dp._EQUATION.search("$$\\frac{N-\\tau}{N} X_{n,p}$$"))

    def test_transcription_scaffolding_is_removed(self):
        raw = "\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n\\section*{Case C}\n\\begin{itemize}\n\\item Demodulation output\n\\[\n\\frac{N-\\tau}{N} X_{n,p}\n\\]\n\\end{itemize}\n\\end{document}"
        self.assertEqual(dp.clean_transcription(raw), "Case C\n- Demodulation output\n\\[\n\\frac{N-\\tau}{N} X_{n,p}\n\\]")

    def test_questions_without_a_document_are_not_handled(self):
        self.assertIsNone(self.planner(FakeLLM()).run("지금 몇 시야?"))
        self.assertIsNone(self.planner(FakeLLM()).run("missing.pdf 요약해 줘"))


class RouterTests(unittest.TestCase):
    def test_documents_first_then_images(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from main import QuestionRouter

        class Stub:
            def __init__(self, reply):
                self.reply, self.options = reply, None

            def run(self, question):
                return self.reply if ("." + self.reply.split(":")[0]) in question else None

        router = QuestionRouter(Stub("pdf:doc"), Stub("jpg:img"))
        self.assertEqual(router.run("a.pdf 요약"), "pdf:doc")
        self.assertEqual(router.run("a.jpg 설명"), "jpg:img")
        self.assertIsNone(router.run("몇 시야?"))


if __name__ == "__main__":
    unittest.main()
