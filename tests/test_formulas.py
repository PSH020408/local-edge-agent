"""Offline tests for agent/formula_tools.py (no model needed)."""

import ctypes
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import formula_tools as ft  # noqa: E402
from agent.document_tools import load_document  # noqa: E402


def make_pdf(path: Path, pages: list[list[tuple[str, float, float]]]) -> None:
    """Pages of text lines (text, x, y) in Helvetica 12."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    pdf = pdfium.PdfDocument.new()
    for lines in pages:
        page = pdf.new_page(600, 800)
        for text, x, y in lines:
            obj = raw.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", ctypes.c_float(12))
            buffer = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
            raw.FPDFText_SetText(obj, ctypes.cast(buffer, ctypes.POINTER(raw.FPDF_WCHAR)))
            raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
            raw.FPDFPage_InsertObject(page.raw, obj)
        raw.FPDFPage_GenerateContent(page.raw)
        page.close()
    pdf.save(str(path))
    pdf.close()


class FakeVision:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def describe(self, path, question):
        self.calls.append((path, question))
        return {"status": "ok", "answer": self.answers.pop(0)}


class NormaliseTests(unittest.TestCase):
    def test_fonts_spacing_and_sizes_do_not_matter(self):
        a = r"\hat{x} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \lambda \|x - p\|_2^2"
        b = r"\hat{x}=\operatorname*{arg\,min}_{x}\left\| \mathbf{A} x-y\right\|_{2}^{2}+\lambda\left\|x-p\right\|_{2}^{2}"
        c = r"\hat{x} = \underset{x}{\arg\min} \|A x - y\|_2^2 + \lambda \|x - p\|_2^2 \quad (4)"
        self.assertEqual(ft.compare_latex(a, b)[0], "same")
        self.assertEqual(ft.compare_latex(a, c)[0], "same")

    def test_function_names_dots_and_mid_do_not_matter(self):
        # Dev run 1 (Run 34): these pairs were graded as different readings.
        self.assertEqual(ft.compare_latex(r"G_{\max} = (RM)^N", r"G_{\mathrm{max}} = (RM)^{N}")[0], "same")
        self.assertEqual(ft.compare_latex(r"\max_{i=1,\dots,N}", r"\max_{i=1,...,N}")[0], "same")
        self.assertEqual(ft.compare_latex(r"\Pr\{W \mid V\}", r"\Pr\{W | V\}")[0], "same")

    def test_line_breaks_and_alignment_do_not_matter(self):
        # Run 38, equation (5): "close" only because one reading broke the line with "\\".
        broken = r"\lim_{n\to\infty}m_n=\sum_{x\in S_X}x\frac{N_x}{n}\\=\sum_{x\in S_X}xP_X(x)=E[X]."
        whole = r"\lim_{n\to\infty}m_n=\sum_{x\in S_X}x\frac{N_x}{n}=\sum_{x\in S_X}xP_X(x)=E[X]."
        self.assertEqual(ft.compare_latex(broken, whole)[0], "same")
        aligned = r"\begin{aligned} y &= a + b \\ &= c \end{aligned}"
        self.assertEqual(ft.compare_latex(aligned, "y = a + b = c")[0], "same")

    def test_matrix_rows_still_count(self):
        self.assertNotEqual(ft.compare_latex(r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}",
                                             r"\begin{bmatrix} a & b & c & d \end{bmatrix}")[0], "same")

    def test_a_missing_term_is_a_difference(self):
        full = r"\frac{P}{BN_0}\left|\sqrt{\rho} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2"
        short = r"\frac{P}{BN_0}\left|\sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2"
        verdict, ratio, differences = ft.compare_latex(full, short)
        self.assertNotEqual(verdict, "same")
        self.assertTrue(any("rho" in d for d in differences))

    def test_swapped_operators_are_different(self):
        self.assertNotEqual(ft.compare_latex(r"A = MFS", r"A = SFM")[0], "same")

    def test_latex_is_taken_from_between_dollars(self):
        self.assertEqual(ft.extract_latex("Here it is:\n$$ y = Ax + n $$\nDone."), "y = Ax + n")

    def test_structure_problems(self):
        self.assertEqual(ft.check_structure(r"\frac{a}{b} + \left( x \right)"), [])
        self.assertIn("unbalanced braces", ft.check_structure(r"\frac{1}{2"))
        self.assertIn("parts marked unreadable", ft.check_structure(r"x = \unreadable + 1"))
        self.assertIn("\\left without \\right", ft.check_structure(r"\left( x )"))
        self.assertIn("a LaTeX document instead of an equation", ft.check_structure(r"\documentclass{article} x"))


class LocateAndReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        make_pdf(self.root / "paper.pdf", [
            [("The samples are modeled as", 72, 700), ("y = Ax + n,      (1)", 250, 660),
             ("where A is the forward operator.", 72, 620)],
            [("as shown in (1)", 72, 700), ("z = x + R(x)      (2)", 250, 650)],
        ])
        self.document = load_document(self.root / "paper.pdf")

    def test_a_multi_line_equation_is_cropped_whole(self):
        make_pdf(self.root / "multi.pdf", [[
            ("We obtain the bound", 72, 700), ("S = a + b", 200, 670), ("<= c + d      (5)", 200, 650),
            ("where the bound follows from the inequality.", 72, 610)]])
        spot = ft.find_equation(load_document(self.root / "multi.pdf"), 5)
        self.assertLessEqual(spot.band[0], 652)
        self.assertGreaterEqual(spot.band[1], 675)  # the line above the number belongs to the equation
        self.assertLess(spot.band[1], 700)          # the prose line does not

    def test_equation_numbers_are_found_in_page_order(self):
        spot = ft.find_equation(self.document, 1)
        self.assertEqual(spot.page, 1)  # not the in-text "(1)" at a line end on p.2
        self.assertEqual(ft.find_equation(self.document, 2).page, 2)
        self.assertIsNone(ft.find_equation(self.document, 9))

    def test_two_equal_readings_are_confirmed(self):
        vision = FakeVision("$$ y = \\mathcal{A}x + n $$", "$$y=Ax+n,$$", "COMPLETE")
        reading = ft.read_equation(vision, self.root, self.document, 1, self.root / "cache")
        self.assertEqual(reading.status, "confirmed")
        self.assertEqual(reading.page, 1)
        self.assertEqual(len(vision.calls), 3)  # two readings and the check
        self.assertNotEqual(vision.calls[0][0], vision.calls[1][0])  # two different crops
        self.assertIn("y = \\mathcal{A}x + n", vision.calls[2][1])
        self.assertIn("(1)", vision.calls[0][1])

    def test_different_readings_are_reported(self):
        vision = FakeVision("$$ y = Ax + n $$", "$$ y = Ax - n^2 + \\sum_{k} b_k $$", "COMPLETE")
        reading = ft.read_equation(vision, self.root, self.document, 1, self.root / "cache")
        self.assertEqual(reading.status, "disagree")
        self.assertTrue(reading.differences)

    def test_an_unusable_reading_leaves_one(self):
        vision = FakeVision("$$ y = \\frac{A}{ $$", "$$ y = Ax + n $$", "COMPLETE")
        reading = ft.read_equation(vision, self.root, self.document, 1, self.root / "cache")
        self.assertEqual(reading.status, "disagree")
        self.assertEqual(reading.latex, "y = Ax + n")
        self.assertTrue(reading.problems)

    def test_the_more_complete_reading_is_kept(self):
        # Run 35, (3): the second line of the equation was in one reading only.
        vision = FakeVision("$$ P = a + b, $$", "$$ P = a + b, \\quad D = E\\{d\\} $$", "COMPLETE")
        reading = ft.read_equation(vision, self.root, self.document, 1, self.root / "cache")
        self.assertIn("D = E", reading.latex)
        self.assertIn("the second reading has more", reading.differences[0])

    def test_a_failed_check_withdraws_the_confirmation(self):
        # Run 35, (55): both readings left out the constraint line.
        vision = FakeVision("$$ \\min_X f(X) $$", "$$\\min_X f(X)$$", "MISSING: the constraint s.t. g(X) = 0")
        reading = ft.read_equation(vision, self.root, self.document, 1, self.root / "cache")
        self.assertEqual(reading.status, "check_failed")
        self.assertIn("s.t.", reading.differences[-1])

    def test_a_missing_number_is_not_found(self):
        reading = ft.read_equation(FakeVision(), self.root, self.document, 7, self.root / "cache")
        self.assertEqual(reading.status, "not_found")



class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, format=None):
        self.calls.append({"messages": messages, "format": format})
        return {"message": {"role": "assistant", "content": self.replies.pop(0)}, "stats": {}}


class PlannerTests(unittest.TestCase):
    """Questions that name an equation get it read from the page image (Holdout Run 33: MR2, MR4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        make_pdf(self.root / "paper.pdf", [
            [("The samples are modeled as", 72, 700), ("y = Ax + n,      (1)", 250, 660),
             ("where A is the forward operator.", 72, 620)],
            [("Results", 72, 700), ("The error fell by 9 percent.", 72, 650)],
        ])
        self.events = []

    def planner(self, llm, vision):
        from agent import document_planner as dp

        registry = type("R", (), {"vision": vision})()
        return dp.DocumentQuestionPlanner(llm, registry, self.root, on_event=self.events.append)

    def test_equation_references_in_questions(self):
        from agent.document_planner import equation_refs

        self.assertEqual(equation_refs("Write equation (1) in LaTeX."), [1])
        self.assertEqual(equation_refs("식 (55)에서 ρ = 1이면?"), [55])
        self.assertEqual(equation_refs("수식 (3)과 Eq. (4)를 비교해 줘"), [3, 4])
        self.assertEqual(equation_refs("(31)번 식의 뜻은?"), [31])
        self.assertEqual(equation_refs("What was the error in 2023 (Table 1)?"), [])

    def test_a_named_equation_is_read_from_the_image_and_given_first(self):
        import json

        vision = FakeVision("$$ y = \\mathcal{A}x + n $$", "$$ y = Ax + n $$", "COMPLETE")
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [2]}), "It is $$ y = Ax + n $$ where A is the forward operator [p.1].")
        answer = self.planner(llm, vision).run("paper.pdf Write equation (1) and explain A.")
        context = llm.calls[1]["messages"][1]["content"]
        self.assertIn("equation (1), read twice from the page image; the readings agree", context)
        self.assertIn("where A is the forward operator", context)  # its page is given too
        self.assertIn("Equation (1) was read twice from the image of p.1: the readings agree.", answer)
        self.assertNotIn("⚠", answer)
        self.assertTrue(any("equation (1): p.1, confirmed" in e for e in self.events))

    def test_an_answer_that_changes_the_equation_is_flagged(self):
        import json

        vision = FakeVision("$$ y = Ax + n $$", "$$ y = Ax + n $$", "COMPLETE")
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [1]}), "It is $$ y = Ax - n^2 + \\sum_k b_k $$ [p.1].")
        answer = self.planner(llm, vision).run("paper.pdf Write equation (1).")
        self.assertIn("differs from equation (1)", answer)


class PartTests(unittest.TestCase):
    """Run 37, RA11: an answer that writes one side of the equation is not a changed equation."""

    READING = (r"\mathrm{SNR} = \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}"
               r"e^{-j2\pi f_c\tau_n}\right|^2 \leq \frac{P}{BN_0}\left|\sqrt{\rho} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2")

    def test_one_side_copied_exactly_is_a_part(self):
        bound = r"\mathrm{SNR} \leq \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2"
        self.assertEqual(ft.compare_latex(bound, self.READING)[0], "different")
        self.assertTrue(ft.is_part_of(bound, self.READING))

    def test_a_side_with_a_term_left_out_is_not(self):
        short = r"\mathrm{SNR} \leq \frac{P}{BN_0} \left| \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2"
        self.assertFalse(ft.is_part_of(short, self.READING))

    def test_parts_split_outside_braces_only(self):
        parts = ft.latex_parts(r"y = \sum_{i=1,\dots,N} x_i, \quad A = MFS")
        self.assertEqual(["".join(p) for p in parts], ["y", r"\sum_{i=1,\dots,N}x_i", "A", "MFS"])


if __name__ == "__main__":
    unittest.main()
