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
            pages (a sign of an invented value). An answer saying the document does not cover
            the question is accepted only after a keyword search of the rest of the document.

Papers (Document.dense) are searched by passage instead of by page: holdout Run 29 showed that
a page index built from first lines is blind on 5,000-character paper pages, and that whole
pages cut to fit the context lose what is at the bottom of each page.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from .table_tools import check_arithmetic, describe_checks, explain_numbers, fill_calculations, statement_checks
from .formula_tools import FormulaReading, compare_latex, display_formulas, is_part_of, read_equation, read_spot
from .document_tools import (
    DOCUMENT_EXTENSIONS,
    Document,
    Passage,
    load_document,
    page_image,
    page_references,
    _tokens,
    is_chart_page,
    rank_pages,
    rank_passages,
    split_passages,
)

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
# Korean counters (102개) and units (백만원) may follow. Run 42: "37,792,969" has two thousands
# separators and was split into 37792 and 969.
_NUMBER = re.compile(r"(?<![0-9A-Za-z_.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)(?![0-9A-Za-z_])")
_CONTEXT_CHARS = 10000   # page text given to the model for one answer
_CHUNK_CHARS = 6000      # page text per chunk for whole-document tasks
_PAPER_CHUNK_CHARS = 12000  # papers: fewer, larger parts (Run 31: 26 parts took 15 minutes)
_REDUCE_TOKENS = 4500    # estimated tokens of key points combined in one call
MAX_PAGES = 6
MAX_VISUAL_PAGES = 4
MAX_PASSAGES = 8         # passages chosen by the planner model for a paper
MAX_EXTRA_PASSAGES = 3   # passages added by keyword search
MAX_PAPER_VISUAL_PAGES = 3
_SHORT_NOT_COVERED = 400  # a "not covered" answer shorter than this triggers a second search
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

PASSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string", "enum": ["passages", "whole"]},
        "passages": {"type": "array", "items": {"type": "integer"}, "maxItems": MAX_PASSAGES},
        "keywords": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": ["scope", "passages", "keywords"],
}

PASSAGE_PROMPT = """You choose which passages of a paper are needed to answer a question.
Below is an index with one line per passage: its [id], page, section (§) and first words. Tables and figures start with their caption ("Table 1:", "Figure 4:").
Return JSON. "scope" is "whole" only when the question needs the whole document: a summary of everything, or practice or exam questions on the whole document. Otherwise "scope" is "passages" and "passages" lists the ids that contain the answer, most relevant first, at most 8.
"keywords" lists up to 8 words or short phrases, in the document's language, that the text answering the question would contain: technical terms, names, symbols, "Table 3".
The question and the document may be in different languages: match by meaning, not by words."""

# "equation (3)", "Eq. (55)", "식 (55)", "수식 (3)", "(3)번 식"
_NUMBER_LIST = r"\(\s*\d{1,3}\s*\)(?:\s*(?:,|and|or|&|와|과|및|,?\s*and)\s*\(\s*\d{1,3}\s*\))*"
# "equation (3)", "equations (1) and (2)", "식 (3)과 (4)", "(31)번 식"
_EQUATION_REF = re.compile(
    rf"(?:equations?|eqs?\.|eqn\.?|수식|공식|식)\s*({_NUMBER_LIST})|({_NUMBER_LIST})\s*번?\s*(?:식|수식)",
    re.IGNORECASE,
)
MAX_EQUATIONS = 2


def equation_refs(question: str) -> list[int]:
    """Equation numbers named in a question, in order, at most MAX_EQUATIONS."""
    found = [int(n) for a, b in _EQUATION_REF.findall(question) for n in re.findall(r"\d{1,3}", a or b)]
    return list(dict.fromkeys(found))[:MAX_EQUATIONS]


# Questions that ask for a formula without naming its number (BS3: "how is it defined?").
_FORMULA_QUESTION = re.compile(
    r"\b(?:formulas?|equations?|expressions?|defin(?:e|ed|es|ition)|latex|derived?)\b|수식|공식|정의|표현식|(?<![가-힣])식",
    re.IGNORECASE)
_GENERIC_FORMULA_WORDS = {"formula", "formulas", "equation", "equations", "expression", "expressions", "define",
                          "defined", "defines", "definition", "latex", "derive", "derived", "write", "used", "given"}
MAX_DISPLAYED = 2  # unnumbered equations read for one question


def formula_name(reading: FormulaReading) -> str:
    """How the context names an equation read from the image."""
    if reading.number:
        return f"equation ({reading.number})"
    tail = " ".join(reading.before.split())[-50:]
    return f'the unnumbered equation after "...{tail}"' if tail else "an unnumbered equation"


def formula_block(reading: FormulaReading) -> str:
    """Context block for an equation read from the page image."""
    if reading.status == "confirmed":
        how = "read twice from the page image; the readings agree"
    elif reading.status in ("close", "check_failed"):
        how = "read twice from the page image; the readings differ slightly, so details are uncertain: " + "; ".join(reading.differences)[:200]
    else:
        how = "read twice from the page image; the readings disagree, so this transcription is uncertain"
    return f"[p.{reading.page}, {formula_name(reading)}, {how}]\n$$ {reading.latex} $$"


