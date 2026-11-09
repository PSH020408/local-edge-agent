"""Reading documents (PDF, PowerPoint) page by page.

Most study material already contains its text as data, so it is extracted exactly, without a
vision model. Two things do not survive text extraction and are flagged per page instead:

- equations: PDF text from equation objects and LaTeX comes out as scattered symbols
  (1/n Σ becomes "1X"), so pages with equations are rendered and read by the vision model
- figures: pictures and diagrams have no text at all

Superscripts lose their position in the text layer ("10²" comes out as "102"), so raised digits
are found from the character boxes and written with a caret ("10^2").

Libraries: pypdfium2 (PDF text and rendering), python-pptx (slides, tables, notes).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DOCUMENT_EXTENSIONS = {".pdf", ".pptx"}
_MATH_CHARS = set("=∑Σ∫√π≤≥±∞∂∆θτεαβγδλμσφωΩ^_")


@dataclass
class Page:
    number: int  # 1-based position in the file; the number used in citations
    text: str
    title: str = ""
    images: int = 0
    math: bool = False
    label: str = ""  # page number printed on the page, when it differs from the position
    drawings: int = 0  # figures drawn as vector graphics (papers only, see _mark_paper_pages)

    @property
    def needs_vision(self) -> bool:
        """Equations are garbled in extracted text; figure-only pages have little text."""
        return self.math or (self.images > 0 and len(self.text) < 400)


@dataclass
class Document:
    path: Path
    kind: str  # "pdf" or "pptx"
    pages: list[Page] = field(default_factory=list)

    def page(self, number: int) -> Page | None:
        return self.pages[number - 1] if 1 <= number <= len(self.pages) else None

    @property
    def dense(self) -> bool:
        """A paper or report: PDF pages full of running text, not slides.

        Holdout Run 29: page selection by title works for slides (one topic per page, under
        400 characters) and fails for papers (5,000 characters, the first line in mid-sentence).
        """
        if self.kind != "pdf" or not self.pages:
            return False
        lengths = sorted(len(p.text) for p in self.pages)
        return lengths[len(lengths) // 2] >= DENSE_PAGE_CHARS

    def summary(self) -> str:
        math = sum(1 for p in self.pages if p.math)
        figures = sum(1 for p in self.pages if p.images or p.drawings)
        kind = ", read as a paper" if self.dense else ""
        return f"{len(self.pages)} page(s), {math} with equations, {figures} with figures{kind}"


DENSE_PAGE_CHARS = 1500   # median characters per page from which a PDF is read as a paper
_VECTOR_PATHS = 50        # drawn lines and shapes on a page from which it holds a vector figure
_FIGURE_CAPTION = re.compile(r"^(?:Figure|FIGURE|Fig\.)\s*\d+\s*[:.]")
_EQUATION_NUMBER = re.compile(r"(?:^|\s)\((\d{1,2})\)$")


def _numbered_equation(lines: list[str]) -> bool:
    """A line ending in "(1)", "(2)" next to an "=", math symbols or scattered one-letter lines:
    a displayed equation. Word's Symbol font comes out as private-use characters (U+F03D is =)."""
    for i, line in enumerate(lines):
        if _EQUATION_NUMBER.search(line):
            before = lines[max(0, i - 3): i]
            near = " ".join(before + [line])
            symbols = sum(1 for ch in near if ch in _MATH_CHARS or "\uf000" <= ch <= "\uf0ff")
            scattered = sum(1 for previous in before if len(previous.strip()) <= 3)
            if "=" in near or symbols >= 2 or scattered >= 2:
                return True
    return False


def _mark_paper_pages(document: "Document", paths: list[int]) -> None:
    """In papers, flag pages with vector figures and numbered equations.

    Holdout Run 29: both papers drew their plots as vector graphics (no image objects) and had
    too few short lines for looks_like_math, so no page was marked and no question about a
    figure or an equation reached the vision model. Slides keep the old rules: these are
    applied only to dense documents.
    """
    if not document.dense:
        return
    for page, count in zip(document.pages, paths):
        lines = page.text.splitlines()
        captions = sum(1 for line in lines if _FIGURE_CAPTION.match(line))
        if captions or count >= _VECTOR_PATHS:
            page.drawings = max(1, captions)
        if _numbered_equation(lines):
            page.math = True


