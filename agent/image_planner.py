"""Code-level planner for questions about an image.

Runs 13-17 showed that the 8B main model ignores planning rules written in prompts:
it sent one multi-part question to every zoomed view, skipped parts of the question,
read the same item twice, and stated one reading as fact when two readings differed.
Here those rules are enforced in code:

1. Plan     The main model splits the question into parts. Ollama structured outputs
            force the reply into a JSON schema, so the plan always has the same shape.
            Code checks that the plan covers the question (labels such as CS or OLED, a
            request to describe) and asks for a new plan once if it does not. Parts with
            the same focus are merged into one look-up.
2. Execute  Code calls one vision tool per part. A part cannot be skipped.
            A request for an exact name or number always uses the two-reading tool.
            A focus that cannot be located is retried once on the whole image;
            a zoomed answer that says "not shown" is retried once with a wider view, and
            an answer from that retry is marked as not verified.
3. Check    Code verifies that every part has a result and counts "not shown" answers.
4. Answer   Code assembles the answer from the vision results. Unconfirmed readings
            are always shown with both versions; the model cannot pick one.

Accurate mode (PlannerOptions) adds three checks that trade time for accuracy, the way a
link adds redundancy instead of accepting errors:

- verify      every factual answer is asked again on a second, different view and code
              compares the short answers; a disagreement gets a third look and a majority vote
- scan_tiles  a large image is transcribed in four zoomed tiles first, and the text is given
              to the vision model with whole-image questions
- reasoning   counting, comparing and chart questions go to the thinking vision model

Questions without an image path go to the normal agent loop.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .llm import LLMError
from .vision_tools import IMAGE_EXTENSIONS, located_by_echo, same_answer, widened_region

_IMAGE_PATH = re.compile(r"(\S+\.(?:" + "|".join(e.lstrip(".") for e in IMAGE_EXTENSIONS) + r"))\b", re.IGNORECASE)
_HANGUL = re.compile(r"[가-힣]")
_QUOTED = re.compile(r"[\"“”‘’「」]")  # not the plain apostrophe: "it's" is not a quotation
MAX_PARTS = 8  # Run 19: with 6, the 8B planner split SD card pins into four parts and dropped OLED
_WIDER_VIEW = 0.4  # retry view: at least 40% of the image width and height around the first focus

# Run 18: the 8B planner chose describe for "전압 레귤레이터 부품명" and the single reading
# came back cut off as "AMS1117-". Exact names and numbers go to the two-reading tool.
_EXACT_TEXT = re.compile(
    r"부품명|부품 번호|모델명|제품명|상호|전화번호|가격|part number|model number|product name|phone number|price",
    re.IGNORECASE,
)
_CONNECTION = re.compile(r"연결|핀|배선|pin|connect|wired", re.IGNORECASE)

# Run 18: two zoomed answers said the pins were "not shown", and the check still counted them
# as answered. Only the first sentence is checked: "the date is not shown" later in a time
# answer is a normal answer, not a failed look-up.
_NOT_SHOWN = re.compile(
    r"보이지 않|보여주지 않|보여 주지 않|나타나 있지 않|표시되어 있지 않|표시돼 있지 않|표시되지 않|나와 있지 않|정보가 없|찾을 수 없|확인할 수 없"
    r"|not shown|not visible|does not show|doesn't show|do not see|don't see|cannot see|can't see|no information|not in (this|the) image",
    re.IGNORECASE,
)


def says_not_shown(answer: str) -> bool:
    first = re.split(r"(?<=[.!?。])\s+|\n+", answer.strip(), maxsplit=1)[0]
    return bool(_NOT_SHOWN.search(first))


# Run 19: the 8B plan dropped OLED (SDA, SCL). Code cannot judge meaning, but it can check that
# labels written in capitals or with digits (CS, OLED, AMS1117) appear in the plan.
# Run 21: a check for "a request to describe" was removed: "왜 웃긴지 설명해 줘" (explain why it is
# funny) was taken as a request to describe the whole image and produced a false warning.
_LABEL_TERM = re.compile(r"(?<![A-Za-z0-9])(?=[A-Z0-9-]*[A-Z])[A-Z][A-Z0-9-]*[A-Z0-9](?![A-Za-z0-9])|(?<![A-Za-z0-9])[A-Z]+\d+[A-Z0-9-]*")
# Words that name a kind of answer, not a thing to look up ("연결된 GPIO 핀").
_GENERIC_TERMS = {"GPIO", "PCB", "PDF", "JPG", "PNG", "OK"}

# Run 21: questions about the image as a whole were zoomed into a small piece of it: "how many
# fish" looked at one fish, "which modulation needs the lowest Eb/N0" at one corner of the chart,
# "the flow of the conversation" and "why it is funny" at the first comment. Such parts are always
# answered from the whole image.
_WHOLE_IMAGE_QUESTION = re.compile(
    r"how many|\bcount|number of|몇 ?(개|마리|명|대|장)|개수|"
    r"compare|comparison|lowest|highest|\bmost\b|\bleast\b|fastest|slowest|가장|제일|비교|"
    r"\bflow\b|흐름|\bwhy\b|왜|funny|humou?r|joke|웃|\bfeel|emotion|기분|감정|느낌|mood|분위기|atmosphere|"
    r"\bstyle\b|스타일|그림체|화풍|summar|요약|overall|전반|layout|배치|구성|"
    r"what does (this|the) (chart|graph|image|picture|photo|diagram) show|무엇을 (보여|설명)",
    re.IGNORECASE,
)


# Runs 18-20: every focus written as a request ("OLED interface (SDA, SCL)") came back with the
# request itself as the "printed label", and every answer from that view was wrong or "not shown".
# A focus matched to a real printed label ("Micro SD Card", "ESP-WROOM-32") was right each time.
# Run 22: "the text of the comments" was read as one short text and only the first comment came
# back. Conversations, threads and pages are long text: they are transcribed from the whole image.
_LONG_TEXT = re.compile(
    r"comments|messages|conversation|thread|chat|paragraph|page|document|body text|transcri|"
    r"댓글|대화|메시지|문단|본문|페이지|전문",
    re.IGNORECASE,
)

# Run 21: only a bracket after a space is a list; "log10(Pb)" must stay as it is.
_BRACKETS = re.compile(r"\s+[(\[][^)\]]*[)\]]")


def clean_focus(focus: str) -> str:
    """Drop lists in brackets: "OLED interface (SDA, SCL)" → "OLED interface"."""
    cleaned = _BRACKETS.sub("", focus).strip()
    return cleaned or focus


def plan_misses(question: str, parts: list["Part"]) -> list[str]:
    """Things the question asks for that no planned part mentions."""
    planned = " ".join(f"{p.item} {p.focus} {p.question}" for p in parts)
    misses = []
    for term in dict.fromkeys(_LABEL_TERM.findall(question)):
        if term.upper() in _GENERIC_TERMS:
            continue
        if not re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", planned, re.IGNORECASE):
            misses.append(term)
    return misses


def merge_same_focus(parts: list["Part"]) -> tuple[list["Part"], list[str]]:
    """Merge parts that look at the same thing into one look-up.

    Run 19: the 8B plan asked about each SD card pin separately, four views of the same module,
    and one pin came back wrong. 14B asked about all four pins in one view and got all of them.
    """
    merged: list[Part] = []
    by_key: dict[tuple[str, str], Part] = {}
    notes = []
    for part in parts:
        key = (part.kind, part.focus.strip().lower())
        # Run 21: whole-image parts are merged too. "Summarize", "who says what" and "why is it
        # funny" were three separate looks at the same image; one look keeps the context together.
        if part.kind == "read_text" and not key[1]:
            merged.append(part)
            continue
        if key not in by_key:
            merged.append(part)
            by_key[key] = part
            continue
        first = by_key[key]
        first.item = f"{first.item} + {part.item}"
        first.question = f"{first.question} {part.question}"
        first.questions += part.questions
        where = f"the same '{part.focus}'" if part.focus else "the whole image"
        notes.append(f"'{part.item}' looks at {where} as an earlier part; asked together")
    return merged, notes

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_PARTS,
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "kind": {"type": "string", "enum": ["describe", "read_text"]},
                    "focus": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["item", "kind", "focus", "question"],
            },
        }
    },
    "required": ["parts"],
}

# The examples are deliberately different from the evaluation images (evals/vision),
# so the planner is not tuned to the test set.
PLAN_PROMPT = """Split the user's question about an image into parts: one part for each thing to look up.
You cannot see the image. Another model will look at it, one part at a time.