ANSWER_PROMPT = """You answer questions about a document using only the pages given below.
Rules:
- Use only information in these pages. If they do not contain the answer, say that the document does not cover it.
- Answer every part of the question, and include each relevant point the pages give: every listed item, condition and conclusion.
- After every sentence or bullet that uses the document, cite the page as [p.N].
- Text marked "read by the vision model" is a transcription of equations or figures and may contain reading errors; say so when an answer depends on it.
- Keep separate points separate: do not combine statements from different bullets or lines into one claim, and keep each number with the item it belongs to.
- In the page text, ^ marks a superscript: 10^2 is 10 to the power 2.
- When an equation is given as read from the page image, copy it exactly as given, and say that it is uncertain if the block says so. Take the meaning of its symbols from the text next to it ("where ... is ...").
- Keep the document's technical terms as they are, and answer in {language}.
- Do not spell out an abbreviation unless the pages spell it out; otherwise keep the abbreviation as it is.
- Do not add facts, numbers or examples that are not in the pages.
- Do not do arithmetic yourself. For every sum, difference, ratio, percentage or growth rate, write the calculation as [calc: expression] with the numbers from the pages, for example [calc: (112010 - 93736) / 93736 * 100]%; it is computed by code and the result is put in its place.
- Values written with ~ were estimated from a chart's axis: give them as approximate.
- Give a number only for the exact item asked. If the pages give a figure only for a larger group that contains it (a whole division when one product in it is asked) or for a different series of the same chart, say that the asked figure is not given, and do not present the other figure as it.
- Lines marked "checked by code" are exact checks of the page's totals; use them, and say so when a total does not match."""

MAP_PROMPT = """Below are some pages of a document. List at most 8 key points of these pages: definitions, steps, results, and important equations or numbers, one short line each, in the language of the pages.
Cite the page as [p.N] after every point. Use only these pages."""

# Run 31: 26 parts of key points from a 43-page paper were far longer than the 8,192-token
# context, so the model saw only the last parts and every practice question came from p.35-38.
MERGE_PROMPT = """Below are key points from several parts of a document, with page citations.
Merge them into at most 12 key points that keep the most important definitions, results and numbers from every part. Keep the [p.N] citation of every point. Use only these points."""

REDUCE_PROMPT = """Below are key points from all parts of a document, with page citations.
Task: {task}
Answer in {language}. Keep the [p.N] citations of every point you use. Use only these points."""

EXAM_TASK = (
    "Write practice exam questions on this document, as the user asked. For each question give the answer "
    "and the page it comes from as [p.N]. Mix definitions, explanations and, where the points allow, calculations."
)

# Run 42: asked for "equations and figures", the vision model answered [none] for chart pages of
# results decks, and charts lost the pairing of numbers and bars. Charts and pictured tables are now
# asked for as tables, with values read from an axis marked "~".
VISUAL_PROMPT = """This image is page {n} of a document. Transcribe what a text extraction cannot show, in this order:
1. Charts and graphs: for each one, its title and unit, then a Markdown table with one row per category (x-axis label, slice or step) and one column per series, named as in the legend. Copy the value printed on or next to each bar, point or slice. If no value is printed, estimate it from the axis and write it with ~ in front (for example ~48). Keep minus signs. For a waterfall (bridge) chart, list the start, every step with its sign and label, and the end.
2. Tables drawn as a picture: copy them as Markdown tables, cell by cell, with the numbers exactly as printed.
3. Equations: each in LaTeX on its own line between $$ and $$, in reading order. Copy the symbols exactly; do not simplify or complete anything. Do not write a LaTeX document: no \\documentclass, \\usepackage or \\begin{{document}}.
4. Other figures and diagrams: one or two sentences each with the labels written on them; keep every number with the label it belongs to, as "label: value".
Write only what is on the page. If the page has none of these, write [none]."""

CHART_PROMPT = """This image is page {n} of a document and it holds one or more charts.
For each chart write its title and unit, then a Markdown table with one row per category (x-axis label, slice or step) and one column per series, named as in the legend, with the value printed on or next to each bar, point or slice. If no value is printed, estimate it from the axis and write it with ~ in front. Keep minus signs and percentages as printed."""

# Page readings are cached per document; the version changes when these prompts change.
_PROMPT_VERSION = hashlib.md5((VISUAL_PROMPT + CHART_PROMPT).encode()).hexdigest()[:8]

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


_ACRONYM = r"[A-Z][A-Za-z0-9&]{0,2}[A-Z][A-Za-z0-9&]{0,6}"   # RIS, SINR, mmWave is not one, PEB, 5G-NR
_WORDS = r"[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){1,7}"
_INLINE_EXPANSION = re.compile(rf"\b({_ACRONYM})\s*\(\s*({_WORDS})\s*\)")          # RIS (Reflective Intelligent Surface)
_EXPANSION_FIRST = re.compile(rf"\b({_WORDS})\s*\(\s*({_ACRONYM})s?\s*\)")         # reconfigurable intelligent surface (RIS)


def _norm_phrase(text: str) -> str:
    words = re.sub(r"[-\s]+", " ", text.lower()).split()
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words)


def _trim_expansion(words: str, acronym: str) -> str:
    """The shortest run of trailing words that starts with the acronym's first letter."""
    tokens = words.split()
    for k in range(1, len(tokens) + 1):
        if tokens[-k][0].lower() == acronym[0].lower() and k >= min(2, len(tokens)):
            return " ".join(tokens[-k:])
    return ""