def looks_like_math(text: str) -> bool:
    """Garbled equations: many one- or two-character lines and mathematical symbols."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        return False
    short = sum(1 for line in lines if len(line) <= 2)
    symbols = sum(1 for ch in text if ch in _MATH_CHARS)
    return short >= 8 and short / len(lines) >= 0.2 and symbols >= 3


def _remove_repeated_lines(pages: list[list[str]]) -> list[list[str]]:
    """Drop headers and footers: lines that appear on at least 40% of the pages (4 pages or more)."""
    if len(pages) < 4:
        return pages
    counts = Counter(line for lines in pages for line in set(lines))
    repeated = {line for line, n in counts.items() if n >= max(3, 0.4 * len(pages)) and len(line) > 3}
    return [[line for line in lines if line not in repeated] for lines in pages]


def _finish(lines: list[str], number: int, images: int, detect_math: bool = True) -> Page:
    label = ""
    if lines and re.fullmatch(r"\d{1,4}", lines[-1]):
        # A printed page number at the end of a slide ("12" on the 13th page).
        label = lines.pop()
        if label == str(number):
            label = ""
    text = "\n".join(lines)
    title = next((line for line in lines if len(line) > 2), "")[:100]
    return Page(number=number, text=text, title=title, images=images,
                math=detect_math and looks_like_math(text), label=label)


def _raised_digits(textpage, count: int) -> set[int]:
    """Indices of digits set as superscripts: the bottom raised by over a quarter of the height of
    the character before it, the top at most half a height above it, and the glyph smaller."""
    raised, base = set(), None
    for i in range(count):
        ch = textpage.get_text_range(i, 1)
        if not ch or ch.isspace():
            continue
        left, bottom, right, top = textpage.get_charbox(i)
        if ch.isdigit() and base is not None:
            b_left, b_bottom, b_right, b_top = base
            height = b_top - b_bottom
            # Run 29: "10^12" in a LaTeX paper rises 0.3 heights above the "0", so up to 0.5.
            if (height > 0 and bottom - b_bottom > 0.25 * height and top <= b_top + 0.5 * height
                    and top - bottom < 0.85 * height and b_left <= left < b_right + height):
                raised.add(i)
                continue
        base = (left, bottom, right, top) if ch.isalnum() or ch in ")]" else None
    return raised


def _pdf_page_text(textpage) -> str:
    """Page text with superscript digits marked by "^". Pages without any keep pdfium's own text."""
    count = textpage.count_chars()
    raised = _raised_digits(textpage, count) if count > 0 else set()
    if not raised:
        return textpage.get_text_bounded()
    # Indices count UTF-16 units (math italic letters take two), so the text is rebuilt in units.
    data = textpage.get_text_range(0, count).encode("utf-16-le")
    units = [data[k:k + 2] for k in range(0, len(data), 2)]
    out: list[bytes] = []
    for i, unit in enumerate(units):
        if i in raised and i - 1 not in raised:
            while out and out[-1] == " ".encode("utf-16-le"):
                out.pop()  # pdfium puts a space before the raised digit
            out.append("^".encode("utf-16-le"))
        out.append(unit)
    return b"".join(out).decode("utf-16-le", errors="replace")


def load_pdf(path: Path) -> Document:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    pdf = pdfium.PdfDocument(str(path))
    raw_pages, images, paths = [], [], []
    try:
        for page in pdf:
            paths.append(sum(1 for _ in page.get_objects(filter=(raw.FPDF_PAGEOBJ_PATH,), max_depth=3)))
            # pdfium marks a word hyphenated at a line end with \x02 ("au\x02dio"); join it again.
            text = re.sub(r"\x02\n?", "", _pdf_page_text(page.get_textpage()).replace("\r", ""))
            raw_pages.append([line.strip() for line in text.splitlines() if line.strip()])
            images.append([
                tuple(round(v) for v in obj.get_bounds())
                for obj in page.get_objects(filter=(raw.FPDF_PAGEOBJ_IMAGE,), max_depth=2)
            ])
    finally:
        pdf.close()
    # A picture at the same place on many pages is part of the template (a footer bar, a logo),
    # not a figure: the OFDM slides have one on every page.
    counts = Counter(box for boxes in images for box in set(boxes))
    template = {box for box, n in counts.items() if len(images) >= 4 and n >= max(3, 0.4 * len(images))}
    figures = [sum(1 for box in boxes if box not in template) for boxes in images]
    cleaned = _remove_repeated_lines(raw_pages)
    document = Document(path, "pdf", [_finish(lines, i + 1, figures[i]) for i, lines in enumerate(cleaned)])
    _mark_paper_pages(document, paths)
    return document