For each part give:
- item: a short name for the part, in the user's language
- kind: "read_text" for one short exact text (a sign or brand name, a phone number, a label, a price, a title); "describe" for everything else (a scene, a layout, a mood, a connection, a value in a diagram)
- focus: for "describe", the visible thing to zoom into: a component, a module, a sign, a chart legend. Use the text printed on it if you can guess it (usually English part names or labels). For pins or connections of a module, focus on the module itself, not on the pins. Never write a question or a list of pins as the focus. "" for the whole image or the whole scene. For "read_text", where the text is and what kind of text it is. Never write the answer you expect.
- question: in the user's language, asking only about this part

Ask about several things in the same place in one part (for example all pins of one module).
Questions about the image as a whole (a summary, a scene, counting, comparing, the flow of a conversation, why something is funny, feelings, style) are one part with focus "".
For "read_text", name one specific text and where it is (for example "the large sign on the right building"), not "any text".
Cover everything the user asked for. Keep the user's order. At most 8 parts. Return only JSON.

Example question: "이 아두이노 보드의 마이크로컨트롤러는 뭐고, USB 칩 이름과 그 칩의 TX, RX 핀 연결, 전원 잭 입력 전압은?"
Example answer: {"parts": [
 {"item": "마이크로컨트롤러", "kind": "describe", "focus": "ATmega328P microcontroller", "question": "이 칩은 어떤 마이크로컨트롤러야?"},
 {"item": "USB 칩", "kind": "read_text", "focus": "the part number on the USB interface chip", "question": "USB 칩 이름은?"},
 {"item": "USB 칩 TX, RX 연결", "kind": "describe", "focus": "USB interface chip", "question": "이 칩의 TX, RX 핀은 각각 어디에 연결돼 있어?"},
 {"item": "전원 잭 입력 전압", "kind": "describe", "focus": "DC power jack", "question": "전원 잭 옆에 표시된 입력 전압은?"}]}

