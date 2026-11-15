"""Formulas: find a numbered equation on a PDF page, read it twice from the page image, compare.

Why (Stage 4 holdouts): the PDF text layer scatters equations into symbols (fractions, sums and
exponents come out as separate lines of characters), and a whole-page reading by the vision model can
drop or mislabel an equation. A formula is therefore read from the page image only, twice, from two different crops
around its equation number, and code compares the two readings:

    confirmed  both readings are the same after normalisation (fonts, spacing, \\left/\\right)
    close      they differ in a few symbols; the differences are listed
    disagree   they differ more; the formula is reported as uncertain

Code also checks the structure of each reading (balanced braces and brackets, \\frac with two
arguments, \\left/\\right pairs). sympy's LaTeX parser was tried as a check and not used: on paper
formulas it drops parts silently (\\frac{N-\\tau}{N} X e^{...} parsed as (N - tau)/N).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .document_tools import Document

READ_PROMPT = """This image shows part of a page. Transcribe {target} into LaTeX.
Write only that equation between $$ and $$: no equation number, no explanation, no other equation.
Copy every symbol, subscript, superscript, exponent, bar, hat and bold letter exactly as printed. If a part cannot be read, write \\unreadable in its place."""

MARGINS = (2.5, 4.5)  # margin around the equation, in heights of its number: two different views
_NUMBER_AT_LINE_END = re.compile(r"\((\d{1,3})\)[ \t]*(?=\r?\n|$)")
_MATH_HINT = set("=+−-×·∑∏∫√≤≥≈∞∂∇αβγδεθλμνπρστφχψωΣΦΨΩ^_") | {chr(c) for c in range(0xF000, 0xF100)}


@dataclass
class EquationSpot:
    page: int          # 1-based page number
    number: int
    bottom: float      # PDF points, origin at the bottom left
    top: float
    page_height: float
    page_width: float
    math_nearby: bool = True
    column: tuple[float, float] = (0.0, 1.0)  # horizontal range to crop, as fractions of the width
    band: tuple[float, float] | None = None   # bottom, top of the whole displayed equation (points)
    before: str = ""   # unnumbered equations: the text just before it ("... is given by")
    after: str = ""    # and just after it ("where ... is ...")
    text: str = ""     # its own characters in the text layer (scattered, but words survive)

    def target(self) -> str:
        """How the reading prompts name this equation."""
        if self.number:
            return f"the equation numbered ({self.number})"
        if self.before:
            return f'the displayed equation that comes right after the text "...{self.before[-60:].strip()}"'
        return "the displayed equation in the middle of the image"


@dataclass
class FormulaReading:
    number: int
    page: int | None
    status: str                         # confirmed, close, disagree, check_failed, unreadable, not_found
    latex: str = ""
    readings: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    check: str = ""                     # the vision model's answer when asked to check the reading
    before: str = ""                    # unnumbered equations: the text just before it, to name it

    def name(self) -> str:
        return f"equation ({self.number})" if self.number else "the unnumbered equation"


# --- locating ---------------------------------------------------------------------------------

def _unit_index(text: str, index: int) -> int:
    """pdfium counts characters in UTF-16 units; Python counts code points."""
    return len(text[:index].encode("utf-16-le")) // 2


def _candidates(document: Document) -> dict[int, list[EquationSpot]]:
    """Every line-end "(n)" on every page, with its box."""
    import pypdfium2 as pdfium

    found: dict[int, list[EquationSpot]] = {}
    pdf = pdfium.PdfDocument(str(document.path))
    try:
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            textpage = page.get_textpage()
            count = textpage.count_chars()
            if count <= 0:
                continue
            text = textpage.get_text_range(0, count)
            width, height = page.get_size()
            boxes_on_page = _char_boxes(textpage, count)
            for match in _NUMBER_AT_LINE_END.finditer(text):
                first = _unit_index(text, match.start())
                last = _unit_index(text, match.end()) - 1
                boxes = [textpage.get_charbox(i) for i in range(first, last + 1)]
                before = text[max(0, match.start() - 160): match.start()]
                math_nearby = sum(1 for ch in before if ch in _MATH_HINT) >= 2
                spot = EquationSpot(page_index + 1, int(match.group(1)), min(b[1] for b in boxes),
                                    max(b[3] for b in boxes), height, width, math_nearby)
                spot.right = max(b[2] for b in boxes) / width  # type: ignore[attr-defined]
                h = max(spot.top - spot.bottom, 6.0)
                gutter = _gutter(boxes_on_page, width, spot.bottom - 20 * h, spot.top + 20 * h)
                if gutter is not None:
                    # A full-width band of a two-column page showed the other column's equation
                    # too ((11) next to (13)), so the crop keeps one column.
                    in_right = min(b[0] for b in boxes) > gutter * width
                    spot.column = (gutter - 0.01, 1.0) if in_right else (0.0, gutter + 0.01)
                spot.band = _equation_band(boxes_on_page, spot.bottom, spot.top, spot.column, width)
                found.setdefault(spot.number, []).append(spot)
    finally:
        pdf.close()
    return found


def _char_boxes(textpage, count: int) -> list[tuple[float, float, float, float, str]]:
    boxes = []
    for i in range(count):
        left, bottom, right, top = textpage.get_charbox(i)
        if right - left > 0 and top - bottom > 0:
            boxes.append((left, bottom, right, top, textpage.get_text_range(i, 1)))
    return boxes


def _gutter(boxes, width: float, low: float, high: float) -> float | None:
    """Where the gutter between two columns is, near the equation (heights low to high), as a
    fraction of the width; None for one column. A gutter is a 1%-wide strip between 45% and 55%
    of the width with far fewer characters than the strips around it.

    Dev run 1: sampling every third character and counting those that cross the exact middle
    took a one-column page for two columns, and the crop cut off the left half of (1) and (3).
    Only text near the equation counts, because a two-column page can hold a full-width table."""
    near = [b for b in boxes if low <= (b[1] + b[3]) / 2 <= high]
    if len(near) < 150:
        return None
    bins = [0] * 10
    for b in near:
        position = (b[0] + b[2]) / 2 / width
        if 0.45 <= position < 0.55:
            bins[int((position - 0.45) * 100)] += 1
    average = sum(bins) / len(bins)
    lowest = min(range(10), key=lambda k: bins[k])
    if average >= 4 and bins[lowest] <= max(1, 0.15 * average):
        return 0.45 + (lowest + 0.5) / 100
    return None


_PROSE = re.compile(r"[A-Za-z]{2,}[ ,;]+[a-z]{2,}[ ,;]+[a-z]{2,}[ ,;]+[a-z]{2,}")


def _equation_band(boxes, spot_bottom: float, spot_top: float, column: tuple[float, float], width: float) -> tuple[float, float]:
    """Vertical extent of the displayed equation around its number: neighbouring text lines are
    added while they are not prose (four words in a row) and not far away.

    Dev run 1: equations of two or three printed lines ((31), (3), (55)) were cut by a band of
    fixed height around the number, which sits on the last or the middle line."""
    h = max(spot_top - spot_bottom, 6.0)
    x0, x1 = column[0] * width, column[1] * width
    inside = sorted((b for b in boxes if x0 <= (b[0] + b[2]) / 2 <= x1), key=lambda b: -(b[1] + b[3]) / 2)
    lines: list[list] = []
    for b in inside:
        centre = (b[1] + b[3]) / 2
        if lines and abs(lines[-1][0] - centre) < 0.45 * h:
            lines[-1][1].append(b)
        else:
            lines.append([centre, [b]])

    def text_of(chars) -> str:
        chars = sorted(chars, key=lambda b: b[0])
        out, last = "", None
        for b in chars:
            if last is not None and b[0] - last > 0.25 * h:
                out += " "
            out += b[4]
            last = b[2]
        return out

    def extent(chars) -> tuple[float, float]:
        return min(b[1] for b in chars), max(b[3] for b in chars)

    centre = (spot_bottom + spot_top) / 2
    index = min(range(len(lines)), key=lambda i: abs(lines[i][0] - centre)) if lines else None
    if index is None:
        return spot_bottom, spot_top
    bottom, top = extent(lines[index][1])
    for step in (-1, 1):  # -1: lines above (higher y come first), 1: lines below
        i = index + step
        while 0 <= i < len(lines):
            line_bottom, line_top = extent(lines[i][1])
            gap = (line_bottom - top) if step == -1 else (bottom - line_top)
            if gap > 2.5 * h or _PROSE.search(text_of(lines[i][1])):
                break
            bottom, top = min(bottom, line_bottom), max(top, line_top)
            i += step
    return bottom, top


_INDEX_CACHE: dict[tuple, dict[int, EquationSpot]] = {}


def equation_index(document: Document) -> dict[int, EquationSpot]:
    """Equation number -> where it is. A number found more than once (an in-text "(29)" at a
    line end) is resolved by its neighbours: equations are numbered in page order, so (29) lies
    between the pages of (28) and (30). Then math on the lines before it, then the furthest right."""
    if document.kind != "pdf":
        return {}
    try:
        stat = document.path.stat()
        key = (str(document.path), stat.st_mtime, stat.st_size)
    except OSError:
        key = (str(document.path), 0, 0)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    candidates = _candidates(document)
    chosen = {n: spots[0] for n, spots in candidates.items() if len(spots) == 1}
    for number in sorted(n for n, spots in candidates.items() if len(spots) > 1):
        lower = max((chosen[n].page for n in chosen if n < number), default=1)
        upper = min((chosen[n].page for n in chosen if n > number), default=len(document.pages))
        def score(spot: EquationSpot) -> tuple:
            inside = lower <= spot.page <= upper
            return (inside, spot.math_nearby, getattr(spot, "right", 0.0))
        chosen[number] = max(candidates[number], key=score)
    _INDEX_CACHE[key] = chosen
    return chosen


def find_equation(document: Document, number: int) -> EquationSpot | None:
    """Where equation (number) is, or None."""
    return equation_index(document).get(number)


_RELATION_CHARS = set("=≤≥≈≜∝<>")
_DISPLAY_MATH = (set("+−×·∑∏∫√≤≥≈∞∂∇∆Δϵ") | set("αβγδεθλμνπρστφχψωΣΦΨΩ")
                 | {chr(c) for c in range(0xF000, 0xF100)})
_DISPLAY_CACHE: dict[tuple, list[EquationSpot]] = {}


def _text_lines(boxes, x0: float, x1: float) -> list[tuple[float, list, float]]:
    """Characters whose centre lies between x0 and x1, grouped into lines from the top down:
    (centre height, characters left to right, character height)."""
    inside = sorted((b for b in boxes if x0 <= (b[0] + b[2]) / 2 <= x1), key=lambda b: -(b[1] + b[3]) / 2)
    lines: list[list] = []
    for b in inside:
        centre, height = (b[1] + b[3]) / 2, max(b[3] - b[1], 4.0)
        if lines and abs(lines[-1][0] - centre) < 0.45 * max(lines[-1][2], height):
            lines[-1][1].append(b)
        else:
            lines.append([centre, [b], height])
    for line in lines:
        line[1].sort(key=lambda b: b[0])
    return [tuple(line) for line in lines]


def _line_text(chars, height: float) -> str:
    out, last = "", None
    for b in chars:
        if last is not None and b[0] - last > 0.25 * height:
            out += " "
        out += b[4]
        last = b[2]
    return out


def display_formulas(document: Document, page_number: int) -> list[EquationSpot]:
    """Displayed equations without a number on a PDF page, each with the text around it.

    Holdout Run 33, BS3: the Ricker wavelet's formula has no number, so the answer rebuilt it from
    the text layer's scattered characters and changed the printed exponent. A displayed equation is a run of lines, set in from both
    edges of its column, that are not prose, not a figure or table caption, and together hold a
    relation (=, ≤, ≈ ...) and at least one other math symbol. Runs near a numbered equation belong
    to it and are left out (they are read through their number)."""
    import pypdfium2 as pdfium

    if document.kind != "pdf" or not 1 <= page_number <= len(document.pages):
        return []
    key = (str(document.path), page_number)
    if key in _DISPLAY_CACHE:
        return _DISPLAY_CACHE[key]
    pdf = pdfium.PdfDocument(str(document.path))
    try:
        page = pdf[page_number - 1]
        width, height = page.get_size()
        textpage = page.get_textpage()
        boxes = _char_boxes(textpage, textpage.count_chars())
    finally:
        pdf.close()
    numbered = [s for s in equation_index(document).values() if s.page == page_number]
    gutter = _gutter(boxes, width, 0.0, height)
    columns = [(0.0, 1.0)] if gutter is None else [(0.0, gutter), (gutter, 1.0)]
    spots: list[EquationSpot] = []
    for column in columns:
        lines = _text_lines(boxes, column[0] * width, column[1] * width)
        if not lines:
            continue
        left = min(c[1][0][0] for c in lines)
        right = max(c[1][-1][2] for c in lines)
        span = max(right - left, 1.0)
        texts = [_line_text(chars, h) for _, chars, h in lines]

        def displayed(i: int) -> bool:
            _, chars, _ = lines[i]
            text = texts[i]
            return (chars[0][0] >= left + 0.12 * span and chars[-1][2] <= right - 0.06 * span
                    and not _PROSE.search(text) and bool(re.search(r"[^\s,.;]", text))
                    and not re.match(r"\s*(?:fig(?:ure)?|table)\b", text, re.IGNORECASE))

        i = 0
        while i < len(lines):
            if not displayed(i):
                i += 1
                continue
            j = i
            while j + 1 < len(lines) and displayed(j + 1) and lines[j][0] - lines[j + 1][0] < 2.5 * lines[j][2]:
                j += 1
            text = " ".join(texts[i:j + 1])
            if any(ch in _RELATION_CHARS for ch in text) and any(ch in _DISPLAY_MATH for ch in text):
                chars = [b for k in range(i, j + 1) for b in lines[k][1]]
                low, high = min(b[1] for b in chars), max(b[3] for b in chars)
                h = sorted(lines[k][2] for k in range(i, j + 1))[(j - i) // 2]
                near_number = any(s.page == page_number and (s.band or (s.bottom, s.top))[0] - 2 * h <= high
                                  and low <= (s.band or (s.bottom, s.top))[1] + 2 * h for s in numbered)
                if not near_number:
                    centre = (low + high) / 2
                    wordy = [k for k in range(len(texts)) if re.search(r"[A-Za-z]{3}", texts[k])]
                    before = " ".join(texts[k] for k in [k for k in wordy if k < i][-2:])
                    after = " ".join(texts[k] for k in [k for k in wordy if k > j][:2])
                    spots.append(EquationSpot(page_number, 0, centre - h / 2, centre + h / 2, height, width,
                                              True, column, (low, high), before[-160:], after[:200], text))
            i = j + 1
    _DISPLAY_CACHE[key] = spots
    return spots


def crop_equation(document: Document, spot: EquationSpot, margin: float, out_dir: Path) -> Path:
    """Render a full-width band of the page around the equation number."""
    import pypdfium2 as pdfium

    line = max(spot.top - spot.bottom, 6.0)
    low, high = spot.band or (spot.bottom, spot.top)
    # at least `margin` heights around the number, and the whole equation plus a margin around it
    band_top = min(spot.page_height, max(spot.top + margin * line, high + (margin - 1.5) * line))
    band_bottom = max(0.0, min(spot.bottom - margin * line, low - (margin - 1.5) * line))
    scale = max(2.0, 1600 / (spot.page_width * (spot.column[1] - spot.column[0])))
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"eq{spot.number}" if spot.number else f"p{spot.page}_y{int(high)}"
    out = out_dir / f"{document.path.stem}_{name}_m{margin:g}.png"
    pdf = pdfium.PdfDocument(str(document.path))
    try:
        page = pdf[spot.page - 1]
        left, right = spot.column[0] * spot.page_width, (1 - spot.column[1]) * spot.page_width
        crop = (left, band_bottom, right, spot.page_height - band_top)  # amounts to remove from each side
        page.render(scale=scale, crop=crop).to_pil().save(out)
    finally:
        pdf.close()
    return out


# --- comparing --------------------------------------------------------------------------------

_STYLE = r"mathrm|mathbf|mathit|mathcal|mathsf|mathtt|mathbb|mathscr|mathfrak|boldsymbol|bm|text|textrm|textbf|textit|operatorname"
_DROP = re.compile(
    r"\\(?:limits|nolimits|left|right|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr|big|Big|bigg|Bigg|displaystyle|textstyle)(?![A-Za-z])"
    r"|\\[,;:! ]|\\q?quad(?![A-Za-z])|~"
)
_RENAME = {
    r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\leq": r"\le", r"\geq": r"\ge", r"\neq": r"\ne",
    r"\lVert": r"\|", r"\rVert": r"\|", r"\Vert": r"\|", r"\lvert": "|", r"\rvert": "|", r"\vert": "|",
    r"\to": r"\rightarrow", r"\overline": r"\bar", r"\widehat": r"\hat", r"\widetilde": r"\tilde",
    r"\ldots": r"\dots", r"\cdots": r"\dots", r"\argmin": "argmin", r"\argmax": "argmax", r"\ast": "*", r"\prime": "'", r"\varepsilon": r"\epsilon", r"\varphi": r"\phi",
    "−": "-", "×": r"\times", "·": r"\cdot",
}


def extract_latex(answer: str) -> str:
    """The equation between $$ ... $$ (or \\[ \\]); otherwise the whole answer."""
    for pattern in (r"\$\$(.+?)\$\$", r"\\\[(.+?)\\\]", r"\$(.+?)\$"):
        found = re.search(pattern, answer, re.S)
        if found:
            return found.group(1).strip()
    return answer.strip()


def normalize_latex(latex: str) -> str:
    """A form for comparing two readings: fonts, sizes, spacing and the equation number removed."""
    text = extract_latex(latex)
    text = re.sub(r"\\(?:tag|label)\{[^{}]*\}", "", text)
    text = re.sub(r"\(\s*\d{1,3}\s*\)\s*$", "", text.strip())
    # Run 38, equation (5): one reading broke the lines with "\\", the other did not. Line breaks and
    # alignment marks only lay the equation out, except inside a matrix or cases, where they separate
    # entries (kept there as a "⏎" token, so "\\ " is not taken for a spacing command below).
    text = re.sub(r"\\(?:begin|end)\{(?:aligned|align\*?|split|gathered|gather\*?|eqnarray\*?|multline\*?)\}", "", text)
    in_grid = re.search(r"\\begin\{(?:[pbvBV]?matrix|array|cases)\}", text)
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", " ⏎ " if in_grid else " ", text)
    if not in_grid:
        text = re.sub(r"(?<!\\)&", "", text)
    text = _DROP.sub("", text)
    for old, new in sorted(_RENAME.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(re.escape(old) + r"(?![A-Za-z])", lambda _m, new=new: new, text) if old.startswith("\\") else text.replace(old, new)
    for _ in range(4):  # nested styles: \mathbf{\mathrm{x}}
        text = re.sub(rf"\\(?:{_STYLE}|mathop)\*?\s*\{{([^{{}}]*)\}}", r"\1", text)
        text = re.sub(r"\\underset\{([^{}]*)\}\{([^{}]*)\}", r"\2_{\1}", text)  # \underset{x}{\arg\min}
    text = re.sub(rf"\\(?:{_STYLE})(?![A-Za-z])\s*(\\?[A-Za-z])", r"\1", text)
    text = re.sub(r"\\arg\s*\\?(min|max)", r"arg\1", text)  # \arg\min, \operatorname*{arg min}
    # Dev run 1: G_{\max} and G_{\mathrm{max}}, \ldots and "...", \mid and | were graded as different.
    text = re.sub(r"\\(max|min|log|ln|exp|sin|cos|tan|lim|det|Pr|sup|inf|arg)(?![A-Za-z])", r"\1", text)
    text = text.replace("...", "\\dots").replace("\\mid", "|")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"([_^])\{(\\?[A-Za-z0-9]|\\[A-Za-z]+)\}", r"\1\2", text)  # _{n} -> _n, ^{2} -> ^2
    text = text.rstrip(".,;")
    return text


_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|[A-Za-z]|\d|\S")


def latex_tokens(latex: str) -> list[str]:
    return _TOKEN.findall(normalize_latex(latex))


def compare_latex(first: str, second: str) -> tuple[str, float, list[str]]:
    """same / close / different, the token similarity, and the differing pieces."""
    a, b = latex_tokens(first), latex_tokens(second)
    if a == b:
        return "same", 1.0, []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    differences = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            differences.append(f"{''.join(a[i1:i2]) or '∅'} ↔ {''.join(b[j1:j2]) or '∅'}")
    ratio = matcher.ratio()
    return ("close" if ratio >= 0.9 else "different"), round(ratio, 3), differences[:6]


_RELATIONS = {"=", "<", ">", "\\le", "\\ge", "\\ne", "\\approx", "\\triangleq", "\\equiv", "\\propto", ","}


def latex_parts(latex: str) -> list[list[str]]:
    """The tokens of an equation split at relations and commas outside braces: the parts of
    "SNR = a ≤ b, x = y" are SNR, a, b, x, y."""
    parts, current, depth = [], [], 0
    for token in latex_tokens(latex):
        depth += token == "{"
        depth -= token == "}"
        if depth == 0 and token in _RELATIONS:
            parts.append(current)
            current = []
        else:
            current.append(token)
    return [p for p in parts + [current] if p]


def is_part_of(written: str, reading: str) -> bool:
    """True when every part of the written equation is a part of the reading, copied exactly.

    Run 37, RA11: the question asked for the upper bound of equation (31), the answer wrote
    "SNR ≤ bound" and left out the middle expression, and the check called it a different equation.
    Parts of one or two tokens ("SNR", "x") are not compared; the rest must be equal, not just close,
    so a part with a term left out (the √ρ of Run 32) still counts as changed."""
    written_parts = [p for p in latex_parts(written) if len(p) > 2]
    reading_parts = latex_parts(reading)
    return bool(written_parts) and all(p in reading_parts for p in written_parts)


def check_structure(latex: str) -> list[str]:
    """Problems that make a reading unusable, found without understanding the mathematics."""
    text = extract_latex(latex)
    problems = []
    if not text.strip():
        return ["empty"]
    if "\\unreadable" in text:
        problems.append("parts marked unreadable")
    if re.search(r"\\(?:documentclass|begin\{document\}|usepackage)", text):
        problems.append("a LaTeX document instead of an equation")
    stripped = re.sub(r"\\[{}]", "", text)
    if stripped.count("{") != stripped.count("}"):
        problems.append("unbalanced braces")
    if len(re.findall(r"\\left(?![A-Za-z])", text)) != len(re.findall(r"\\right(?![A-Za-z])", text)):
        problems.append("\\left without \\right")
    plain = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)[lr]?(?![A-Za-z])", "", stripped)
    plain = re.sub(r"\\[A-Za-z]+", "", plain)
    if plain.count("(") != plain.count(")"):
        problems.append("unbalanced parentheses")
    for frac in re.finditer(r"\\[dt]?frac(?![A-Za-z])", text):
        rest = text[frac.end():].lstrip()
        groups = 0
        while rest.startswith("{") and groups < 2:
            depth = 0
            for k, ch in enumerate(rest):
                depth += ch == "{"
                depth -= ch == "}"
                if depth == 0:
                    rest = rest[k + 1:].lstrip()
                    groups += 1
                    break
            else:
                break
        if groups < 2 and not re.match(r"[A-Za-z0-9]{1,2}|\\[A-Za-z]+", rest):
            problems.append("\\frac without two arguments")
            break
    return problems


# --- reading ----------------------------------------------------------------------------------

def _only_additions(shorter: str, longer: str) -> bool:
    """True when `longer` is `shorter` with parts added and nothing changed (a reading that kept
    a line or term the other one left out)."""
    a, b = latex_tokens(shorter), latex_tokens(longer)
    ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    return len(b) > len(a) and all(tag in ("equal", "insert") for tag, *_ in ops)


VERIFY_PROMPT = """The image shows {target}. Below is a LaTeX transcription of it.
Compare them part by part: every line, term, fraction, subscript, superscript and constraint.
If the transcription contains everything in the image, answer exactly: COMPLETE
Otherwise answer: MISSING: and name the parts of the image that the transcription leaves out or gets wrong.