def _pptx_lines(shapes, lines: list[str]) -> int:
    """Collect text and table rows from slide shapes (groups included); return the picture count."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    pictures = 0
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            pictures += _pptx_lines(shape.shapes, lines)
            continue
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            pictures += 1
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
        elif getattr(shape, "has_text_frame", False) and shape.has_text_frame:
            lines.extend(line.strip() for line in shape.text_frame.text.splitlines() if line.strip())
    return pictures


def load_pptx(path: Path) -> Document:
    from pptx import Presentation

    presentation = Presentation(str(path))
    raw_pages, pictures = [], []
    for slide in presentation.slides:
        lines: list[str] = []
        pictures.append(_pptx_lines(slide.shapes, lines))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"[speaker notes] {notes}")
        raw_pages.append(lines)
    cleaned = _remove_repeated_lines(raw_pages)
    # Equations in slides are not extracted as text at all, and numbered diagram labels
    # ("1", "2", ...) look like garbled math, so math detection is for PDF only.
    return Document(path, "pptx", [_finish(lines, i + 1, pictures[i], detect_math=False) for i, lines in enumerate(cleaned)])


_cache: dict[tuple[str, float], Document] = {}


def load_document(path: Path) -> Document:
    key = (str(path), path.stat().st_mtime)
    if key not in _cache:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            _cache[key] = load_pdf(path)
        elif suffix == ".pptx":
            _cache[key] = load_pptx(path)
        else:
            raise ValueError(f"unsupported document type '{suffix}'; supported: {', '.join(sorted(DOCUMENT_EXTENSIONS))}")
    return _cache[key]


def page_image(document: Document, number: int, out_dir: Path) -> Path | None:
    """An image of one page for the vision model.

    PDF: the page is rendered (about 1440 px wide for a slide). PowerPoint cannot be rendered
    without an office suite, so the largest picture on the slide is used instead.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", document.path.stem)[:60]
    if document.kind == "pdf":
        target = out_dir / f"{stem}_p{number}.png"
        if not target.exists():
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(document.path))
            try:
                page = pdf[number - 1]
                width = page.get_size()[0]
                image = page.render(scale=max(1.0, 1440 / width)).to_pil()
                image.save(target)
            finally:
                pdf.close()
        return target

    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    slide = Presentation(str(document.path)).slides[number - 1]
    best = None
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            size = shape.width * shape.height
            if best is None or size > best[0]:
                best = (size, shape.image)
    if best is None:
        return None
    target = out_dir / f"{stem}_p{number}.{best[1].ext}"
    if not target.exists():
        target.write_bytes(best[1].blob)
    return target


# --- finding pages ---------------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "is", "are", "of", "and", "or", "to", "in", "on", "what", "which", "how", "why", "this",
    "that", "it", "for", "with", "explain", "describe", "tell", "me", "about", "document", "page", "pages",
    "뭐야", "뭐", "알려", "줘", "설명해", "설명", "어떻게", "왜", "무엇", "있어", "해", "이", "그", "강의", "문서",
}


_GREEK = re.compile(r"[α-ωΑ-Ωϑϕϵϱς]")
# a displayed equation's number at a line end, or a reference to one in a question
_EQUATION_NUMBER_TOKEN = re.compile(
    r"\((\d{1,3})\)[ \t]*$|(?:equations?|eqs?\.|eqn\.?|수식|공식|식)\s*\(\s*(\d{1,3})\s*\)", re.M | re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z0-9]+|[가-힣]+", text.lower()) if w not in _STOP]
    tokens = []
    for word in words:
        if re.fullmatch(r"[가-힣]+", word) and len(word) > 2:
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))  # Korean: two-syllable pieces
        elif len(word) > 1:
            tokens.append(word)
    # Run 33 (MR4): a question about φ, α and ᾱ in equation (3) had no searchable words left.
    tokens.extend(ch.lower() for ch in _GREEK.findall(text))
    tokens.extend(f"eq{a or b}" for a, b in _EQUATION_NUMBER_TOKEN.findall(text))
    return tokens


def rank_pages(document: Document, query: str) -> list[tuple[int, float]]:
    """Pages by keyword overlap with the query (titles count double), best first."""
    import math

    page_tokens = [set(_tokens(p.text)) | set(_tokens(p.title)) for p in document.pages]
    title_tokens = [set(_tokens(p.title)) for p in document.pages]
    n = len(document.pages)
    scores = []
    for i, tokens in enumerate(page_tokens):
        score = 0.0
        for token in set(_tokens(query)):
            if token in tokens:
                df = sum(1 for t in page_tokens if token in t)
                weight = math.log(1 + n / df)
                score += weight * (2 if token in title_tokens[i] else 1)
        scores.append((i + 1, round(score, 3)))
    return sorted(scores, key=lambda s: -s[1])


_PAGE_REF = re.compile(
    r"(?:p\.?\s*|page\s*|slide\s*|페이지\s*|슬라이드\s*)(\d{1,4})|(\d{1,4})\s*(?:페이지|쪽|번\s*슬라이드|슬라이드)",
    re.IGNORECASE,
)


def page_references(question: str, document: Document) -> list[int]:
    numbers = []
    for match in _PAGE_REF.finditer(question):
        number = int(match.group(1) or match.group(2))
        if document.page(number) and number not in numbers:
            numbers.append(number)
    return numbers


# --- passages: search inside papers --------------------------------------------------------