Example question: "Describe the mood of this cafe and read the price of an americano on the menu board."
Example answer: {"parts": [
 {"item": "Cafe mood", "kind": "describe", "focus": "", "question": "Describe the mood of this cafe."},
 {"item": "Americano price", "kind": "read_text", "focus": "the americano line on the menu board", "question": "What is the price of an americano?"}]}"""


@dataclass
class Part:
    item: str
    kind: str
    focus: str
    question: str
    questions: list[str] = field(default_factory=list)  # the original sub-questions, kept when parts merge

    def __post_init__(self) -> None:
        if not self.questions:
            self.questions = [self.question]


@dataclass
class PlannerOptions:
    verify: bool = False
    scan_tiles: bool = False
    reasoning_vision: bool = False


# Questions whose answer is open prose (a summary, an explanation, a transcription). Two
# independent short answers to these differ in wording even when both are right, so they
# are not compared.
_OPEN_ENDED = re.compile(
    r"describe|description|summar|explain|\bwhy\b|what is happening|what does (this|the) \w+ show|transcri|"
    r"\bread\b|\blist\b|organi[sz]e|who says what|\bmood\b|atmosphere|\bstyle\b|layout|\bflow\b|"
    r"설명|요약|왜|묘사|무슨 일|읽어|받아 적|정리|분위기|스타일|그림체|배치|구성|흐름|누가 (뭐|무슨)",
    re.IGNORECASE,
)


def _expand(region: str, margin: float) -> str:
    try:
        left, top, right, bottom = (float(v) for v in region.split(","))
    except ValueError:
        return "full"
    return ",".join(
        f"{v:.4f}" for v in (max(0.0, left - margin), max(0.0, top - margin), min(1.0, right + margin), min(1.0, bottom + margin))
    )


def find_image_path(text: str, workspace: Path) -> str | None:
    """The first image path in the question that exists inside the workspace."""
    # Resolve the workspace too: on macOS /var is a link to /private/var, so an
    # unresolved workspace never matches the resolved image path.
    workspace = workspace.resolve()
    for match in _IMAGE_PATH.finditer(text):
        candidate = match.group(1).strip("'\"()[]<>,")
        try:
            resolved = (workspace / candidate).resolve()
        except OSError:
            continue
        if resolved.is_file() and (resolved == workspace or workspace in resolved.parents):
            return candidate
    return None


def parse_plan(raw: str, question: str) -> tuple[list[Part], bool]:
    """Validate the planner's JSON. Returns (parts, ok). Falls back to one whole-image part."""
    try:
        data = json.loads(raw)
        items = data["parts"] if isinstance(data, dict) else data
        parts = []
        for entry in items[:MAX_PARTS]:
            item = str(entry.get("item", "")).strip()
            q = str(entry.get("question", "")).strip()
            if not item or not q:
                continue
            kind = entry.get("kind") if entry.get("kind") in ("describe", "read_text") else "describe"
            parts.append(Part(item=item, kind=kind, focus=str(entry.get("focus", "")).strip(), question=q))
        if parts:
            return parts, True
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return [Part(item="", kind="describe", focus="", question=question)], False


