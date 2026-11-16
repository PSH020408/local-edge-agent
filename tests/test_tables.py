"""Offline tests for agent/table_tools.py and the Stage 6 changes to the document planner."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import table_tools as tt  # noqa: E402

CONTOSO = """| | 2024 | 2025 |
|---|---|---|
| Revenue | 2,040 | 2,310 |
| Cost of revenue | (930) | (1,050) |
| Gross profit | 1,110 | 1,360 |
| Operating expenses | (780) | (850) |
| Operating income | 330 | 410 |"""


class NumberTests(unittest.TestCase):
    def test_printed_numbers(self):
        self.assertEqual(tt.parse_number("1,234,567"), 1234567)
        self.assertEqual(tt.parse_number("(4,480,835)"), -4480835)
        self.assertEqual(tt.parse_number("△301,146"), -301146)
        self.assertEqual(tt.parse_number("~48"), 48)
        self.assertEqual(tt.parse_number("-0.6"), -0.6)
        self.assertIsNone(tt.parse_number("-"))

    def test_only_arithmetic_is_evaluated(self):
        self.assertAlmostEqual(tt.safe_eval("(112,010 − 93,736) / 93,736 × 100"), 19.4952, places=3)
        with self.assertRaises(ValueError):
            tt.safe_eval("__import__('os')")


class CalculationTests(unittest.TestCase):
    def test_calc_tags_are_filled_by_code(self):
        answer, results = tt.fill_calculations("Growth was [calc: (112010 - 93736) / 93736 * 100]% [p.32].")
        self.assertIn("= 19.50%", answer)
        self.assertEqual(results, ["19.50"])
        answer, _ = tt.fill_calculations("[calc: 1 / 0]")
        self.assertIn("could not be calculated", answer)

    def test_written_arithmetic_is_checked_and_corrected(self):
        # Run 42, TC3: 1,777,303 / 6,141,116 is 28.94%, written as 28.95%.
        answer, fixes, _ = tt.check_arithmetic("부채비율 = 1,777,303 / 6,141,116 ≈ 28.95% [p.14].")
        self.assertIn("≈ 28.94%", answer)
        self.assertEqual(fixes, [("1,777,303 / 6,141,116", "28.95", "28.94")])
        answer, fixes, checked = tt.check_arithmetic("85,315,148 - 47,522,179 = 37,792,969백만원")
        self.assertEqual(fixes, [])
        self.assertEqual(checked, ["37,792,969"])
        self.assertEqual(tt.check_arithmetic("43,601,051 / 333,605,938 ≈ 0.1307")[1], [])

    def test_year_ranges_are_not_subtractions(self):
        self.assertEqual(tt.check_arithmetic("in 2024-2025 = two years")[1], [])


class StatementTests(unittest.TestCase):
    def test_balance_sheet_identity_from_text(self):
        text = "자산총계 566,942,110 514,531,948\n부채총계 130,621,773 112,339,878\n자본총계 436,320,337 402,192,070"
        checks = tt.statement_checks(text)
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c.ok for c in checks))

    def test_a_wrong_subtotal_is_found_and_not_passed_on(self):
        # Run 42, SC6: gross profit 2025 printed 1,360 (2,310 − 1,050 = 1,260); operating income
        # 410 is right for the correct gross profit and must not be called wrong.
        checks = {(c.name.split(" =")[0], c.column): c for c in tt.statement_checks(CONTOSO)}
        self.assertFalse(checks[("gross profit", 1)].ok)
        self.assertEqual(checks[("gross profit", 1)].expected, 1260)
        self.assertTrue(checks[("operating income", 1)].ok)
        self.assertTrue(checks[("gross profit", 0)].ok)
        text = tt.describe_checks(tt.statement_checks(CONTOSO), 10)
        self.assertIn("DOES NOT MATCH: the parts give 1,260", text)
        self.assertIn("checked by code", text)

    def test_note_references_and_dollar_signs_are_ignored(self):
        text = "Total assets $ 359,241 $ 364,980\nTotal liabilities 285,508 308,030\nTotal shareholders’ equity 73,733 56,950"
        self.assertTrue(all(c.ok for c in tt.statement_checks(text)))
        text = "매출액 (주30) 333,605,938\n매출원가 (주21) 202,235,513\n매출총이익 131,370,425"
        self.assertTrue(tt.statement_checks(text)[0].ok)


class PicturePageTests(unittest.TestCase):
    def test_pages_made_of_one_picture_each_are_picture_pages(self):
        # Run 42: the same full-page picture box on every page was taken for the template.
        from PIL import Image

        from agent.document_tools import load_document

        with tempfile.TemporaryDirectory() as tmp:
            images = [Image.new("RGB", (800, 450), (255, 255, 255)) for _ in range(5)]
            path = Path(tmp) / "scan.pdf"
            images[0].save(path, save_all=True, append_images=images[1:])
            document = load_document(path)
            self.assertTrue(all(page.images >= 1 for page in document.pages))


class PlannerTests(unittest.TestCase):
    def test_checks_go_to_the_context_and_calculations_are_done_by_code(self):
        import ctypes

        import pypdfium2 as pdfium
        import pypdfium2.raw as raw

        from agent import document_planner as dp

        class FakeLLM:
            def __init__(self, *replies):
                self.replies, self.calls = list(replies), []

            def chat(self, messages, tools=None, format=None):
                self.calls.append(messages)
                return {"message": {"role": "assistant", "content": self.replies.pop(0)}, "stats": {}}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = pdfium.PdfDocument.new()
            for lines in (["Statement of operations", "Revenue 2,310", "Cost of revenue (1,050)", "Gross profit 1,360"],
                          ["Notes", "Nothing else here"], ["More notes", "Still nothing"]):
                page = pdf.new_page(600, 800)
                for i, text in enumerate(lines):
                    obj = raw.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", ctypes.c_float(12))
                    buffer = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
                    raw.FPDFText_SetText(obj, ctypes.cast(buffer, ctypes.POINTER(raw.FPDF_WCHAR)))
                    raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 72, 700 - 20 * i)
                    raw.FPDFPage_InsertObject(page.raw, obj)
                raw.FPDFPage_GenerateContent(page.raw)
                page.close()
            pdf.save(str(root / "report.pdf"))
            pdf.close()
            llm = FakeLLM(json.dumps({"scope": "pages", "pages": [1]}),
                          "Gross profit is printed as 1,360 but should be [calc: 2310 - 1050] [p.1].")
            registry = type("R", (), {"vision": None})()
            answer = dp.DocumentQuestionPlanner(llm, registry, root).run("report.pdf Is gross profit right?")
            context = llm.calls[1][1]["content"]
            self.assertIn("DOES NOT MATCH: the parts give 1,260", context)
            self.assertIn("2310 - 1050 = 1,260", answer)
            self.assertNotIn("not appear in the document", answer)
            self.assertIn("1 calculation(s) were done by code", answer)

    def test_numbers_with_two_separators_are_one_number(self):
        from agent.document_planner import unsupported_numbers

        # Run 42, TA5: 37,792,969 was split into 37792 and 969.
        self.assertEqual(unsupported_numbers("차이는 37,792,969백만원입니다", "37,792,969", ""), [])
        self.assertEqual(unsupported_numbers("It is 1,234,567 [p.1]", "nothing", ""), ["1234567"])



class ExplainTests(unittest.TestCase):
    """Run 43: arithmetic written in LaTeX, outside [calc: ...]."""

    def test_a_rounding_slip_in_a_latex_answer_is_corrected(self):
        answer = ("Net income was $112,010 million, and $93,736 million in 2024 [p.32].\n\n"
                  "$$ G = \\left( \\frac{112,010 - 93,736}{93,736} \\right) \\times 100 = 19.49\\% $$")
        fixed, fixes, explained = tt.explain_numbers(answer, ["19.49"], {"112010", "93736"})
        self.assertIn("19.50", fixed)
        self.assertEqual(fixes[0][1:], ("19.49", "19.50"))

    def test_correct_results_are_explained_and_others_are_not(self):
        _, fixes, explained = tt.explain_numbers("$89.3 billion and $15.4 billion, $104.7 billion in total", ["104.7"], {"89.3", "15.4"})
        self.assertEqual((fixes, explained), ([], ["104.7"]))
        _, fixes, explained = tt.explain_numbers("It was 1,475억 원 [p.8].", ["1475"], {"24.9", "12.9"})
        self.assertEqual((fixes, explained), ([], []))

    def test_operands_in_earlier_paragraphs_and_two_steps(self):
        # Run 44, TB1: operands in the prose, the result two LaTeX blocks later, in two steps.
        answer = ("The net income for fiscal 2024 was $93,736 million and $112,010 million in 2025 [p.32].\n\n"
                  "$$\nG = \\left( \\frac{112,010 - 93,736}{93,736} \\right) \\times 100\n$$\n\n"
                  "$$\nG = \\left( \\frac{18,274}{93,736} \\right) \\times 100\n$$\n\n"
                  "$$\nG = 19.48\\%\n$$\n\n"
                  "Therefore, the net income grew by approximately 19.48% from 2024 to 2025.")
        fixed, fixes, explained = tt.explain_numbers(answer, ["18274", "19.48"], {"112010", "93736"})
        self.assertIn("18274", explained)
        self.assertEqual(fixes[0][1:], ("19.48", "19.50"))
        self.assertNotIn("19.48", fixed)
        self.assertIn("approximately 19.50%", fixed)

    def test_a_number_given_as_a_fact_is_never_changed(self):
        # Close to 1,288 / 1,000 × 1,000 = 1,288, but stated as a fact, not as a result.
        answer = "Revenue was 1,288 in 2024 and 1,000 in 2023 [p.3].\n\nThe segment had 1,289 stores [p.4]."
        fixed, fixes, explained = tt.explain_numbers(answer, ["1289"], {"1288", "1000"})
        self.assertEqual((fixes, explained), ([], []))
        self.assertIn("1,289 stores", fixed)

    def test_operands_far_away_are_not_used(self):
        far = "A was 400 and B was 100 [p.1].\n\n" + "Filler.\n\n" * 5 + "The total is = 500."
        self.assertEqual(tt.explain_numbers(far, ["500"], {"400", "100"})[2], [])
        near = "A was 400 and B was 100 [p.1].\n\n" + "Filler.\n\n" * 3 + "The total is = 500."
        self.assertEqual(tt.explain_numbers(near, ["500"], {"400", "100"})[2], ["500"])

    def test_sums_keep_the_operands_decimals(self):
        self.assertEqual(tt.fill_calculations("[calc: 89.3 + 15.4]")[0], "89.3 + 15.4 = 104.7")


class RetryPromptTests(unittest.TestCase):
    def test_a_chart_page_read_as_none_is_asked_for_its_charts(self):
        from agent import document_planner as dp
        from agent.document_tools import Document, Page

        class Vision:
            def __init__(self):
                self.calls = []

            def describe(self, path, question):
                self.calls.append(question)
                return {"status": "ok", "answer": "[none]" if len(self.calls) == 1 else "| Q | Units |\n|---|---|\n| Q3 | 921 |", "text": ""}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = Page(number=1, text="921\n1,038\n-11.3%\nQ3 2025\nQ3 2026\n2,145\n+4.2%\n20,514\n22,817\n-10.1%", title="", images=1)
            document = Document(path=root / "deck.pdf", kind="pdf", pages=[page])
            vision = Vision()
            planner = dp.DocumentQuestionPlanner(None, type("R", (), {"vision": vision})(), root)
            planner_image = dp.page_image
            dp.page_image = lambda document, number, cache_dir: root / "p1.png"
            (root / "p1.png").write_bytes(b"")
            try:
                notes = planner._look(document, [1], "How many units?")
            finally:
                dp.page_image = planner_image
            self.assertIn("921", notes[1])
            self.assertIn("holds one or more charts", vision.calls[1])


class ChartPageTests(unittest.TestCase):
    def test_chart_labels_but_not_text_tables(self):
        from agent.document_tools import Page, is_chart_page

        bridge = Page(number=13, text="매출액\n46,721\n+658\n-3,435\n-685\n+1,851\n45,110\nQ3 2025\n환율\n물량", title="", images=0)
        bridge.drawings = 1
        self.assertTrue(is_chart_page(bridge))
        table = Page(number=12, text="매출액 46,721 49,215 45,110 -3.4%\n자동차 부문 36,715 36,832 33,058\n영업이익 2,537 2,851 2,677",
                     title="", images=0)
        table.drawings = 1
        self.assertFalse(is_chart_page(table))
        bridge.drawings = 0
        self.assertFalse(is_chart_page(bridge))  # no picture and no vector figure


class NotesCacheTests(unittest.TestCase):
    def test_a_chart_read_as_none_is_asked_again_and_readings_are_cached(self):
        from PIL import Image

        from agent import document_planner as dp
        from agent.document_tools import load_document

        class Vision:
            def __init__(self, *answers):
                self.answers, self.calls = list(answers), []

            def describe(self, path, question):
                self.calls.append(question)
                return {"status": "ok", "answer": self.answers.pop(0), "text": ""}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = [Image.new("RGB", (800, 450), (255, 255, 255)) for _ in range(2)]
            images[0].save(root / "charts.pdf", save_all=True, append_images=images[1:])
            document = load_document(root / "charts.pdf")
            vision = Vision("[none]", "| Quarter | Revenue |\n|---|---|\n| Q1 | 412.0 |")
            planner = dp.DocumentQuestionPlanner(None, type("R", (), {"vision": vision})(), root)
            notes = planner._look(document, [1], "What was Q1 revenue?")
            self.assertIn("412.0", notes[1])
            self.assertEqual(len(vision.calls), 2)
            # Run 45 (GC2): a picture page that is not a chart page is asked for every kind of content.
            self.assertIn("Its text layer is almost empty", vision.calls[1])
            self.assertIn("Equations", vision.calls[1])
            again = dp.DocumentQuestionPlanner(None, type("R", (), {"vision": Vision()})(), root)
            self.assertIn("412.0", again._look(document, [1], "What was Q1 revenue?")[1])  # from the cache


if __name__ == "__main__":
    unittest.main()