@dataclass
class Passage:
    id: int
    page: int
    section: str
    text: str

    @property
    def label(self) -> str:
        """Index line: the start of the passage and what it contains further down.

        Run 31: the answer to a question about the Fig. 6 simulation (3 GHz, 400 elements,
        150 kHz) was in the middle of a passage whose first words were about something else.
        """
        flat = " ".join(self.text.split())
        first = flat[:90]
        found: list[str] = []
        for pattern in (_REFERENCE, _QUANTITY, _ACRONYM_TERM):
            for match in pattern.findall(flat[60:]):
                item = " ".join(match.split())
                if item not in found and item not in first:
                    found.append(item)
        contains = f" … contains: {', '.join(found[:7])}" if found else ""
        return f"[{self.id}] p.{self.page}" + (f" §{self.section[:40]}" if self.section else "") + f" | {first}{contains}"


_REFERENCE = re.compile(r"\b(?:Fig\.|Figure|FIGURE|Table|TABLE)\s*\d+[a-z]?(?:\([a-z]\))?|\b(?:Eq\.|equation)\s*\(?\d+\)?")
_QUANTITY = re.compile(r"\b\d+(?:\.\d+)?\s?(?:GHz|MHz|kHz|Hz|dBm|dB|ms|µs|ns|m/s|km|mm|µW|mW|W|bps|%)(?![A-Za-z])")
_ACRONYM_TERM = re.compile(r"\b[A-Z][A-Z0-9]{1,5}(?:-[A-Z0-9]+)?\b")
_HEADING = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2})*\.?\s+[A-Z(][^=]{1,80}"          # 2.1. Digital features, 1.1 Truncation
    r"|[A-Z][A-Z0-9 ,&\-]{3,60}"                                # CASCADED INTEGRATOR COMB FILTER
    r"|(?:Abstract|ABSTRACT|References|REFERENCES|Acknowledg\w*|Conclusions?|Discussion|Introduction))$"
)
_CAPTION = re.compile(r"^(?:Table|TABLE|Figure|FIGURE|Fig\.)\s*\d+\s*[:.]")
PASSAGE_CHARS = 1100


def split_passages(document: Document) -> list[Passage]:
    """Cut a paper into passages of about a paragraph: a new one starts at every heading and
    every table or figure caption, and a long run of text is cut at a sentence end."""
    passages: list[Passage] = []
    section = ""

    def close(page: int, lines: list[str]) -> None:
        text = "\n".join(lines).strip()
        if text:
            passages.append(Passage(len(passages) + 1, page, section, text))

    for page in document.pages:
        current: list[str] = []
        size = 0
        for line in page.text.splitlines():
            heading = (_HEADING.match(line) and len(line) < 90 and not line.endswith(".")
                       and (not line.isupper() or re.search(r"[A-Z]{4,}", line)))  # not "RM N" from an equation
            caption = _CAPTION.match(line)
            if (heading or caption) and current:
                close(page.number, current)
                current, size = [], 0
            if heading:
                section = line.strip()
            current.append(line)
            size += len(line) + 1
            if size >= PASSAGE_CHARS and (line.endswith(".") or size >= 1.5 * PASSAGE_CHARS):
                close(page.number, current)
                current, size = [], 0
        close(page.number, current)
    return _join_figure_text(passages)


def _join_figure_text(passages: list[Passage]) -> list[Passage]:
    """Labels drawn inside a figure come out as short lines just before its caption; keep them
    with the caption so a question about "Figure 4" finds the numbers in it."""
    joined: list[Passage] = []
    for passage in passages:
        previous = joined[-1] if joined else None
        if (previous and _FIGURE_CAPTION.match(passage.text) and previous.page == passage.page
                and not _CAPTION.match(previous.text)):
            lines = [line for line in previous.text.splitlines() if line.strip()]
            if lines and sum(len(line) for line in lines) / len(lines) < 30:
                joined[-1] = Passage(previous.id, passage.page, passage.section,
                                     passage.text + "\n[text inside the figure]\n" + previous.text)
                continue
        joined.append(passage)
    return [Passage(i + 1, p.page, p.section, p.text) for i, p in enumerate(joined)]


def rank_passages(passages: list[Passage], query: str) -> list[tuple[int, float]]:
    """Passages by BM25 score for the query terms, best first (passage ids)."""
    import math

    docs = [_tokens(p.section + " " + p.text) for p in passages]
    if not docs:
        return []
    average = sum(len(d) for d in docs) / len(docs)
    terms = set(_tokens(query))
    frequency = {t: sum(1 for d in docs if t in d) for t in terms}
    scores = []
    for passage, words in zip(passages, docs):
        counts = Counter(words)
        score = 0.0
        for term in terms:
            if not counts[term]:
                continue
            idf = math.log(1 + (len(docs) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            tf = counts[term]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(words) / average))
        scores.append((passage.id, round(score, 3)))
    return sorted(scores, key=lambda s: -s[1])