class ImageQuestionPlanner:
    def __init__(
        self,
        llm,
        registry,
        workspace: Path,
        on_tool_call: Callable[[str, dict, str], None] | None = None,
        on_event: Callable[[str], None] | None = None,
        options: PlannerOptions | None = None,
    ) -> None:
        self.llm = llm
        self.vision = registry.vision
        self.options = options or PlannerOptions()
        self.workspace = workspace.resolve()
        self.on_tool_call = on_tool_call or (lambda name, args, result: None)
        self.on_event = on_event or (lambda message: None)
        self.uncovered: list[str] = []

    def applies(self, question: str) -> str | None:
        if self.vision is None:
            return None
        return find_image_path(question, self.workspace)

    def plan(self, question: str, path: str) -> list[Part]:
        user_question = question.replace(path, "").strip()
        messages = [{"role": "system", "content": PLAN_PROMPT}, {"role": "user", "content": user_question}]
        try:
            response = self.llm.chat(messages, format=PLAN_SCHEMA)
        except LLMError:
            if not getattr(self.llm, "think", False):
                raise
            # Thinking together with a JSON schema may not be supported; plan without thinking.
            self.on_event("planning with thinking failed; planning without it")
            self.llm.think = False
            response = self.llm.chat(messages, format=PLAN_SCHEMA)
        raw = response["message"].get("content") or ""
        parts, ok = parse_plan(raw, user_question)
        if not ok:
            self.on_event("plan could not be read; asking the whole question about the whole image")
        self.uncovered = plan_misses(user_question, parts) if ok else []
        if self.uncovered:
            missing = ", ".join(self.uncovered)
            self.on_event(f"plan does not cover: {missing}; asking for a new plan")
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Your plan leaves out: {missing}. Return the complete plan again, with parts for these too."},
            ]
            retry = self.llm.chat(messages, format=PLAN_SCHEMA)
            new_parts, new_ok = parse_plan(retry["message"].get("content") or "", user_question)
            if new_ok:
                parts = new_parts
                self.uncovered = plan_misses(user_question, parts)
            if self.uncovered:
                self.on_event(f"still not covered: {', '.join(self.uncovered)}; reported in the answer")
        for part in parts:
            if part.kind == "read_text" and _LONG_TEXT.search(f"{part.item} {part.focus}") and not _EXACT_TEXT.search(part.item):
                self.on_event(f"'{part.item}' is long text (comments, a conversation, a page); read from the whole image")
                part.kind, part.focus = "describe", ""
            if part.kind == "describe" and part.focus and _WHOLE_IMAGE_QUESTION.search(f"{part.item} {part.question}"):
                self.on_event(f"'{part.item}' is about the whole image (counting, comparing, flow, feeling, style); no zoom")
                part.focus = ""
            if part.kind == "describe" and part.focus:
                cleaned = clean_focus(part.focus)
                if cleaned != part.focus:
                    self.on_event(f"focus '{part.focus}' shortened to '{cleaned}' (a list in brackets is not a thing to find)")
                    part.focus = cleaned
        parts, notes = merge_same_focus(parts)
        for note in notes:
            self.on_event(note)
        for part in parts:
            text = f"{part.item} {part.question}"
            if part.kind == "describe" and part.item and _EXACT_TEXT.search(text) and not _CONNECTION.search(text):
                part.kind = "read_text"
                self.on_event(f"'{part.item}' asks for an exact name or number; using read_text_in_image")
        return parts

    def run(self, question: str) -> str | None:
        path = self.applies(question)
        if path is None:
            return None
        korean = bool(_HANGUL.search(question))
        start = time.perf_counter()
        parts = self.plan(question, path)
        plan_seconds = time.perf_counter() - start
        self.on_event(
            f"plan: {len(parts)} part(s) - " + " / ".join(p.item or "whole question" for p in parts)
            + f" ({plan_seconds:.1f} s)"
        )

        results = []
        for part in parts:
            results.append((part, self._execute(path, part)))

        self._mark_duplicates(results)
        missing = sum(1 for _, r in results if r.get("status") in ("not_located", "not_shown", "not_found"))
        uncertain = sum(1 for _, r in results if r.get("status") in _NOT_CONFIRMED)
        summary = f"check: {len(parts) - missing}/{len(parts)} parts answered"
        if missing:
            summary += f", {missing} not found in the image"
        if uncertain:
            summary += f", {uncertain} not confirmed (shown with both readings or marked)"
        if self.uncovered:
            summary += f", not planned: {', '.join(self.uncovered)}"
        summary += f" | total {time.perf_counter() - start:.1f} s"
        self.on_event(summary)
        return self._compose(results, korean)

    def _execute(self, path: str, part: Part) -> dict:
        if part.kind == "read_text":
            target = part.focus or part.item
            result = self.vision.read_text(path, target)
            self.on_tool_call("read_text_in_image", {"path": path, "target": target}, result["text"])
            no_text = result.get("readings") and all(r == "[no text]" for r in result["readings"])
            if no_text:
                # Run 22: a key signature is symbols, not text, so both readings were "[no text]".
                self.on_event(f"'{target}' has no readable text; asking about the whole image instead")
            elif result["status"] != "not_located":
                return result
            else:
                self.on_event(f"'{target}' was not located; asking about the whole image instead")
            # Fall back to the whole image: a general description can fail to locate.
            fallback = self.vision.describe(
                path, part.question, scan_notes=self._scan_notes(path), reasoning=self._reasoning(part)
            )
            self.on_tool_call("describe_image", {"path": path, "question": part.question}, fallback["text"])
            if fallback["status"] == "ok":
                # Run 21: "Not shown." from the whole image is an answer, not an unverified finding.
                fallback["status"] = "not_shown" if says_not_shown(fallback["answer"]) else "unverified"
            self._verify(path, part, fallback)
            return fallback

        whole = not part.focus
        result = self.vision.describe(
            path, part.question, part.focus, strict=True,
            scan_notes=self._scan_notes(path) if whole else "", reasoning=whole and self._reasoning(part),
        )
        self.on_tool_call("describe_image", {"path": path, "question": part.question, "focus": part.focus}, result["text"])
        if result["status"] == "not_located" and part.focus:
            if result.get("echo"):
                self.on_event(f"'{part.focus}' matched no printed label, only a small spot; asking about the whole image instead")
            else:
                self.on_event(f"focus '{part.focus}' was not located; retrying on the whole image")
            result = self.vision.describe(
                path, part.question, scan_notes=self._scan_notes(path), reasoning=self._reasoning(part)
            )
            self.on_tool_call("describe_image", {"path": path, "question": part.question}, result["text"])
            if result["status"] == "ok" and not says_not_shown(result["answer"]):
                result["status"] = "unverified"
        elif result["status"] == "ok" and result.get("box") and says_not_shown(result["answer"]):
            # The zoomed view may have missed the part: look once more with a wider view around it.
            region = widened_region(result["box"], _WIDER_VIEW)
            self.on_event(f"the zoomed view of '{part.focus}' did not show it; retrying with a wider view")
            result = self.vision.describe(path, part.question, region=region, scan_notes=self._scan_notes(path))
            result["widened"] = True
            self.on_tool_call("describe_image", {"path": path, "question": part.question, "region": region}, result["text"])
            if result["status"] == "ok" and not says_not_shown(result["answer"]):
                # Run 19: the first view honestly said "not shown"; the wider view then answered
                # "SDA G23, SCL G24" with confidence (G24 does not exist). An answer that appears
                # only after a miss is not trusted as a finding.
                result["status"] = "unverified_wider"
        if result["status"] == "ok" and says_not_shown(result["answer"]):
            result["status"] = "not_shown"
        self._verify(path, part, result)
        return result

    # --- accurate mode -------------------------------------------------------------------

    def _reasoning(self, part: Part) -> bool:
        return (
            self.options.reasoning_vision and getattr(self.vision, "has_reasoning", False)
            and bool(_WHOLE_IMAGE_QUESTION.search(" ".join(part.questions)))
        )

    def _scan_notes(self, path: str) -> str:
        if not self.options.scan_tiles or not hasattr(self.vision, "scan"):
            return ""
        first = path not in getattr(self, "_scanned", set())
        result = self.vision.scan(path)
        if first:
            self._scanned = getattr(self, "_scanned", set()) | {path}
            if result["tiles"]:
                lines = len(result["notes"].splitlines()) if result["notes"] else 0
                self.on_event(f"tile scan: {lines} text line(s) from {result['tiles']} zoomed tiles ({result['seconds']:.1f} s)")
            else:
                self.on_event(f"tile scan skipped: {result['reason']}")
        return result["notes"]

    def _verify(self, path: str, part: Part, result: dict) -> None:
        """Ask the factual sub-questions again on two views and compare the short answers in code."""
        if not self.options.verify or result.get("status") not in ("ok", "unverified", "unverified_wider"):
            return
        questions = [q for q in part.questions if not _OPEN_ENDED.search(q)]
        if not questions:
            return
        start = time.perf_counter()
        region = result.get("region") or "full"
        whole = region == "full"
        first = self.vision.brief(path, questions, region=region)
        # The second view must differ: more pixels for the whole image, more context for a zoom.
        second = self.vision.brief(path, questions, scale=1.35) if whole else self.vision.brief(
            path, questions, region=_expand(region, 0.15)
        )
        checks, calls = [], 2
        disputed = [i for i, q in enumerate(questions) if not same_answer(first["answers"][i], second["answers"][i])]
        third = None
        if disputed:
            reasoning = self.options.reasoning_vision and getattr(self.vision, "has_reasoning", False)
            third = self.vision.brief(
                path, [questions[i] for i in disputed], region=region, scale=1.0 if reasoning else 1.15, reasoning=reasoning
            )
            calls += 1
        for i, question in enumerate(questions):
            a, b = first["answers"][i], second["answers"][i]
            if i not in disputed:
                checks.append({"question": question, "verdict": "agree", "answer": a or b, "answers": [a, b]})
                continue
            c = third["answers"][disputed.index(i)]
            if same_answer(c, a):
                checks.append({"question": question, "verdict": "majority", "answer": a, "answers": [a, b, c], "first": True})
            elif same_answer(c, b):
                checks.append({"question": question, "verdict": "majority", "answer": b, "answers": [a, b, c], "first": False})
            else:
                checks.append({"question": question, "verdict": "disagree", "answer": "", "answers": [a, b, c]})
        result["checks"] = checks
        counts = {v: sum(1 for c in checks if c["verdict"] == v) for v in ("agree", "majority", "disagree")}
        self.on_event(
            f"verify '{part.item}': {counts['agree']} agree, {counts['majority']} by majority, "
            f"{counts['disagree']} disagree ({calls} looks, {time.perf_counter() - start:.1f} s)"
        )
        if counts["disagree"] or any(c["verdict"] == "majority" and not c["first"] for c in checks):
            result["status"] = "uncertain_answer"

    def _mark_duplicates(self, results: list[tuple[Part, dict]]) -> None:
        """Two different parts that read the same text: at least one of them looked in the wrong place.

        Run 22: "the artist name" and "the instrument name" were both read as "Guitar/Ukulele".
        """
        seen: dict[str, Part] = {}
        for part, result in results:
            if result.get("status") not in ("confirmed", "format_differs", "cut_off") or not result.get("readings"):
                continue
            key = "".join(ch for ch in result["readings"][0].lower() if ch.isalnum())
            if not key or key == "notext":
                continue
            if key in seen:
                first = seen[key]
                self.on_event(f"'{first.item}' and '{part.item}' read the same text; at least one is in the wrong place")
                for p, r in results:
                    if p is first or p is part:
                        r["duplicate_of"] = part.item if p is first else first.item
                        r["status"] = "uncertain_place"
            else:
                seen[key] = part

    @staticmethod
    def _check_lines(checks: list[dict], t: dict) -> str:
        lines = [t["verify_head"]]
        for c in checks:
            if c["verdict"] == "agree":
                lines.append(f"- ✔ {c['question']} → {c['answer']}")
            elif c["verdict"] == "majority":
                note = "" if c["first"] else f" {t['verify_differs']}"
                lines.append(f"- ✔ {c['question']} → {c['answer']} {t['verify_majority']}{note}")
            else:
                lines.append(f"- ⚠ {c['question']} → {t['verify_disagree']}: " + " / ".join(a or '-' for a in c["answers"]))
        return "\n".join(lines)

    @staticmethod
    def _clean(answer: str) -> tuple[str, bool]:
        lines, warned = [], False
        for line in answer.splitlines():
            if line.strip().startswith("[warning:"):
                warned = True
                continue
            lines.append(line)
        return "\n".join(lines).strip(), warned

    def _compose(self, results: list[tuple[Part, dict]], korean: bool) -> str:
        t = _TEXT["ko" if korean else "en"]
        sections = []
        for part, result in results:
            status = result.get("status")
            if status in ("ok", "unverified", "unverified_wider", "not_shown", "uncertain_answer"):
                body, warned = self._clean(result.get("answer", ""))
                if status == "unverified":
                    body = f"{t['unverified']}\n{body}"
                if status == "unverified_wider":
                    body = f"{t['unverified_wider']}\n{body}"
                if status == "not_shown":
                    body += f"\n{t['not_shown_wider'] if result.get('widened') else t['not_shown']}"
                if warned:
                    body += f"\n{t['cut']}"
            elif status == "confirmed" and result["readings"][0] == "[no text]":
                body = t["no_text"]
            elif status == "confirmed":
                body = result["readings"][0]
                if result.get("nearby"):
                    body += f"\n{t['nearby'].format(lines=' / '.join(result['nearby']))}"
            elif status == "uncertain_place":
                body = f"{result['readings'][0]}\n{t['duplicate'].format(other=result['duplicate_of'])}"
            elif status == "cut_off":
                shorter, longer = sorted(result["readings"], key=len)
                body = f"{longer}\n{t['cut_off'].format(short=' '.join(shorter.split()))}"
            elif status == "format_differs":
                first, second = result["readings"]
                body = f"{second}\n{t['format_differs'].format(other=' '.join(first.split()))}"
            elif status == "partly_unclear":
                body = f"{result['readings'][0]}\n{t['partly']}"
            elif status == "uncertain":
                first, second = (t["no_text"] if r == "[no text]" else r for r in result["readings"])
                body = f"{t['uncertain']}\n- {t['reading']} 1: {first}\n- {t['reading']} 2: {second}"
            elif status == "not_found":
                body = t["not_found"]
            else:
                body = t["not_located"]
            if result.get("checks"):
                body += "\n" + self._check_lines(result["checks"], t)
            sections.append(f"**{part.item}**\n{body}" if part.item else body)

        # Run 18: the scene description quoted the sign as "푸르지오 건담" while the two-reading
        # tool confirmed "푸르지오강남". Point to the checked reading instead of leaving both unexplained.
        read = [p.item for p, r in results if r.get("status") in _TWO_READINGS and p.item]
        quoted = any(
            r.get("status") in ("ok", "unverified", "unverified_wider") and _QUOTED.search(r.get("answer", ""))
            for _, r in results
        )
        if read and quoted:
            sections.append(t["text_note"].format(items=", ".join(f"'{i}'" for i in read)))
        if self.uncovered:
            sections.append(t["uncovered"].format(items=", ".join(self.uncovered)))
        return "\n\n".join(sections)


