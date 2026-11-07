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

    def summary(self) -> str:
        math = sum(1 for p in self.pages if p.math)
        figures = sum(1 for p in self.pages if p.images)
        return f"{len(self.pages)} page(s), {math} with equations, {figures} with figures"


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
    the character before it, the top not above it, and the glyph smaller (10², 10¹¹, x²)."""
    raised, base = set(), None
    for i in range(count):
        ch = textpage.get_text_range(i, 1)
        if not ch or ch.isspace():
            continue
        left, bottom, right, top = textpage.get_charbox(i)
        if ch.isdigit() and base is not None:
            b_left, b_bottom, b_right, b_top = base
            height = b_top - b_bottom
            if (height > 0 and bottom - b_bottom > 0.25 * height and top <= b_top + 0.25 * height
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
    raw_pages, images = [], []
    try:
        for page in pdf:
            text = _pdf_page_text(page.get_textpage()).replace("\r", "")
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
    return Document(path, "pdf", [_finish(lines, i + 1, figures[i]) for i, lines in enumerate(cleaned)])


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


def _tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z0-9]+|[가-힣]+", text.lower()) if w not in _STOP]
    tokens = []
    for word in words:
        if re.fullmatch(r"[가-힣]+", word) and len(word) > 2:
            tokens.extend(word[i:i + 2] for i in range(len(word) - 1))  # Korean: two-syllable pieces
        elif len(word) > 1:
            tokens.append(word)
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