def unsupported_expansions(answer: str, document_text: str) -> list[str]:
    """Acronym expansions in the answer that the document never writes.

    Run 31: the answer called RIS a "Reflective Intelligent Surface" (the paper: reconfigurable)
    and PEB a "Predicted Error Bound" (the paper: position error bound). Only acronyms that the
    document itself uses are checked, so an expansion of a term the document does not use is left
    alone.
    """
    found: list[tuple[str, str]] = []
    for acronym, words in _INLINE_EXPANSION.findall(answer):
        found.append((acronym, words))
    for words, acronym in _EXPANSION_FIRST.findall(answer):
        found.append((acronym, _trim_expansion(words, acronym)))
    document = _norm_phrase(document_text)
    flagged = []
    for acronym, expansion in found:
        if not expansion or expansion[0].lower() != acronym[0].lower():
            continue
        if not re.search(rf"\b{re.escape(acronym)}", document_text):
            continue  # not the document's term
        if _norm_phrase(expansion) not in document:
            item = f"{acronym} ({expansion})"
            if item not in flagged:
                flagged.append(item)
    return flagged


def document_expansions(document_text: str) -> dict[str, str]:
    """The document's own definitions, "reconfigurable intelligent surface (RIS)", by acronym."""
    counts: dict[str, Counter] = {}
    for words, acronym in _EXPANSION_FIRST.findall(document_text):
        phrase = _trim_expansion(" ".join(words.split()), acronym)
        if phrase:
            counts.setdefault(acronym, Counter())[phrase] += 1
    return {acronym: c.most_common(1)[0][0] for acronym, c in counts.items()}


def repair_expansions(answer: str, document_text: str) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    """Replace acronym expansions the document never writes with the document's own.

    Run 38 repeats: RA6 called RIS a "Reflective Intelligent Surface" in 2 of 3 runs although the
    paper defines "reconfigurable intelligent surface (RIS)" on p.1; the page was not among the
    passages, so the model guessed. The expansion is not what was asked, so it is corrected in code:
    to the document's definition when there is one, otherwise "RIS (...)" becomes "RIS". Returns the
    answer, the corrections (acronym, old, new; new is "" when removed) and the expansions left as
    they were (an invented "words (ACR)" with no definition to put in its place).
    """
    known = document_expansions(document_text)
    fixed: list[tuple[str, str, str]] = []
    left: list[str] = []
    for item in unsupported_expansions(answer, document_text):
        acronym, expansion = item[:-1].split(" (", 1)
        words = r"[\s-]+".join(re.escape(w) for w in expansion.split())
        inline = re.compile(rf"\b{re.escape(acronym)}\s*\(\s*{words}\s*\)")
        first = re.compile(rf"\b{words}(\s*\(\s*{re.escape(acronym)}s?\s*\))")
        right = known.get(acronym, "")
        before = answer
        if right:
            answer = inline.sub(f"{acronym} ({right})", answer)
            answer = first.sub(lambda m: right + m.group(1), answer)
        else:
            answer = inline.sub(acronym, answer)
        if answer != before:
            fixed.append((acronym, expansion, right))
        else:
            left.append(item)
    return answer, fixed, left


def drop_repeated_paragraphs(answer: str, min_chars: int = 40) -> tuple[str, int]:
    """Remove paragraphs that repeat an earlier one word for word.

    Run 38 repeats: one RA1 answer wrote the same paragraph three times. Short paragraphs
    (a source line, "- [p.3]") are never removed."""
    seen: set[str] = set()
    kept, dropped = [], 0
    for paragraph in re.split(r"\n\s*\n", answer):
        key = re.sub(r"\W+", "", paragraph.lower())
        if len(key) >= min_chars and key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(paragraph)
    return ("\n\n".join(kept), dropped) if dropped else (answer, 0)


def estimate_tokens(text: str) -> int:
    """Rough token count: about four characters per token for Latin text, one per Hangul."""
    ascii_chars = sum(1 for ch in text if ch.isascii())
    return ascii_chars // 4 + (len(text) - ascii_chars)


_TRIGRAM_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def misplaced_citations(answer: str, pages: dict[int, str]) -> list[tuple[int, int]]:
    """Sentences cited to one page whose wording is found on another given page instead.

    Run 31: "channel estimation must be carried out at the receiver [p.7]" is a sentence from
    p.24. A sentence is compared by its three-word sequences, so only answers that keep the
    document's wording (English text) can be checked; others are skipped.
    """
    page_text = {n: " ".join(_TRIGRAM_WORD.findall(text.lower())) for n, text in pages.items()}
    flagged: list[tuple[int, int]] = []
    for sentence in re.split(r"(?<=\])\s*|\n+", answer):
        cited = cited_pages(sentence)
        if len(cited) != 1:
            continue
        plain = _CITATION.sub("", sentence)
        if len(re.findall(r"[가-힣]", plain)) >= 5:
            continue  # a Korean sentence: its English words are terms, not the document's wording
        words = _TRIGRAM_WORD.findall(plain.lower())
        trigrams = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
        if len(trigrams) < 4:
            continue
        def score(n: int) -> float:
            text = page_text.get(n, "")
            return sum(1 for t in trigrams if t in text) / len(trigrams)
        own = score(cited[0])
        best = max((n for n in page_text if n != cited[0]), key=score, default=None)
        if best is not None and own <= 0.15 and score(best) >= 0.5 and (cited[0], best) not in flagged:
            flagged.append((cited[0], best))
    return flagged