Transcription:
$$ {latex} $$"""


def read_equation(vision, workspace: Path, document: Document, number: int, cache_dir: Path,
                  verify: bool = True) -> FormulaReading:
    """Find equation (number), read it from two crops, compare the readings, and (verify) ask the
    vision model to check the chosen reading against the larger crop.

    Run 35: the two readings agreed on a transcription that left out a constraint line (55) or a
    middle term (27): agreement cannot catch what both readings leave out, so a third call looks
    at the image and the transcription together."""
    spot = find_equation(document, number)
    if spot is None:
        return FormulaReading(number, None, "not_found")
    return read_spot(vision, workspace, document, spot, cache_dir, verify)


def read_spot(vision, workspace: Path, document: Document, spot: EquationSpot, cache_dir: Path,
              verify: bool = True) -> FormulaReading:
    """Read the equation at `spot` (numbered or not) from two crops, compare, and check."""
    number = spot.number
    readings, images = [], []
    for margin in MARGINS:
        image = crop_equation(document, spot, margin, cache_dir)
        relative = str(image.resolve().relative_to(workspace.resolve()))
        result = vision.describe(relative, READ_PROMPT.format(target=spot.target()))
        readings.append(extract_latex(result.get("answer", "")) if result.get("status") == "ok" else "")
        images.append(relative)
    problems = [f"reading {i + 1}: {p}" for i, r in enumerate(readings) for p in check_structure(r)]
    usable = [r for r in readings if r and not check_structure(r)]
    if not usable:
        return FormulaReading(number, spot.page, "unreadable", "", readings, [], problems, images, before=spot.before)
    if len(usable) == 1:
        reading = FormulaReading(number, spot.page, "disagree", usable[0], readings, ["only one reading is usable"], problems, images)
    else:
        verdict, _, differences = compare_latex(usable[0], usable[1])
        status = {"same": "confirmed", "close": "close", "different": "disagree"}[verdict]
        chosen = usable[0]
        # Run 35, (3): one reading kept the second line of the equation, the other left it out.
        if verdict != "same":
            if _only_additions(usable[0], usable[1]):
                chosen = usable[1]
                differences = ["the second reading has more: " + "; ".join(differences)]
            elif _only_additions(usable[1], usable[0]):
                differences = ["the first reading has more: " + "; ".join(differences)]
        reading = FormulaReading(number, spot.page, status, chosen, readings, differences, problems, images)
    reading.before = spot.before
    if verify and reading.latex:
        result = vision.describe(images[-1], VERIFY_PROMPT.format(target=spot.target().replace("the equation numbered", "equation"), latex=reading.latex))
        answer = (result.get("answer", "") if result.get("status") == "ok" else "").strip()
        reading.check = answer[:300]
        if answer and not answer.upper().startswith("COMPLETE"):
            reading.differences.append("check against the image: " + answer[:200])
            if reading.status == "confirmed":
                reading.status = "check_failed"
    return reading
