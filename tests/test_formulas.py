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
        self.assertEqual(equation_refs("Compare equations (1) and (2)."), [1, 2])
        self.assertEqual(equation_refs("식 (3)과 (4)를 비교해 줘"), [3, 4])

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



class UnnumberedTests(unittest.TestCase):
    """Holdout Run 33, BS3: an unnumbered formula was rebuilt from the text layer, not read from the page."""

    PROSE = "The mother wavelet used in this work is the Ricker wavelet, defined as the second derivative of a"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        make_pdf(self.root / "paper.pdf", [[
            (self.PROSE, 40, 700), ("Gaussian function, and it is given by", 40, 686),
            ("psi = c + d * t", 250, 650),
            ("where c is a constant and the time t is measured in seconds from the start.", 40, 614),
            ("Figure 2: the score = a + b for each of the classes in the large test set", 40, 560),
            ("y = Ax + n      (1)", 250, 500),
        ]])
        self.document = load_document(self.root / "paper.pdf")

    def test_a_displayed_unnumbered_equation_is_found_with_its_text(self):
        spots = ft.display_formulas(self.document, 1)
        self.assertEqual(len(spots), 1)  # not the caption, not the numbered equation
        spot = spots[0]
        self.assertEqual(spot.number, 0)
        self.assertLessEqual(spot.band[0], 652)
        self.assertGreaterEqual(spot.band[1], 655)
        self.assertIn("given by", spot.before)
        self.assertIn("where c is a constant", spot.after)
        self.assertIn('right after the text "...', spot.target())

    def test_it_is_read_and_named_by_its_text(self):
        spot = ft.display_formulas(self.document, 1)[0]
        vision = FakeVision("$$ \\psi = c + d t $$", "$$\\psi=c+dt$$", "COMPLETE")
        reading = ft.read_spot(vision, self.root, self.document, spot, self.root / "cache")
        self.assertEqual(reading.status, "confirmed")
        self.assertIn("given by", vision.calls[0][1])
        self.assertNotEqual(vision.calls[0][0], vision.calls[1][0])
        from agent.document_planner import formula_block
        self.assertIn('[p.1, the unnumbered equation after "...', formula_block(reading))

    def test_the_planner_reads_it_for_a_formula_question(self):
        from agent import document_planner as dp

        vision = FakeVision("$$ \\psi = c + d t $$", "$$ \\psi = c + d t $$", "COMPLETE")
        events = []
        registry = type("R", (), {"vision": vision})()
        planner = dp.DocumentQuestionPlanner(FakeLLM(), registry, self.root, on_event=events.append)
        from agent.document_tools import split_passages

        passages = split_passages(self.document)
        readings, around = planner._read_displayed(self.document, "How is the Ricker wavelet defined?", passages, [1])
        self.assertEqual([r.latex for r in readings], ["\\psi = c + d t"])
        self.assertTrue(around)  # the passage next to it is given too
        self.assertTrue(any("unnumbered equation on p.1" in e for e in events))
        # no formula words, or no shared words: nothing is read
        self.assertEqual(planner._read_displayed(self.document, "What is the Ricker wavelet used for?", passages, [1]), ([], []))
        self.assertEqual(planner._read_displayed(self.document, "How is the loss defined?", passages, [1]), ([], []))

    def test_rare_words_decide_and_other_pages_count(self):
        # Run 39, UN1: "function" (common) chose the wrong formula over "PolyLoss" (rare);
        # UN2: the formula was on a page no chosen passage was on.
        from agent import document_planner as dp
        from agent.document_tools import load_document, split_passages

        filler = "The function of this part of the system is described in the text of this function section here."
        make_pdf(self.root / "two.pdf", [
            [(filler, 40, 740), (filler, 40, 726), ("A Gaussian function is used, given by", 40, 700),
             ("g = c + d * t", 250, 664), ("where the function g is smooth and the time t is measured in seconds.", 40, 628)],
            [(filler, 40, 740), ("The best results came with PolyLoss, which is", 40, 700),
             ("L = e + f * y", 250, 664), ("where y is the predicted probability of each of the classes here.", 40, 628)],
        ])
        document = load_document(self.root / "two.pdf")
        vision = FakeVision("$$ L = e + f y $$", "$$ L = e + f y $$", "COMPLETE", "$$ g = c + d t $$", "$$ g = c + d t $$", "COMPLETE")
        planner = dp.DocumentQuestionPlanner(FakeLLM(), type("R", (), {"vision": vision})(), self.root)
        readings, _ = planner._read_displayed(document, "How is the PolyLoss function defined?", split_passages(document), [1])
        self.assertEqual(readings[0].page, 2)  # the rare word wins, although p.1 holds the chosen passages
        self.assertEqual(readings[0].latex, "L = e + f y")

    def test_an_answer_about_another_formula_is_not_flagged(self):
        # Run 39, UN1: the answer wrote PolyLoss; the Ricker reading must not call it "changed".
        from agent import document_planner as dp

        vision = FakeVision("$$ \\psi = c + d t $$", "$$ \\psi = c + d t $$", "COMPLETE")
        planner = dp.DocumentQuestionPlanner(FakeLLM(), type("R", (), {"vision": vision})(), self.root)
        spot = ft.display_formulas(self.document, 1)[0]
        planner.formulas = [ft.read_spot(vision, self.root, self.document, spot, self.root / "cache")]
        answer = ("PolyLoss is $$ -\\sum_{n=1}^{k} y_i \\log(\\hat{y}_i) + \\epsilon (1 - \\hat{y}_i) $$ [p.1].")
        result = planner._finish(self.document, answer, [1], "", "How is PolyLoss defined?", False, 0.0)
        self.assertNotIn("differs from", result)
        self.assertIn('The unnumbered equation on p.1 (after "...', result)
        # a formula that does look like the reading but changes it is still flagged
        result = planner._finish(self.document, "It is $$ \\psi = c - d t^2 $$ [p.1].", [1], "", "How is psi defined?", False, 0.0)
        self.assertIn("differs from the unnumbered equation on p.1", result)


class TwoEquationTests(unittest.TestCase):
    def test_an_answer_that_writes_one_of_two_equations_is_not_flagged(self):
        import json
        from agent import document_planner as dp

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_pdf(root / "paper.pdf", [[("The model is", 72, 700), ("y = Ax + n,      (1)", 250, 660),
                                       ("and the estimate is", 72, 620), ("z = By - m      (2)", 250, 580)]])
        vision = FakeVision("$$ y = Ax + n $$", "$$ y = Ax + n $$", "COMPLETE",
                            "$$ z = By - m $$", "$$ z = By - m $$", "COMPLETE")
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [1]}), "Equation (1) is $$ y = Ax + n $$ [p.1].")
        registry = type("R", (), {"vision": vision})()
        answer = dp.DocumentQuestionPlanner(llm, registry, root).run("paper.pdf Compare equations (1) and (2).")
        self.assertNotIn("⚠", answer)
        llm = FakeLLM(json.dumps({"scope": "pages", "pages": [1]}), "Equation (2) is $$ z = By + m^2 $$ [p.1].")
        vision.answers = ["$$ y = Ax + n $$", "$$ y = Ax + n $$", "COMPLETE", "$$ z = By - m $$", "$$ z = By - m $$", "COMPLETE"]
        answer = dp.DocumentQuestionPlanner(llm, registry, root).run("paper.pdf Compare equations (1) and (2).")
        self.assertIn("differs from equation (2)", answer)
        self.assertNotIn("differs from equation (1)", answer)


if __name__ == "__main__":
    unittest.main()