def unsupported_numbers(answer: str, sources: str, question: str) -> list[str]:
    """Numbers in the answer that appear nowhere in the sources or the question."""
    body = _CITATION.sub(" ", answer)
    body = re.sub(r"(?m)^\s*(?:[-*]\s*)?(?:\d{1,2}[.)]|Q\d+[.:)]?|문제\s*\d+[.:)]?)\s", " ", body)  # list numbering
    # Run 30: "F R = 30f ps" in a paper; a unit glued to a number in the source still counts.
    known = {n.replace(",", "") for n in _NUMBER.findall(sources + " " + question)}
    known |= {n.replace(",", "") for n in re.findall(r"(?<![0-9.])\d+(?:[.,]\d+)?", sources)}
    # Run 33: "89,28%" is a decimal comma (European style); the answer writes 89.28.
    known |= {n.replace(",", ".") for n in re.findall(r"(?<![0-9.,])\d+,\d{1,2}(?![0-9])", sources)}
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
        self.labels: dict[int, str] = {}  # papers: the section of each cited page, for the source line
        self.formulas: list[FormulaReading] = []  # equations named in the question, read from the image

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
            flags = (" [equations]" if page.math else "") + (" [figure]" if page.images or page.drawings else "")
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

    def _select_passages(self, document: Document, passages: list[Passage], question: str) -> tuple[str, list[int], list[int], list[str]]:
        """Papers: the planner model picks passages from a passage index and names keywords;
        keyword search adds a few more. Returns scope, chosen ids, extra ids, keywords."""
        explicit = page_references(question, document)
        if explicit:
            self.on_event(f"pages named in the question: {', '.join(f'p.{n}' for n in explicit)}")
            return "passages", [p.id for p in passages if p.page in explicit], [], []
        shown = passages
        if len(passages) > 80:  # a long paper: index the best keyword matches only
            keep = {i for i, _ in rank_passages(passages, question)[:80]}
            shown = [p for p in passages if p.id in keep]
        messages = [
            {"role": "system", "content": PASSAGE_PROMPT},
            {"role": "user", "content": "Index:\n" + "\n".join(p.label for p in shown) + f"\n\nQuestion: {question}"},
        ]
        try:
            raw = self.llm.chat(messages, format=PASSAGE_SCHEMA)["message"].get("content") or ""
            data = json.loads(raw)
            scope = data.get("scope", "passages")
            valid = {p.id for p in passages}
            chosen = [int(i) for i in data.get("passages", []) if int(i) in valid]
            keywords = [str(k) for k in data.get("keywords", []) if str(k).strip()][:8]
        except (ValueError, TypeError, KeyError, AttributeError):
            scope, chosen, keywords = "passages", [], []
        if scope == "whole" and _WHOLE.search(question):
            return "whole", [], [], keywords
        if scope == "whole":
            self.on_event("the model asked for the whole document, but the question is not a summary or practice task; using matching passages")
        chosen = list(dict.fromkeys(chosen))[:MAX_PASSAGES]
        ranked = [i for i, score in rank_passages(passages, question + " " + " ".join(keywords)) if score > 0]
        if not chosen:
            self.on_event("passage selection could not be read; using keyword matches")
            return "passages", ranked[:5] or [passages[0].id], [], keywords
        extra = [i for i in ranked if i not in chosen][:MAX_EXTRA_PASSAGES]
        return "passages", chosen, extra, keywords

    def _passage_context(self, passages: dict[int, Passage], ids: list[int], notes: dict[int, str],
                         document: Document, budget: int) -> tuple[str, list[int], list[int]]:
        """Whole passages in reading order, most relevant first until the budget is used."""
        kept, size = [], 0
        for i in ids:
            length = len(passages[i].text) + 40
            if kept and size + length > budget:
                continue
            kept.append(i)
            size += length
        kept.sort()
        blocks, pages = [], []
        for position, i in enumerate(kept):
            passage = passages[i]
            section = f" §{passage.section}" if passage.section else ""
            blocks.append(f"[p.{passage.page}]{section}\n{passage.text}")
            last_on_page = position == len(kept) - 1 or passages[kept[position + 1]].page != passage.page
            if passage.page not in pages:
                pages.append(passage.page)
            if last_on_page:
                page = document.page(passage.page)
                if passage.page in notes:
                    blocks.append(f"[p.{passage.page}, read by the vision model]\n{notes[passage.page]}")
                elif page.math:
                    blocks.append(
                        f"(p.{passage.page}: equations on this page were extracted as scattered symbols and are not "
                        "reliable. Do not write these equations out; say they were not read.)"
                    )
        return "\n\n".join(blocks), pages, kept

    def _look(self, document: Document, numbers: list[int], question: str) -> dict[int, str]:
        """Vision transcriptions of the selected pages whose equations or figures are needed.

        Run 25: every selected page with equations was read, also for questions about plain
        text (D01 spent 20 s on p.7 for a list of synchronization types). Equations are now
        read only when the question asks about an equation or a figure; a figure-only page
        (almost no text) is always read.

        Run 43 (TD2): a question about a waterfall chart that did not say "chart" left the page
        unread, and the answer took the wrong bar. In slides and reports (not papers) a figure page
        whose text is mostly numbers is a chart page and is read for any question. Readings are
        cached per page, and a chart page read as [none] is asked once more for its charts only
        (TD3: a page of sixteen bar groups came back as [none]).
        """
        if self.vision is None:
            return {}
        visual = bool(_VISUAL.search(question))
        wanted = []
        for n in numbers:
            page = document.page(n)
            figure_only = page.images > 0 and len(page.text) < 400
            chart = not document.dense and is_chart_page(page)
            if figure_only or chart or (visual and (page.math or page.images or page.drawings)):
                wanted.append(n)
        wanted = wanted[:MAX_PAPER_VISUAL_PAGES if document.dense else MAX_VISUAL_PAGES]
        stored, cache, signature = self._load_notes(document)
        notes = {}
        for number in wanted:
            if str(number) in stored:
                if stored[str(number)]:
                    notes[number] = stored[str(number)]
                continue
            image = page_image(document, number, self.cache_dir)
            if image is None:
                continue
            relative = str(image.resolve().relative_to(self.workspace))
            result = self.vision.describe(relative, VISUAL_PROMPT.format(n=number))
            self.on_tool_call("describe_image", {"path": relative, "question": f"equations and figures on p.{number}"}, result["text"])
            answer = clean_transcription(result.get("answer", "")) if result.get("status") == "ok" else ""
            page = document.page(number)
            if answer in ("", "[none]") and (is_chart_page(page) or (page.images > 0 and len(page.text) < 400)):
                result = self.vision.describe(relative, CHART_PROMPT.format(n=number))
                self.on_tool_call("describe_image", {"path": relative, "question": f"charts on p.{number}"}, result["text"])
                answer = clean_transcription(result.get("answer", "")) if result.get("status") == "ok" else ""
            if result.get("status") == "ok":
                stored[str(number)] = answer if answer != "[none]" else ""
            if answer and answer != "[none]":
                notes[number] = answer
        self._save_notes(cache, signature, stored)
        return notes

    def _load_notes(self, document: Document) -> tuple[dict[str, str], Path, str]:
        try:
            stat = document.path.stat()
            signature = f"{stat.st_size}:{int(stat.st_mtime)}:{_PROMPT_VERSION}"
        except OSError:
            signature = ""
        cache = self.cache_dir / f"{document.path.stem}_notes.json"
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if signature and data.get("signature") == signature:
                return dict(data.get("pages", {})), cache, signature
        except (OSError, ValueError, AttributeError):
            pass
        return {}, cache, signature

    @staticmethod
    def _save_notes(cache: Path, signature: str, stored: dict[str, str]) -> None:
        if not signature or not stored:
            return
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"signature": signature, "pages": stored}, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

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
            elif len(page.text.strip()) < 20:
                # Run 42, SC5: a picture page that was not read gave the model nothing, and it
                # answered with a business unit and a number it made up.
                block += "\n(This page has no text, and its picture was not read. Nothing on it can be used.)"
            blocks.append(block)
        return "\n\n".join(blocks)

    def _add_checks(self, document: Document, context: str, pages: list[int], notes: dict[int, str]) -> str:
        """Totals of the statements on the given pages, recomputed by code (agent/table_tools.py).

        Each page is checked alone, and each pair of consecutive pages together, since a balance
        sheet often runs over two pages (assets on one, liabilities and equity on the next)."""
        lines: list[str] = []
        seen: set[tuple[str, int]] = set()
        groups = [[n] for n in pages] + [[n, n + 1] for n in pages if n + 1 in pages]
        for group in groups:
            text = "\n".join(document.page(n).text + "\n" + notes.get(n, "") for n in group if document.page(n))
            checks = [c for c in statement_checks(text) if (c.name, c.column) not in seen]
            for check in checks:
                seen.add((check.name, check.column))
            if checks:
                lines.append(describe_checks(checks, group[-1] if len(group) == 1 else None))
        if lines:
            self.on_event(f"totals checked by code: {sum(l.count(chr(10)) + 1 for l in lines)}, "
                          f"{sum(l.count('DOES NOT MATCH') for l in lines)} not matching")
            return context + "\n\n" + "\n".join(lines)
        return context

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
        self.labels = {}
        self.formulas = self._read_equations(document, user_question)
        if document.dense:
            return self._run_paper(document, user_question, language, korean, start)
        scope, numbers = self._select(document, user_question)
        if scope != "whole" and self.formulas:
            numbers = list(dict.fromkeys([r.page for r in self.formulas] + numbers))
        notes: dict[int, str] = {}
        if scope == "whole":
            answer, given, sources = self._whole(document, user_question, language)
        else:
            self.on_event("pages: " + ", ".join(f"p.{n}" for n in numbers))
            notes = self._look(document, numbers, user_question)
            context = self._add_checks(document, self._context(document, numbers, notes, _CONTEXT_CHARS), numbers, notes)
            answer = self._answer(context, user_question, language)
            given, sources = numbers, self._with_formulas(context)
            if self._needs_search(answer) and not page_references(user_question, document):
                more = [n for n, score in rank_pages(document, user_question) if score > 0 and n not in numbers][:3]
                if more:
                    self.on_event(self._search_event(more))
                    more_notes = self._look(document, more, user_question)
                    notes.update(more_notes)
                    given = more + numbers
                    context = self._add_checks(document, self._context(document, given, notes, _CONTEXT_CHARS), given, notes)
                    answer = self._answer(context, user_question, language)
                    sources = self._with_formulas(context)
        return self._finish(document, answer, given, sources, user_question, korean, start, notes)

    def _read_equations(self, document: Document, question: str) -> list[FormulaReading]:
        """Equations named in the question ("equation (3)", "식 (55)"), located by their number and
        read twice from the page image (agent/formula_tools.py).

        Holdout Run 33: a question about φ, α in equation (3) found no passage (keyword search
        ignores Greek letters), and an answer about equation (1) swapped two operators that the
        text next to the equation defines."""
        if self.vision is None or document.kind != "pdf":
            return []
        readings = []
        for number in equation_refs(question):
            reading = read_equation(self.vision, self.workspace, document, number, self.cache_dir.parent / "formulas")
            for image in reading.images[:1]:
                self.on_tool_call("read_equation", {"path": image, "equation": number}, f"{reading.status}: {reading.latex}")
            where = f"p.{reading.page}" if reading.page else "not found"
            self.on_event(f"equation ({number}): {where}, {reading.status.replace('_', ' ')}")
            if reading.differences and reading.status != "confirmed":
                # Run 37, SA8: the report showed "disagree" but not where the readings differed.
                self.on_event("  readings differ: " + "; ".join(reading.differences[:4]))
            if reading.page:
                readings.append(reading)
        return readings

    def _read_displayed(self, document: Document, question: str, passages: list[Passage],
                        chosen_pages: list[int]) -> tuple[list[FormulaReading], list[int]]:
        """Unnumbered equations for a question that asks for a formula without a number, read like
        numbered ones. Returns the readings and the passages next to them, to be given first.

        Holdout Run 33, BS3: the Ricker wavelet's formula has no number; the answer rebuilt it from
        the text layer's scattered characters and wrote an exponent the page does not print.

        Every displayed equation in the document is a candidate, scored by the words it shares with
        the question in the text before, inside and after it, each word weighted by how rare it is
        among the document's passages. Run 39: counting shared words picked the Ricker wavelet
        ("Gaussian function") over PolyLoss for "How is the PolyLoss function defined?", and looking
        only on the chosen pages missed the k-space error formula on p.22, a page no passage chosen
        for the question was on."""
        if self.vision is None or document.kind != "pdf" or not _FORMULA_QUESTION.search(question):
            return [], []
        import math

        words = set(_tokens(question)) - _GENERIC_FORMULA_WORDS
        passage_words = [set(_tokens(p.text)) for p in passages]
        def weight(word: str) -> float:
            df = sum(word in w for w in passage_words)
            return math.log((len(passages) + 1) / (df + 1)) + 0.1
        found = []
        for page in range(1, len(document.pages) + 1):
            for spot in display_formulas(document, page):
                shared = words & set(_tokens(" ".join((spot.before, spot.text, spot.after))))
                score = sum(weight(w) for w in shared)
                if score > 0:
                    found.append((score, page in chosen_pages, -page, spot.band[1], spot))
        found.sort(key=lambda f: f[:4], reverse=True)
        found = found[:MAX_DISPLAYED]
        readings, around = [], []
        for *_, spot in found:
            reading = read_spot(self.vision, self.workspace, document, spot, self.cache_dir.parent / "formulas")
            for image in reading.images[:1]:
                self.on_tool_call("read_equation", {"path": image, "page": spot.page}, f"{reading.status}: {reading.latex}")
            self.on_event(f"unnumbered equation on p.{spot.page} after \"...{spot.before[-40:].strip()}\": "
                          + reading.status.replace("_", " "))
            if reading.differences and reading.status != "confirmed":
                self.on_event("  readings differ: " + "; ".join(reading.differences[:4]))
            if reading.latex:
                readings.append(reading)
                near = set(_tokens(spot.before + " " + spot.after))
                same_page = [p for p in passages if p.page == spot.page]
                if same_page:
                    around.append(max(same_page, key=lambda p: len(near & set(_tokens(p.text)))).id)
        return readings, around

    def _with_formulas(self, context: str) -> str:
        """Equations read from the image go first, so the context budget never drops them."""
        blocks = [formula_block(r) for r in self.formulas if r.latex]
        return "\n\n".join(blocks + [context]) if blocks else context

    def _answer(self, context: str, question: str, language: str) -> str:
        context = self._with_formulas(context)
        prompt = f"Pages:\n\n{context}\n\nQuestion: {question}"
        answer = self._ask(ANSWER_PROMPT.format(language=language), prompt)
        if not cited_pages(answer) and not _NOT_COVERED.search(answer):
            self.on_event("answer had no page citations; asking again")
            answer = self._ask(
                ANSWER_PROMPT.format(language=language),
                prompt + "\n\nYour previous answer had no [p.N] citations. Answer again and cite a page after every claim.",
            )
        return answer

    @staticmethod
    def _needs_search(answer: str) -> bool:
        """A short answer saying the document does not cover the question.

        Holdout Run 29: given the wrong pages, the model answered "the document does not cover
        this" nine times, and the code accepted it. Such an answer now has to survive a keyword
        search of the rest of the document first.
        """
        return bool(_NOT_COVERED.search(answer)) and (not cited_pages(answer) or len(answer) < _SHORT_NOT_COVERED)

    @staticmethod
    def _search_event(pages: list[int]) -> str:
        return ("the answer says the document does not cover this; searching the rest of the document: "
                + ", ".join(f"p.{n}" for n in pages))

    def _run_paper(self, document: Document, question: str, language: str, korean: bool, start: float) -> str:
        passages = split_passages(document)
        by_id = {p.id: p for p in passages}
        scope, chosen, extra, keywords = self._select_passages(document, passages, question)
        if scope == "whole":
            answer, given, sources = self._whole(document, question, language)
            self.labels = {}
            for passage in passages:  # the first section on each page names it in the source line
                if passage.section:
                    self.labels.setdefault(passage.page, passage.section)
            return self._finish(document, answer, given, sources, question, korean, start, {})
        if self.formulas:
            around = [p.id for r in self.formulas for p in passages
                      if p.page == r.page and re.search(rf"\({r.number}\)", p.text)]
            chosen = list(dict.fromkeys(around + chosen))
            extra = [i for i in extra if i not in chosen]
        if not self.formulas:
            self.formulas, around = self._read_displayed(
                document, question, passages, list(dict.fromkeys(by_id[i].page for i in chosen)))
            chosen = list(dict.fromkeys(around + chosen))
            extra = [i for i in extra if i not in chosen]
        pages = list(dict.fromkeys(by_id[i].page for i in chosen))
        self.on_event(
            f"passages: {len(chosen)} chosen, {len(extra)} by keywords, on "
            + ", ".join(f"p.{n}" for n in dict.fromkeys(by_id[i].page for i in chosen + extra))
            + (f" | keywords: {', '.join(keywords[:6])}" if keywords else "")
        )
        notes = self._look(document, pages, question)
        context, given, kept = self._passage_context(by_id, chosen + extra, notes, document, _CONTEXT_CHARS)
        context = self._add_checks(document, context, given, notes)
        dropped = [i for i in chosen + extra if i not in kept]
        if dropped:
            self.on_event(f"{len(dropped)} passage(s) did not fit and were left out")
        self.labels = {by_id[i].page: by_id[i].section for i in reversed(kept) if by_id[i].section}
        answer = self._answer(context, question, language)
        # Run 31: passages left out by the budget were counted as read, so the second search never
        # returned to them; the answers to RA2 and RA4 were most likely in such passages.
        used = set(kept)
        if self._needs_search(answer) and not page_references(question, document):
            ranked = rank_passages(passages, question + " " + " ".join(keywords))
            more = [i for i in dropped if i not in used]
            more += [i for i, score in ranked if score > 0 and i not in used and i not in more]
            more = more[:6]
            if more:
                self.on_event(self._search_event(list(dict.fromkeys(by_id[i].page for i in more))))
                new_pages = [n for n in dict.fromkeys(by_id[i].page for i in more) if n not in notes]
                notes.update(self._look(document, new_pages, question))
                context, given, kept = self._passage_context(by_id, more + kept, notes, document, _CONTEXT_CHARS)
                context = self._add_checks(document, context, given, notes)
                answer = self._answer(context, question, language)
        return self._finish(document, answer, given, self._with_formulas(context), question, korean, start, notes)

    def _whole(self, document: Document, question: str, language: str) -> tuple[str, list[int], str]:
        limit = _PAPER_CHUNK_CHARS if document.dense else _CHUNK_CHARS
        chunks, current, size = [], [], 0
        for page in document.pages:
            if current and (size + len(page.text) > limit or len(current) >= 10):
                chunks.append(current)
                current, size = [], 0
            current.append(page.number)
            size += len(page.text)
        if current:
            chunks.append(current)
        self.on_event(f"whole document: {len(chunks)} part(s) summarised first, then combined")
        points = []
        for chunk in chunks:
            context = self._context(document, chunk, {}, limit)
            points.append(self._ask(MAP_PROMPT.format(language=language), context))
        while len(points) > 1 and estimate_tokens("\n\n".join(points)) > _REDUCE_TOKENS:
            groups, group = [], []
            for point in points:
                if group and estimate_tokens("\n\n".join(group + [point])) > _REDUCE_TOKENS:
                    groups.append(group)
                    group = []
                group.append(point)
            groups.append(group)
            if len(groups) == len(points):  # every part alone is too long: merge pairs
                groups = [points[i:i + 2] for i in range(0, len(points), 2)]
            self.on_event(f"key points too long for one call; merging {len(points)} part(s) into {len(groups)}")
            points = [self._ask(MERGE_PROMPT, "Key points:\n\n" + "\n\n".join(g)) if len(g) > 1 else g[0] for g in groups]
        task = EXAM_TASK if _EXAM.search(question) else f"Answer the user's request: {question}"
        combined = "\n\n".join(points)
        answer = self._ask(REDUCE_PROMPT.format(task=task, language=language), f"Key points:\n\n{combined}\n\nRequest: {question}")
        all_text = "\n".join(p.text for p in document.pages) + "\n" + "\n".join(self.captions.values())
        # Numbers are checked against the document itself, not against the intermediate summaries.
        return answer, [p.number for p in document.pages], all_text

    def _finish(self, document, answer, given, sources, question, korean, start, read: dict | None = None) -> str:
        t = _TEXT["ko" if korean else "en"]
        read = dict(read or {})
        for reading in self.formulas:  # equations read from the image count as read
            read[reading.page] = read.get(reading.page, "") + "\n" + formula_block(reading)
        answer, repeated = drop_repeated_paragraphs(answer)
        answer, corrected, expansions = repair_expansions(answer, "\n".join(p.text for p in document.pages))
        # Run 42: arithmetic done by the answer model was off in the last digit, and every computed
        # value was then flagged as not in the document. Results computed or checked by code count
        # as known numbers.
        answer, computed = fill_calculations(answer)
        answer, arithmetic_fixes, checked_results = check_arithmetic(answer)
        cited = cited_pages(answer)
        wrong = [n for n in cited if n not in given]
        known_text = sources + "\n" + " ".join(computed + checked_results + ["100", "1000"])
        numbers = unsupported_numbers(answer, known_text, question)
        if numbers:
            known = {n.replace(",", "") for n in _NUMBER.findall(known_text + " " + question)}
            answer, more_fixes, explained = explain_numbers(answer, numbers, known)
            arithmetic_fixes += more_fixes
            numbers = [n for n in numbers if n not in explained]
        page_texts = {n: document.page(n).text + "\n" + read.get(n, "") for n in given if document.page(n)}
        misplaced = misplaced_citations(answer, page_texts)
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
        # Run 38+: with two equations read, an answer that writes only one of them is fine. Each
        # formula in the answer is paired with the reading it is closest to; a reading is flagged
        # when some formula was aimed at it and none reproduces it (whole, or one side exactly).
        written = [b for b in re.findall(r"\$\$(.+?)\$\$", answer, re.S) if len(b.strip()) > 5]
        usable = [r for r in self.formulas if r.latex]
        aimed = set()
        for b in written:
            if usable:
                best = max(usable, key=lambda r: compare_latex(b, r.latex)[1])
                # Run 39, UN1: the PolyLoss formula was "aimed" at the Ricker wavelet read for the
                # same question. An unnumbered reading was found by its words, not named, so a
                # formula only counts as aimed at it when the two look alike.
                if best.number or compare_latex(b, best.latex)[1] >= 0.5:
                    aimed.add(id(best))
        for reading in self.formulas:
            name = (t["formula_name"].format(number=reading.number) if reading.number
                    else t["formula_unnumbered_name"].format(page=reading.page, after=" ".join(reading.before.split())[-30:]))
            notes.append(t["formula"].format(name=name, page=reading.page,
                                             status=t["formula_status"].get(reading.status, reading.status)))
            if id(reading) in aimed and not any(
                    compare_latex(b, reading.latex)[0] != "different" or is_part_of(b, reading.latex)
                    for b in written):
                notes.append(t["formula_changed"].format(name=name[:1].lower() + name[1:]))
        if wrong:
            notes.append(t["wrong_citation"].format(pages=", ".join(f"p.{n}" for n in wrong)))
        if numbers:
            notes.append(t["numbers"].format(numbers=", ".join(numbers)))
        if misplaced:
            notes.append(t["misplaced"].format(pairs=", ".join(t["pair"].format(cited=a, found=b) for a, b in misplaced)))
        if expansions:
            notes.append(t["expansions"].format(items=", ".join(expansions)))
        if arithmetic_fixes:
            notes.append(t["arithmetic_fixed"].format(items=", ".join(f"{e} = {w} → {c}" for e, w, c in arithmetic_fixes)))
        if computed:
            notes.append(t["computed"].format(count=len(computed)))
        if corrected:
            notes.append(t["expansions_fixed"].format(items=", ".join(
                f"{a}: {old} → {new or t['removed']}" for a, old, new in corrected)))
        used = [n for n in cited if n in given]
        source_line = t["sources"] + ", ".join(
            f"p.{n} ({(self.labels.get(n) or document.page(n).title or self.captions.get(n, ''))[:50]})" for n in used[:8]
        ) if used else ""
        self.on_event(
            f"check: {len(used)} cited page(s)"
            + (f", {len(wrong)} citation(s) to pages not given" if wrong else "")
            + (f", {len(numbers)} number(s) not in the document" if numbers else "")
            + (f", {len(misplaced)} citation(s) to another page" if misplaced else "")
            + (f", {len(expansions)} expansion(s) not in the document" if expansions else "")
            + (f", {len(corrected)} expansion(s) corrected" if corrected else "")
            + (f", {repeated} repeated paragraph(s) removed" if repeated else "")
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
        "misplaced": "⚠ 출처 페이지가 틀렸을 수 있습니다: {pairs}.",
        "formula": "{name}은 p.{page}의 이미지에서 두 번 읽었습니다: {status}.",
        "formula_name": "수식 ({number})",
        "formula_unnumbered_name": "p.{page}의 번호 없는 수식(\"...{after}\" 다음)",
        "formula_status": {"confirmed": "두 번 일치", "close": "거의 일치 (세부는 불확실)", "disagree": "불일치 (불확실)",
                           "check_failed": "두 번 일치했지만 확인 단계에서 문제 제기 (불확실)", "unreadable": "읽지 못함"},
        "formula_changed": "⚠ 답에 쓴 수식이 이미지에서 읽은 {name}과 다릅니다.",
        "pair": "p.{cited}로 표시한 문장이 p.{found}에 있습니다",
        "expansions": "⚠ 문서에 없는 약어 풀이가 있습니다: {items}. 모델이 덧붙인 것이라 틀릴 수 있습니다.",
        "expansions_fixed": "약어 풀이를 문서의 표현으로 고쳤습니다: {items}.",
        "arithmetic_fixed": "답에 있던 계산 결과를 코드로 다시 계산해 고쳤습니다: {items}.",
        "computed": "계산 {count}개는 코드로 했습니다.",
        "removed": "(삭제, 문서에 정의 없음)",
    },
    "en": {
        "sources": "Sources: ",
        "no_citation": "⚠ The answer has no page citations; it may not come from the document.",
        "wrong_citation": "⚠ The answer cites pages that were not given: {pages}. Check those statements.",
        "numbers": "⚠ Numbers in the answer that do not appear in the document: {numbers}. They may be invented.",
        "not_covered": "(The answer says the document does not cover this. Pages checked: {pages})",
        "unread_equations": "⚠ The equations in this answer were written without reading the original page ({pages}). Check them against the document.",
        "misplaced": "⚠ A citation may point to the wrong page: {pairs}.",
        "formula": "{name} was read twice from the image of p.{page}: {status}.",
        "formula_name": "Equation ({number})",
        "formula_unnumbered_name": "The unnumbered equation on p.{page} (after \"...{after}\")",
        "formula_status": {"confirmed": "the readings agree", "close": "the readings nearly agree (details uncertain)",
                           "disagree": "the readings disagree (uncertain)",
                           "check_failed": "the readings agree, but the check against the image raised a problem (uncertain)",
                           "unreadable": "not readable"},
        "formula_changed": "⚠ The equation written in the answer differs from {name} as read from the image.",
        "pair": "a sentence cited to p.{cited} is on p.{found}",
        "expansions": "⚠ Abbreviations spelled out in a way the document never uses: {items}. The model added these and they may be wrong.",
        "expansions_fixed": "Abbreviations spelled out in a way the document never uses were corrected to the document's: {items}.",
        "arithmetic_fixed": "A calculation in the answer was redone by code and corrected: {items}.",
        "computed": "{count} calculation(s) were done by code.",
        "removed": "(removed; the document gives no definition)",
    },
}