_NOT_CONFIRMED = ("uncertain", "uncertain_place", "uncertain_answer", "partly_unclear", "cut_off", "unverified", "unverified_wider")
_TWO_READINGS = ("confirmed", "format_differs", "cut_off", "partly_unclear", "uncertain", "uncertain_place")


_TEXT = {
    "ko": {
        "uncertain": "⚠ 확실하지 않음: 두 번 읽은 결과가 다릅니다.",
        "no_text": "(읽을 수 있는 글자가 없습니다.)",
        "verify_head": "검증 (다른 화면으로 다시 본 짧은 답):",
        "verify_majority": "(세 번 중 두 번 일치)",
        "verify_differs": "⚠ 위 설명과 다를 수 있습니다",
        "verify_disagree": "볼 때마다 답이 달라 확인하지 못했습니다",
        "nearby": "(넓은 화면에는 주변 글자도 보였습니다: {lines})",
        "duplicate": "⚠ 위치 확인 필요: '{other}' 항목에서도 같은 글자가 읽혔습니다. 둘 중 하나는 엉뚱한 곳을 읽었을 수 있습니다.",
        "reading": "읽기",
        "partly": "(일부 글자는 흐려서 ?로 표시했습니다)",
        "not_found": "이미지에서 찾을 수 없습니다.",
        "not_located": "이미지에서 위치를 찾지 못해 확인하지 못했습니다.",
        "unverified": "(정확한 위치를 찾지 못해 전체 이미지에서 확인한 내용입니다. 확대 확인은 하지 않았습니다.)",
        "cut": "(주의: 답이 길이 제한이나 반복 때문에 잘렸을 수 있습니다.)",
        "not_shown": "(눈 모델이 이미지에서 찾지 못했다고 답했습니다.)",
        "not_shown_wider": "(확대한 화면과 더 넓은 화면 모두에서 찾지 못했습니다.)",
        "text_note": "※ 설명 항목에 나온 글자는 한 번만 읽은 결과라 틀릴 수 있습니다. 정확한 글자는 두 번 읽어 비교한 {items} 항목을 따르세요.",
        "unverified_wider": "⚠ 확인되지 않음: 처음 확대한 화면에서는 보이지 않아 더 넓은 화면에서 다시 본 결과입니다. 틀렸을 수 있습니다.",
        "format_differs": "(글자와 숫자는 두 번 모두 같고, 괄호·하이픈 같은 표기만 다르게 읽혔습니다. 다른 표기: {other})",
        "cut_off": "(⚠ 일부만 확인됨: 좁은 화면 읽기는 '{short}'까지만 보였습니다. 겹치는 부분은 두 번 모두 같지만 나머지는 한 번만 읽혔습니다.)",
        "uncovered": "※ 질문 중 다음 부분은 계획에 들어가지 않아 확인하지 못했습니다: {items}. 따로 다시 물어봐 주세요.",
    },
    "en": {
        "uncertain": "⚠ Uncertain: the two readings differ.",
        "no_text": "(No readable text.)",
        "verify_head": "Check (short answers from separate looks):",
        "verify_majority": "(two of three looks agree)",
        "verify_differs": "⚠ this may differ from the description above",
        "verify_disagree": "the answer changed between looks, so it is not confirmed",
        "nearby": "(The wider view also showed nearby text: {lines})",
        "duplicate": "⚠ Check the place: '{other}' read the same text, so one of the two may have looked in the wrong place.",
        "reading": "Reading",
        "partly": "(Some characters were unclear and are shown as ?.)",
        "not_found": "Not found in the image.",
        "not_located": "Could not locate this in the image, so it was not checked.",
        "unverified": "(Not located precisely; answered from the whole image without a zoomed check.)",
        "cut": "(Note: the answer may have been cut off by the length limit or a repetition.)",
        "not_shown": "(The vision model said it is not in the image.)",
        "not_shown_wider": "(Not found in the zoomed view or in a wider view.)",
        "text_note": "Note: text quoted in the descriptions was read only once and may be wrong. For exact text, use {items}, which was read twice and compared.",
        "unverified_wider": "⚠ Not verified: the first zoomed view did not show this, so it was looked at again in a wider view. It may be wrong.",
        "format_differs": "(Both readings have the same letters and digits; only punctuation such as brackets or hyphens differs. Other form: {other})",
        "cut_off": "(⚠ Partly confirmed: the tight reading stopped at '{short}'. The overlapping part agrees in both readings; the rest was read once.)",
        "uncovered": "Note: these parts of the question were not in the plan and were not checked: {items}. Please ask about them separately.",
    },
}
