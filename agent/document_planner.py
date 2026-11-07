"""Answering questions about a document (PDF, PowerPoint) with page citations.

The same idea as the image planner: the model judges, code controls the steps and checks
the result.

1. Index    Code extracts every page (agent/document_tools.py) and builds a one-line index.
            Pages that are only a picture get a short caption from the vision model, cached on
            disk, so they can be found and used like pages with text.
2. Select   The planner model picks the pages that answer the question (JSON schema), or
            "whole" for summaries and practice questions. Page numbers in the question win.
3. Look     Selected pages whose equations or figures are not in the text are rendered and
            read by the vision model (equations as LaTeX).
4. Answer   The model answers only from those pages and cites [p.N] after every claim.
            Whole-document tasks are summarised in chunks first, then combined.
5. Check    Code verifies every citation points to a page that was given, asks once more
            if there are none, and lists numbers in the answer that appear nowhere in the
            pages (a sign of an invented value).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

from .document_tools import DOCUMENT_EXTENSIONS, Document, load_document, page_image, page_references, rank_pages

_DOC_PATH = re.compile(r"(\S+\.(?:" + "|".join(e.lstrip(".") for e in DOCUMENT_EXTENSIONS) + r"))\b", re.IGNORECASE)
_HANGUL = re.compile(r"[가-힣]")
_EXAM = re.compile(r"시험 ?문제|예상 ?문제|문제를? ?(만들|내)|퀴즈|quiz|exam question|practice question|test question", re.IGNORECASE)
# Run 25: "이 노트에서 분산의 정의 식은?" (not in the document) went to the whole-document path,
# which summarised all pages first (258 s). Only these requests may use the whole document.
_WHOLE = re.compile(
    r"요약|정리해|전체|핵심|목차|시험 ?문제|예상 ?문제|문제를? ?(만들|내)|퀴즈|"
    r"summar|overview|outline|all (the )?topics|whole|entire|quiz|exam question|practice question|test question",
    re.IGNORECASE,
)
# An answer that says the document does not cover the question needs no citation.
_NOT_COVERED = re.compile(
    r"다루지 않|포함되어 있지 않|포함하지 않|언급(이|은|도)? 없|언급되지 않|언급하지 않|나와 있지 않|나오지 않|"
    r"정보를 제공하지 않|정보가 없|찾을 수 없|확인할 수 없|제공되지 않|명시되어 있지 않|나타나 있지 않|"
    r"(does|do|did) not (cover|mention|include|contain|give|provide|state|say|discuss)|"
    r"(doesn't|don't|didn't) (cover|mention|include|contain|give|provide|discuss)|"
    r"(is|are) not (covered|mentioned|included|given|provided)|no (information|mention)",
    re.IGNORECASE,
)
# An equation, not just a symbol: Run 26 flagged "$\\tau$" in a sentence as an unread equation.
_EQUATION = re.compile(r"\\frac|\\sum|\\hat|\\arg|\\int|\\sqrt|\\prod|\\lim|[∑Σ∫√]|\$[^$\n]*=[^$\n]*\$")
_PREAMBLE = re.compile(
    r"^\\(documentclass|usepackage|begin\{document\}|end\{document\}|maketitle|title\{|author\{|date\{)"
    r"|^\\(begin|end)\{(itemize|enumerate|center|figure|table|tabular)\}"
)
_VISUAL = re.compile(
    r"수식|식 ?\(|equation|formula|latex|그림|figure|diagram|graph|그래프|차트|chart|도식|constellation|plot|표\b|table",
    re.IGNORECASE,
)
# Run 28: "[p.7, read by the vision model]" (copied from the page notes) was not taken as a citation.
_CITATION = re.compile(
    r"\[p\.?\s*(\d{1,4})(?:\s*[,–-]\s*(?:p\.?\s*)?(\d{1,4}))*(?:,\s*(?:read by|picture described by) the vision model)?\]",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:[.,]\d+)?(?![0-9A-Za-z_])")  # Korean counters (102개) may follow
_CONTEXT_CHARS = 10000   # page text given to the model for one answer
_CHUNK_CHARS = 6000      # page text per chunk for whole-document tasks
MAX_PAGES = 6
MAX_VISUAL_PAGES = 4
MAX_CAPTIONS = 40        # picture-only pages captioned per document (a scanned book is not captioned)
_CAPTION_TEXT = 80       # a page with a picture and less text than this is captioned

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string", "enum": ["pages", "whole"]},
        "pages": {"type": "array", "items": {"type": "integer"}, "maxItems": MAX_PAGES},
    },
    "required": ["scope", "pages"],
}

SELECT_PROMPT = """You choose which pages of a document are needed to answer a question.
Below is an index with one line per page: its title and first words. [equations] and [figure] mark pages whose equations or figures are not in the extracted text; "picture:" is a short description of a page that is only a picture.
Return JSON. "scope" is "whole" when the question needs the whole document: a summary of everything, practice or exam questions on the whole document, or a list of all topics. Otherwise "scope" is "pages" and "pages" lists the page numbers that contain the answer, most relevant first, at most 6.
The question and the document may be in different languages: match by meaning, not by words."""

ANSWER_PROMPT = """You answer questions about a document using only the pages given below.
Rules:
- Use only information in these pages. If they do not contain the answer, say that the document does not cover it.
- Answer every part of the question, and include each relevant point the pages give: every listed item, condition and conclusion.
- After every sentence or bullet that uses the document, cite the page as [p.N].
- Text marked "read by the vision model" is a transcription of equations or figures and may contain reading errors; say so when an answer depends on it.
- Keep separate points separate: do not combine statements from different bullets or lines into one claim, and keep each number with the item it belongs to.
- In the page text, ^ marks a superscript: 10^2 is 10 to the power 2.
- Keep the document's technical terms as they are, and answer in {language}.
- Do not add facts, numbers or examples that are not in the pages."""

MAP_PROMPT = """Below are some pages of a document. List the key points of these pages: definitions, steps, results, and important equations or numbers, in {language}.
Cite the page as [p.N] after every point. Use only these pages."""

REDUCE_PROMPT = """Below are key points from all parts of a document, with page citations.
Task: {task}
Answer in {language}. Keep the [p.N] citations of every point you use. Use only these points."""

EXAM_TASK = (
    "Write practice exam questions on this document, as the user asked. For each question give the answer "
    "and the page it comes from as [p.N]. Mix definitions, explanations and, where the points allow, calculations."
)

VISUAL_PROMPT = """This image is page {n} of a document.
1. Transcribe every equation on it in LaTeX, each on its own line between $$ and $$, in reading order. Copy the symbols exactly; do not simplify or complete anything. Do not write a LaTeX document: no \\documentclass, \\usepackage or \\begin{{document}}.
2. Describe each figure, diagram, table or chart in one or two sentences: what it shows and the labels written on it.
3. When a figure shows numbers, vectors or values, copy each one together with the label it belongs to, as "label: value" (for example "Q3 revenue: 4.2"). Never list values without their labels.
Write only what is on the page. If there are no equations and no figures, write [none]."""

CAPTION_PROMPT = """This image is page {n} of a document; the page has no text apart from what is in the picture.
In at most three sentences, say what the page shows and copy the important words, names, labels and numbers written on it. Write only what is on the page."""


def clean_transcription(text: str) -> str:
    """Strip LaTeX document scaffolding from a vision transcription; keep equations and text.

    Run 25: the vision model read the Case C equations on p.13 correctly but wrapped them in
    \\documentclass, \\usepackage and itemize blocks, which buried them in the page notes.
    """
    lines, in_math = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _PREAMBLE.match(stripped):
            continue
        if stripped == "$$":
            if in_math and lines and lines[-1] == "$$":  # Run 28: an empty "$$ $$" pair
                lines.pop()
                in_math = False
                continue
            in_math = not in_math
        stripped = re.sub(r"^\\item\s*", "- ", stripped)
        stripped = re.sub(r"^\\(sub)*section\*?\{(.*)\}$", r"\2", stripped)
        lines.append(stripped)
    return "\n".join(lines).strip()


def find_document_path(text: str, workspace: Path) -> str | None:
    workspace = workspace.resolve()
    for match in _DOC_PATH.finditer(text):
        candidate = match.group(1).strip("'\"()[]<>,")
        try:
            resolved = (workspace / candidate).resolve()
        except OSError:
            continue
        if resolved.is_file() and (resolved == workspace or workspace in resolved.parents):
            return candidate
    return None


def cited_pages(answer: str) -> list[int]:
    pages = []
    for match in _CITATION.finditer(answer):
        for number in re.findall(r"\d{1,4}", match.group(0)):
            if int(number) not in pages:
                pages.append(int(number))
    return pages


def unsupported_numbers(answer: str, sources: str, question: str) -> list[str]:
    """Numbers in the answer that appear nowhere in the sources or the question."""
    body = _CITATION.sub(" ", answer)
    body = re.sub(r"(?m)^\s*(?:[-*]\s*)?(?:\d{1,2}[.)]|Q\d+[.:)]?|문제\s*\d+[.:)]?)\s", " ", body)  # list numbering
    known = {n.replace(",", "") for n in _NUMBER.findall(sources + " " + question)}
    for base, power in re.findall(r"(\d{1,3})\^(\d{1,2})", sources):  # 10^2 written as 100
        if int(power) <= 12:
            known.add(str(int(base) ** int(power)))
    missing = []
    for number in _NUMBER.findall(body):
        clean = number.replace(",", "")
        if clean not in known and clean not in missing and len(clean.replace(".", "")) >= 2:
            missing.append(clean)
    return missing


class DocumentQuestionPlanner:
    def __init__(
        self,
        llm,
        registry,
        workspace: Path,
        on_tool_call: Callable[[str, dict, str], None] | None = None,
        on_event: Callable[[str], None] | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.llm = llm
        self.vision = getattr(registry, "vision", None)
        self.workspace = workspace.resolve()
        self.cache_dir = cache_dir or self.workspace / "logs" / "cache" / "pages"
        self.on_tool_call = on_tool_call or (lambda name, args, result: None)
        self.on_event = on_event or (lambda message: None)
        self.captions: dict[int, str] = {}

    def applies(self, question: str) -> str | None:
        return find_document_path(question, self.workspace)

    # --- steps -----------------------------------------------------------------------------

    def _caption(self, document: Document) -> dict[int, str]:
        """Short vision captions for pages that are only a picture, cached per document.

        Holdout Run 27 (GA6): a slide of biometric methods was a single picture, so its index
        line was empty and the question about it was answered from other pages.
        """
        blank = [p.number for p in document.pages if p.images > 0 and len(p.text) < _CAPTION_TEXT]
        if self.vision is None or not blank:
            return {}
        if len(blank) > MAX_CAPTIONS:
            self.on_event(f"{len(blank)} picture-only pages; captioning the first {MAX_CAPTIONS}")
            blank = blank[:MAX_CAPTIONS]
        try:
            stat = document.path.stat()
            signature = f"{stat.st_size}:{int(stat.st_mtime)}"
        except OSError:
            signature = ""
        cache = self.cache_dir / f"{document.path.stem}_captions.json"
        stored: dict[str, str] = {}
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("signature") == signature and signature:
                stored = data.get("pages", {})
        except (OSError, ValueError, AttributeError):
            pass
        todo = [n for n in blank if str(n) not in stored]
        if todo:
            self.on_event(f"captioning {len(todo)} picture-only page(s) for the index (saved for next time)")
        for number in todo:
            image = page_image(document, number, self.cache_dir)
            if image is None:
                stored[str(number)] = ""
                continue
            relative = str(image.resolve().relative_to(self.workspace))
            result = self.vision.describe(relative, CAPTION_PROMPT.format(n=number))
            self.on_tool_call("describe_image", {"path": relative, "question": f"caption of p.{number}"}, result["text"])
            answer = clean_transcription(result.get("answer", "")) if result.get("status") == "ok" else ""
            stored[str(number)] = " ".join(answer.split())[:400]
        if todo and signature:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps({"signature": signature, "pages": stored}, ensure_ascii=False, indent=1), encoding="utf-8")
            except OSError:
                pass
        return {int(n): text for n, text in stored.items() if text and int(n) in blank}

    def _index(self, document: Document, question: str) -> str:
        pages = document.pages
        if len(pages) > 60:  # a long document: index the best keyword matches only
            keep = {n for n, _ in rank_pages(document, question)[:40]}
            pages = [p for p in pages if p.number in keep]
        lines = []
        for page in pages:
            rest = " / ".join(page.text.splitlines()[1:])[:140]
            if page.number in self.captions:
                rest = (rest + " / " if rest else "") + "picture: " + self.captions[page.number][:200]
            flags = (" [equations]" if page.math else "") + (" [figure]" if page.images else "")
            lines.append(f"p.{page.number}: {page.title} — {rest}{flags}")
        return "\n".join(lines)

    def _select(self, document: Document, question: str) -> tuple[str, list[int]]:
        explicit = page_references(question, document)
        if explicit:
            self.on_event(f"pages named in the question: {', '.join(f'p.{n}' for n in explicit)}")
            return "pages", explicit[:MAX_PAGES]
        if len(document.pages) <= 2:
            return "pages", [p.number for p in document.pages]
        messages = [
            {"role": "system", "content": SELECT_PROMPT},
            {"role": "user", "content": f"Index:\n{self._index(document, question)}\n\nQuestion: {question}"},
        ]
        try:
            raw = self.llm.chat(messages, format=SELECT_SCHEMA)["message"].get("content") or ""
            data = json.loads(raw)
            scope = data.get("scope", "pages")
            pages = [int(n) for n in data.get("pages", []) if document.page(int(n))]
        except (ValueError, TypeError, KeyError, AttributeError):
            scope, pages = "pages", []
        if scope == "whole" and _WHOLE.search(question):
            return "whole", []
        if scope == "whole":
            self.on_event("the model asked for the whole document, but the question is not a summary or practice task; using matching pages")
        if not pages:
            pages = [n for n, score in rank_pages(document, question)[:3] if score > 0] or [1]
            self.on_event("page selection could not be read; using keyword matches")
        return "pages", list(dict.fromkeys(pages))[:MAX_PAGES]

    def _look(self, document: Document, numbers: list[int], question: str) -> dict[int, str]:
        """Vision transcriptions of the selected pages whose equations or figures are needed.

        Run 25: every selected page with equations was read, also for questions about plain
        text (D01 spent 20 s on p.7 for a list of synchronization types). Equations are now
        read only when the question asks about an equation or a figure; a figure-only page
        (almost no text) is always read.
        """
        if self.vision is None:
            return {}
        visual = bool(_VISUAL.search(question))
        wanted = []
        for n in numbers:
            page = document.page(n)
            figure_only = page.images > 0 and len(page.text) < 400
            if figure_only or (visual and (page.math or page.images)):
                wanted.append(n)
        wanted = wanted[:MAX_VISUAL_PAGES]
        notes = {}
        for number in wanted:
            image = page_image(document, number, self.cache_dir)
            if image is None:
                continue
            relative = str(image.resolve().relative_to(self.workspace))
            result = self.vision.describe(relative, VISUAL_PROMPT.format(n=number))
            self.on_tool_call("describe_image", {"path": relative, "question": f"equations and figures on p.{number}"}, result["text"])
            answer = clean_transcription(result.get("answer", ""))
            if result.get("status") == "ok" and answer and answer != "[none]":
                notes[number] = answer
        return notes

    def _context(self, document: Document, numbers: list[int], notes: dict[int, str], budget: int) -> str:
        per_page = max(800, budget // max(1, len(numbers)))
        blocks = []
        for number in numbers:
            page = document.page(number)
            text = page.text if len(page.text) <= per_page else page.text[:per_page] + " …"
            block = f"[p.{number}] {page.title}\n{text}"
            if page.math and number not in notes:
                block += (
                    "\n(Equations on this page were extracted as scattered symbols and are not reliable. "
                    "Do not write these equations out; say they were not read.)"
                )
            if number in notes:
                block += f"\n[p.{number}, read by the vision model]\n{notes[number]}"
            elif number in self.captions:
                block += f"\n[p.{number}, picture described by the vision model]\n{self.captions[number]}"
            blocks.append(block)
        return "\n\n".join(blocks)

    def _ask(self, system: str, user: str) -> str:
        response = self.llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return (response["message"].get("content") or "").strip()

    # --- run -------------------------------------------------------------------------------

    def run(self, question: str) -> str | None:
        path = self.applies(question)
        if path is None:
            return None
        start = time.perf_counter()
        korean = bool(_HANGUL.search(question.replace(path, "")))
        language = "Korean" if korean else "English"
        try:
            document = load_document(self.workspace / path)
        except Exception as exc:  # unreadable or unsupported file: say so instead of guessing
            return f"[{path}: the document could not be read ({exc})]"
        self.on_event(f"document: {document.summary()}")

        user_question = question.replace(path, "").strip()
        self.captions = self._caption(document)
        scope, numbers = self._select(document, user_question)
        notes: dict[int, str] = {}
        if scope == "whole":
            answer, given, sources = self._whole(document, user_question, language)
        else:
            self.on_event("pages: " + ", ".join(f"p.{n}" for n in numbers))
            notes = self._look(document, numbers, user_question)
            context = self._context(document, numbers, notes, _CONTEXT_CHARS)
            prompt = f"Pages:\n\n{context}\n\nQuestion: {user_question}"
            answer = self._ask(ANSWER_PROMPT.format(language=language), prompt)
            if not cited_pages(answer) and not _NOT_COVERED.search(answer):
                self.on_event("answer had no page citations; asking again")
                answer = self._ask(
                    ANSWER_PROMPT.format(language=language),
                    prompt + "\n\nYour previous answer had no [p.N] citations. Answer again and cite a page after every claim.",
                )
            given, sources = numbers, context
        return self._finish(document, answer, given, sources, user_question, korean, start, notes)

    def _whole(self, document: Document, question: str, language: str) -> tuple[str, list[int], str]:
        chunks, current, size = [], [], 0
        for page in document.pages:
            if current and (size + len(page.text) > _CHUNK_CHARS or len(current) >= 10):
                chunks.append(current)
                current, size = [], 0
            current.append(page.number)
            size += len(page.text)
        if current:
            chunks.append(current)
        self.on_event(f"whole document: {len(chunks)} part(s) summarised first, then combined")
        points = []
        for chunk in chunks:
            context = self._context(document, chunk, {}, _CHUNK_CHARS)
            points.append(self._ask(MAP_PROMPT.format(language=language), context))
        task = EXAM_TASK if _EXAM.search(question) else f"Answer the user's request: {question}"
        combined = "\n\n".join(points)
        answer = self._ask(REDUCE_PROMPT.format(task=task, language=language), f"Key points:\n\n{combined}\n\nRequest: {question}")
        all_text = "\n".join(p.text for p in document.pages) + "\n" + "\n".join(self.captions.values())
        # Numbers are checked against the document itself, not against the intermediate summaries.
        return answer, [p.number for p in document.pages], all_text

    def _finish(self, document, answer, given, sources, question, korean, start, read: dict | None = None) -> str:
        t = _TEXT["ko" if korean else "en"]
        read = read or {}
        cited = cited_pages(answer)
        wrong = [n for n in cited if n not in given]
        numbers = unsupported_numbers(answer, sources, question)
        not_covered = not cited and bool(_NOT_COVERED.search(answer))
        notes = []
        if not_covered:
            checked = ", ".join(f"p.{n}" for n in given[:8]) + (" …" if len(given) > 8 else "")
            notes.append(t["not_covered"].format(pages=checked))
        elif not cited:
            notes.append(t["no_citation"])
        # Run 25: a practice question gave the van de Beek estimate as (2/π)·arg γ; the slide's
        # equation was never read by the vision model, so the formula came from the model itself.
        unread = [n for n in cited if n in given and document.page(n).math and n not in read]
        if unread and _EQUATION.search(answer):
            notes.append(t["unread_equations"].format(pages=", ".join(f"p.{n}" for n in unread)))
        if wrong:
            notes.append(t["wrong_citation"].format(pages=", ".join(f"p.{n}" for n in wrong)))
        if numbers:
            notes.append(t["numbers"].format(numbers=", ".join(numbers)))
        used = [n for n in cited if n in given]
        source_line = t["sources"] + ", ".join(
            f"p.{n} ({(document.page(n).title or self.captions.get(n, ''))[:50]})" for n in used[:8]
        ) if used else ""
        self.on_event(
            f"check: {len(used)} cited page(s)"
            + (f", {len(wrong)} citation(s) to pages not given" if wrong else "")
            + (f", {len(numbers)} number(s) not in the document" if numbers else "")
            + (", answer: not covered by the document" if not_covered else ", no citations" if not cited else "")
            + f" | total {time.perf_counter() - start:.1f} s"
        )
        return "\n\n".join(part for part in [answer, source_line, *notes] if part)


_TEXT = {
    "ko": {
        "sources": "출처: ",
        "no_citation": "⚠ 답에 페이지 출처가 없습니다. 문서에서 확인되지 않은 내용일 수 있습니다.",
        "wrong_citation": "⚠ 참고하지 않은 페이지를 출처로 달았습니다: {pages}. 해당 문장은 확인이 필요합니다.",
        "numbers": "⚠ 문서에서 찾을 수 없는 숫자가 답에 있습니다: {numbers}. 지어낸 값일 수 있습니다.",
        "not_covered": "(문서에 없다는 답입니다. 확인한 페이지: {pages})",
        "unread_equations": "⚠ 답의 수식은 원본 페이지를 눈으로 확인하지 않고 쓴 것입니다 ({pages}). 원본과 대조가 필요합니다.",
    },
    "en": {
        "sources": "Sources: ",
        "no_citation": "⚠ The answer has no page citations; it may not come from the document.",
        "wrong_citation": "⚠ The answer cites pages that were not given: {pages}. Check those statements.",
        "numbers": "⚠ Numbers in the answer that do not appear in the document: {numbers}. They may be invented.",
        "not_covered": "(The answer says the document does not cover this. Pages checked: {pages})",
        "unread_equations": "⚠ The equations in this answer were written without reading the original page ({pages}). Check them against the document.",
    },
}
