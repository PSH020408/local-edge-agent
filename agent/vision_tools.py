"""Vision tool: lets the text-only main model "see" images through a vision model.

Design (same rule as the other tools): the main model decides, a specialist executes.
The main model never receives image data. It calls describe_image with a file path
and a question; this module prepares the image and asks a separate vision model
(qwen3-vl by default) through Ollama, then returns plain text.

Image preparation matters for speed. A 1932x2576 phone photo cost 4,044 prompt
tokens and 23 s of the 30 s total before any answer was written, so images are
downscaled to a configurable longest side before they are sent.
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from pathlib import Path
from typing import Callable, Protocol

from .tools import ToolRegistry

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_MAX_FILE_BYTES = 50 * 1024 * 1024
_MAX_ZOOM_UPSCALE = 3.0
_SMALL_IMAGE_SIDE = 768  # full images with a longer side below this are enlarged (at most 2x)

VISION_SYSTEM_PROMPT = """You are the vision component of a local assistant.
Describe only what is actually visible in the image.
- Read text exactly as written. Keep the original language.
- If text is too small, blurry or cut off to read, say so instead of guessing.
- If the question asks about something that is not in the image, say it is not shown.
- Do not invent names, numbers or details.
- Keep what you see separate from what you guess. A word on a sign or a business name is not evidence of the location. If you guess a place or time, say it is a guess and give the visible evidence.
- In schematics, a signal or GPIO name is the label written next to a pin or wire (such as G05, SDA, TXD), not the pin number of the part.
Answer in the language of the question."""


class ChatModel(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict: ...


@dataclass
class VisionConfig:
    model: str = "qwen3-vl:8b-instruct"
    max_side: int = 1280  # size setting: pixel budget = max_side * max_side * 3/4 (1280 -> about 1.2 megapixels)
    keep_alive: str = "5m"  # how long Ollama keeps the vision model in memory; "0" unloads right away
    num_ctx: int = 8192
    num_predict: int = 1200  # output token limit; Run 16: without it one answer looped for 196 s
    extra: dict = field(default_factory=dict)
    reasoning_model: str = ""  # optional thinking variant (qwen3-vl:8b) for counting, comparing and charts


# Named regions as (left, top, right, bottom) fractions of the image.
REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top": (0.0, 0.0, 1.0, 0.5), "bottom": (0.0, 0.5, 1.0, 1.0),
    "left": (0.0, 0.0, 0.5, 1.0), "right": (0.5, 0.0, 1.0, 1.0),
    "center": (0.25, 0.25, 0.75, 0.75),
    "top-left": (0.0, 0.0, 0.5, 0.5), "top-right": (0.5, 0.0, 1.0, 0.5),
    "bottom-left": (0.0, 0.5, 0.5, 1.0), "bottom-right": (0.5, 0.5, 1.0, 1.0),
}


def parse_region(region: str) -> tuple[float, float, float, float]:
    """A named region, or 'left,top,right,bottom' as fractions between 0 and 1."""
    text = (region or "full").strip().lower().replace("_", "-").replace(" ", "-")
    if text in REGIONS:
        return REGIONS[text]
    try:
        box = tuple(float(v) for v in text.replace("-", ",").split(",") if v != "")
    except ValueError:
        box = ()
    if len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(
            f"unknown region '{region}'. Use one of {', '.join(REGIONS)}, "
            "or 'left,top,right,bottom' fractions such as '0.6,0.4,1,0.7'."
        )
    return box  # type: ignore[return-value]


@dataclass
class PreparedImage:
    data: bytes
    original_size: tuple[int, int]
    sent_size: tuple[int, int]
    source_format: str
    notes: list[str]


def prepare_image(path: Path, max_side: int, region: str = "full") -> PreparedImage:
    """Open any common image format and return JPEG/PNG bytes that Ollama accepts.

    - GIF and WebP are converted (the test set includes both).
    - Animated images: only the first frame is used, and the result says so.
    - Phone photos are rotated according to their EXIF orientation.
    - Transparent images are flattened onto white.
    - Images above a pixel budget (max_side² × 3/4) are downscaled. Zoomed crops are enlarged
      up to 3x within the budget; small full images (longer side below 768) up to 2x.
    - region crops the original full-resolution image first, so zooming into a small
      sign or label gives the vision model many more pixels for the same token cost.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError(f"image is larger than {_MAX_FILE_BYTES // (1024 * 1024)} MB")
    try:
        image = Image.open(path)
    except UnidentifiedImageError:
        raise ValueError(
            f"'{path.name}' is not a readable image. Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}. "
            "HEIC photos must be exported as JPEG first."
        ) from None

    with image:
        notes: list[str] = []
        source_format = image.format or path.suffix.lstrip(".").upper()
        frames = getattr(image, "n_frames", 1)
        if frames > 1:
            image.seek(0)
            notes.append(f"animated image with {frames} frames; only the first frame was analyzed")
        image = ImageOps.exif_transpose(image)
        original_size = image.size
        box = parse_region(region)
        if box != REGIONS["full"]:
            width, height = image.size
            pixels = (round(box[0] * width), round(box[1] * height), round(box[2] * width), round(box[3] * height))
            image = image.crop(pixels)
            notes.append(f"zoomed into region '{region}' ({image.size[0]}x{image.size[1]} pixels of the original)")

        has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        if has_alpha:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # The limit is a pixel budget, not a longest side. Vision tokens grow with area,
        # so the budget keeps the cost about constant, while a zoomed crop (fewer pixels)
        # stays closer to the original resolution. A longest-side limit made zooming
        # useless on tall photos: the right half of a 1932x2576 photo is still 2576 tall.
        budget = max_side * max_side * 3 // 4
        width, height = image.size
        if width * height > budget or max(width, height) > 2 * max_side:
            scale = min((budget / (width * height)) ** 0.5, 2 * max_side / max(width, height))
            image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
            notes.append(f"downscaled from {width}x{height}")
        elif box != REGIONS["full"]:
            # Run 13: a 580x361 crop of a sign was read as "(03)715-1544" instead of
            # "(031)715-1544". Thin characters smaller than the model's image patches get
            # lost, so a zoomed crop is enlarged (up to 3x, within the budget) like a magnifier.
            scale = min((budget / (width * height)) ** 0.5, 2 * max_side / max(width, height), _MAX_ZOOM_UPSCALE)
            if scale > 1.05:
                image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)  # floor: stay within budget
                notes.append(f"enlarged {scale:.1f}x for reading small details")
        elif max(width, height) < _SMALL_IMAGE_SIDE / 1.05:
            # Run 14: a 284x213 cartoon frame was misread (knee pain seen as "surprise or
            # tiredness"). Run 11 showed the model uses about the same number of tokens for
            # any image up to about 960 px, so enlarging a small image is nearly free.
            scale = min(_SMALL_IMAGE_SIDE / max(width, height), 2.0)
            image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
            notes.append(f"small image enlarged {scale:.1f}x")

        # Lossless PNG keeps thin lines and small text sharp in diagrams and screenshots;
        # JPEG is much smaller for photos.
        buffer = io.BytesIO()
        if source_format in ("PNG", "GIF", "BMP"):
            image.save(buffer, format="PNG", optimize=True)
        else:
            image.save(buffer, format="JPEG", quality=90)
        return PreparedImage(buffer.getvalue(), original_size, image.size, source_format, notes)


LOCATE_PROMPT = """Find this in the image: {target}
Match by meaning as well as by printed text (for example, "the microcontroller" can be a module labeled "ESP-WROOM-32").
Return only JSON, no other text: [{{"bbox_2d": [x1, y1, x2, y2], "label": "the text printed on or next to it, or a short description"}}]
Coordinates are on a 0-1000 scale relative to the image width and height (0,0 is the top-left corner).
List the best match first. If it is not in the image, return []."""

# Run 19: "read all text" made the wider crop return every nearby label (IN, OUT, GND, C7, C8),
# so two correct readings never matched. Each reading now asks only for the target text.
READ_PROMPT = """Read this text in the image: {target}.
Copy only that text, exactly, character by character, including numbers, brackets and punctuation. Leave out other text around it.
Keep the original language and line breaks. Do not add, complete or correct anything (for example, do not add area codes).
If a character is unclear, write ? in its place. If there is no such text (for example it is a symbol or a drawing), write [no text]."""

# Accurate mode, second look: short answers that code can compare between two views.
BRIEF_PROMPT = """Answer each question about this image in a few words: a name, a number, a label or a short phrase.
If the answer is not visible, write: not shown.
Reply with exactly one line per question, in this form:
{lines}"""

# Accurate mode, tile scan: a zoomed quarter of a large image, transcribed before the real question.
TILE_PROMPT = """This is one zoomed part of a larger image. List every piece of text, label and number you can read in it, exactly as written, one per line.
Write nothing else. If there is no text, write [no text]."""

NOTES_SUFFIX = """

Text read from zoomed parts of this image (it may contain errors; use it only where it matches what you see):
{notes}"""

# Margin around the found box for the two readings, as a fraction of its size.
# Run 19: with 0.15 the tight crop cut "AMS1117-3V3" to "AMS11".
_PADDING = (0.3, 0.6)
_FOCUS_PADDING = 0.25  # margin around a focus area, so nearby labels and wires stay in view
_FOCUS_MAX_AREA = 0.6  # a focus box larger than this share of the image is treated as the whole image
_FOCUS_MIN_SIDE = 0.15  # a focus crop is at least this share of the image width and height
_WHOLE_IMAGE = __import__("re").compile(
    r"^(the )?(whole|entire|full|complete|all of the)( image| picture| photo| screenshot| page)?$|^(image|picture|photo|all|everything)$|^(전체|이미지 전체|사진 전체|전부|모두|그림 전체)( 이미지| 사진)?$"
)
# A printed reference such as R50, U5, C12, J3, Q1, IC7 or a part number like AMS1117.
_LABEL_PATTERN = __import__("re").compile(r"\b[A-Z]{1,3}\d{1,4}\b|\b[A-Z]{2,}\d{3,}[A-Z0-9-]*\b")


def parse_boxes(text: str, sent_size: tuple[int, int]) -> list[tuple[float, float, float, float]]:
    """Boxes only; see parse_located."""
    return [box for box, _ in parse_located(text, sent_size)]


def parse_located(text: str, sent_size: tuple[int, int]) -> list[tuple[tuple[float, float, float, float], str]]:
    """Extract (box, label) pairs from the vision model's answer. Boxes are (left, top, right, bottom) fractions.

    The prompt asks for a 0-1000 scale (Qwen-VL's native grounding format). If a model
    answers in pixels of the image it was sent instead, values above 1000 reveal that.
    """
    import json
    import re

    numbers: list[list[float]] = []
    labels: list[str] = []
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        items = data if isinstance(data, list) else [data]
        for item in items:
            box = item.get("bbox_2d") or item.get("bbox") if isinstance(item, dict) else item
            if isinstance(box, list) and len(box) == 4:
                numbers.append([float(v) for v in box])
                labels.append(str(item.get("label", "")) if isinstance(item, dict) else "")
    except (ValueError, TypeError, AttributeError):
        numbers, labels = [], []
        for match in re.findall(r"\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]", text):
            numbers.append([float(v) for v in match])
            labels.append("")

    width, height = sent_size
    located = []
    for (x1, y1, x2, y2), label in zip(numbers, labels):
        if max(x1, y1, x2, y2) > 1000:  # pixel coordinates of the sent image
            fx1, fy1, fx2, fy2 = x1 / width, y1 / height, x2 / width, y2 / height
        else:
            fx1, fy1, fx2, fy2 = x1 / 1000, y1 / 1000, x2 / 1000, y2 / 1000
        fx1, fx2 = sorted((max(0.0, min(1.0, fx1)), max(0.0, min(1.0, fx2))))
        fy1, fy2 = sorted((max(0.0, min(1.0, fy1)), max(0.0, min(1.0, fy2))))
        if fx2 - fx1 > 0.002 and fy2 - fy1 > 0.002:
            located.append(((fx1, fy1, fx2, fy2), label.strip()))
    return located


def padded_region(box: tuple[float, float, float, float], padding: float) -> str:
    x1, y1, x2, y2 = box
    pad_x, pad_y = (x2 - x1) * padding, (y2 - y1) * padding
    return ",".join(
        f"{v:.4f}" for v in (max(0.0, x1 - pad_x), max(0.0, y1 - pad_y), min(1.0, x2 + pad_x), min(1.0, y2 + pad_y))
    )


def widened_region(box: tuple[float, float, float, float], min_side: float) -> str:
    """The box grown around its centre to at least min_side of the image width and height."""
    x1, y1, x2, y2 = box
    values = []
    for low, high in ((x1, x2), (y1, y2)):
        side = max(high - low, min_side)
        centre = (low + high) / 2
        low, high = centre - side / 2, centre + side / 2
        if low < 0:
            low, high = 0.0, min(1.0, high - low)
        if high > 1:
            low, high = max(0.0, low - (high - 1)), 1.0
        values.append((low, high))
    (ax1, ax2), (ay1, ay2) = values
    return ",".join(f"{v:.4f}" for v in (ax1, ay1, ax2, ay2))


def trim_repetition(text: str, min_length: int = 12, max_repeats: int = 5) -> tuple[str, bool]:
    """Cut an answer that has started repeating itself.

    Run 16: one describe_image answer looped on the same sentence for 196 s, and the main
    model then treated the output as the user's own text. A line or sentence that appears
    max_repeats times is kept once, and everything from its second appearance is dropped.
    Run 21: with 3, a handwriting sample written three times ("handwriting 손글씨") was cut.
    """
    import re

    pieces = [p for p in re.split(r"(?<=[.!?。])\s+|\n+", text) if p.strip()]
    seen: dict[str, int] = {}
    kept: list[str] = []
    for piece in pieces:
        key = re.sub(r"\W+", "", piece.lower())
        if len(key) >= min_length:
            seen[key] = seen.get(key, 0) + 1
            if seen[key] >= max_repeats:
                # Drop back to the first appearance of this repeated piece.
                first = next(i for i, k in enumerate(kept) if re.sub(r"\W+", "", k.lower()) == key)
                return "\n".join(kept[: first + 1]), True
        kept.append(piece.strip())
    return text, False


def _normalize_reading(text: str) -> str:
    """Letters, digits and punctuation, without spaces or line breaks."""
    return "".join(ch for ch in text.lower() if not ch.isspace())


def _characters_only(text: str) -> str:
    """Letters, digits and '?' only: "031-715-1544" and "(031)715-1544" give the same result."""
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == "?")


# Run 21: a reading of "the key signature at the beginning of the staff" came back as that
# same sentence. A reading that only repeats the request is not a reading.
def repeats_request(reading: str, target: str) -> bool:
    r, t = _characters_only(reading), _characters_only(target)
    return len(r) >= 6 and r in t


_DESCRIPTIVE_FOCUS = __import__("re").compile(
    r"\b(the|a|an|interface|connections?|pins?|area|part|component|section|signals?|wiring|lines?|modulation|measures?|comments?)\b",
    __import__("re").IGNORECASE,
)
_ECHO_MAX_AREA = 0.05  # Runs 18-21: every echo-located box below 5% of the image was the wrong place


def located_by_echo(focus: str, label: str) -> bool:
    """The locator returned the request itself as the label: no printed text was matched."""
    def norm(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())
    return bool(label) and norm(label) == norm(focus) and bool(_DESCRIPTIVE_FOCUS.search(focus))


# "any signs", "all text": several matches are possible; the largest is the most readable.
_GENERIC_READ = __import__("re").compile(r"\b(any|all|every|visible)\b|모든|전부|보이는", __import__("re").IGNORECASE)


def _nearby_lines(tight: str, wider: str) -> list[str] | None:
    """Extra whole lines the wider reading has before or after the tight reading, if that is the only difference."""
    t_lines = [line.strip() for line in tight.strip().splitlines() if line.strip()]
    w_lines = [line.strip() for line in wider.strip().splitlines() if line.strip()]
    n = len(t_lines)
    if n == 0 or n >= len(w_lines) or t_lines == ["[no text]"]:
        return None
    key = [_characters_only(line) for line in t_lines]
    if [_characters_only(line) for line in w_lines[:n]] == key:
        return w_lines[n:]
    if [_characters_only(line) for line in w_lines[-n:]] == key:
        return w_lines[:-n]
    return None


def parse_brief(answer: str, count: int) -> list[str]:
    """Read "1: answer" lines. Missing lines become empty strings."""
    import re

    found: dict[int, str] = {}
    for line in answer.splitlines():
        match = re.match(r"\s*(?:Q)?(\d+)\s*[:.)]\s*(.*)", line)
        if match and 1 <= int(match.group(1)) <= count:
            found.setdefault(int(match.group(1)), match.group(2).strip().strip("*").strip())
    return [found.get(i, "") for i in range(1, count + 1)]


_STOP_WORDS = {"the", "a", "an", "is", "are", "of", "and", "or", "to", "in", "on", "it", "its", "with", "at", "about",
               "approximately", "around", "which", "that", "this", "by", "for", "be", "as"}


def same_answer(first: str, second: str) -> bool:
    """Do two short answers say the same thing? Numbers must match; words must mostly overlap."""
    import re

    a, b = first.strip().lower(), second.strip().lower()
    if not a or not b:
        return a == b
    na, nb = "".join(ch for ch in a if ch.isalnum()), "".join(ch for ch in b if ch.isalnum())
    nums_a = set(re.findall(r"\d+(?:\.\d+)?", a))
    nums_b = set(re.findall(r"\d+(?:\.\d+)?", b))
    if nums_a and nums_b and nums_a != nums_b:
        return False
    if na and nb and (na in nb or nb in na):
        return True
    words_a = {w for w in re.findall(r"\w+", a) if w not in _STOP_WORDS}
    words_b = {w for w in re.findall(r"\w+", b) if w not in _STOP_WORDS}
    if not words_a or not words_b:
        return False
    return len(words_a & words_b) / len(words_a | words_b) >= 0.4


_TILES = (
    ("top left", "0,0,0.55,0.55"), ("top right", "0.45,0,1,0.55"),
    ("bottom left", "0,0.45,0.55,1"), ("bottom right", "0.45,0.45,1,1"),
)


def _one_is_cut_off(first: str, second: str) -> bool:
    """One reading is the start or the end of the other (a crop cut the text off)."""
    a, b = _characters_only(first), _characters_only(second)
    short, long = sorted((a, b), key=len)
    return len(short) >= 3 and short != long and (long.startswith(short) or long.endswith(short))


# Run 19: the note about signs was added to a reading of a regulator on a schematic.
_SIGN_TARGET = __import__("re").compile(
    r"\bsigns?\b|signboard|signage|\bshops?\b|\bstores?\b|business|banner|storefront|간판|상호|가게|매장|현수막|점포",
    __import__("re").IGNORECASE,
)


def register_vision_tools(
    registry: ToolRegistry,
    resolve_path: Callable[[str], Path],
    client: ChatModel | None,
    config: VisionConfig,
    reasoning_client: ChatModel | None = None,
) -> None:
    """Register describe_image and read_text_in_image. `client` talks to the vision model (a fake in tests).

    reasoning_client: optional thinking variant, used only by code-level callers (the planner in
    accurate mode) for counting, comparing and chart questions. If it fails, `client` is used.
    """
    from .llm import LLMError

    state = {"reasoning_error": ""}

    def find_image(path: str) -> Path:
        if client is None:
            raise ValueError("no vision model is configured")
        target = resolve_path(path)
        if not target.is_file():
            raise ValueError(f"'{path}' does not exist. Use list_files or find the correct path first.")
        if target.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(
                f"'{path}' is not an image file. Use read_file for text. Supported images: {', '.join(sorted(IMAGE_EXTENSIONS))}"
            )
        return target

    def ask(
        image: PreparedImage, prompt: str, system: str | None = VISION_SYSTEM_PROMPT, reasoning: bool = False
    ) -> tuple[str, float, int]:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt, "images": [base64.b64encode(image.data).decode("ascii")]})
        start = time.perf_counter()
        response = None
        if reasoning and reasoning_client is not None and not state["reasoning_error"]:
            try:
                response = reasoning_client.chat(messages)
            except LLMError as exc:
                # A missing model or a server without thinking support must not stop the answer.
                state["reasoning_error"] = str(exc)[:200]
        if response is None:
            response = client.chat(messages)
        seconds = time.perf_counter() - start
        answer = (response["message"].get("content") or "").strip()
        stats = response.get("stats") or {}
        answer, looped = trim_repetition(answer)
        if looped:
            answer += "\n[warning: the vision model started repeating itself; the rest of its answer was dropped]"
        elif config.num_predict and stats.get("output_tokens", 0) >= config.num_predict:
            answer += "\n[warning: the answer hit the length limit and may be cut off]"
        return answer, seconds, stats.get("prompt_tokens") or 0

    def locate(
        image_path: Path, target: str, largest: bool = False
    ) -> tuple[tuple[float, float, float, float] | None, str, str, float]:
        overview = prepare_image(image_path, config.max_side)
        answer, seconds, _ = ask(overview, LOCATE_PROMPT.format(target=target), system=None)
        found = parse_located(answer, overview.sent_size)
        if not found:
            return None, "", answer, seconds
        if largest:
            found.sort(key=lambda f: (f[0][2] - f[0][0]) * (f[0][3] - f[0][1]), reverse=True)
        box, label = found[0]
        return box, label, answer, seconds

    def not_found(image_path: Path, target: str, calls: int, seconds: float, raw: str) -> dict:
        header = f"[{image_path.name}: '{target}' was not found, {calls} vision call, {seconds:.1f} s]\n"
        if _LABEL_PATTERN.search(target):
            # Run 14: after "not found" for resistor R50, the main model asked describe_image
            # instead, which invented "R50 is 10k". A missing printed label is usually absent.
            return {"status": "not_found", "text": header + (
                f"NOT FOUND: the specific label in '{target}' could not be located. It is probably not in the image. "
                "Tell the user it is not shown. Do not ask describe_image for its value, because that invites a guess."
            )}
        # Run 16: "MCU 모듈" was not found although the board is built around an ESP-WROOM-32.
        # A general or translated description can fail where the printed name would work.
        return {"status": "not_located", "text": header + (
            f"NOT LOCATED: the vision model could not place '{target}'. This does not prove it is absent. "
            "Retry once with the text printed in the image (usually English, such as a part number or label), "
            "or call describe_image without focus and ask about the whole image."
        )}

    def describe(
        path: str, question: str, focus: str = "", region: str = "full", strict: bool = False,
        scan_notes: str = "", reasoning: bool = False,
    ) -> dict:
        """Core of describe_image. Returns a dict with status, answer and the formatted tool text."""
        target = find_image(path)
        calls, total = 0, 0.0
        focus_note = ""
        guard_note = ""
        used_box = None
        if _WHOLE_IMAGE.match(focus.strip().lower()):
            # Run 17: focus "whole image" failed to locate three times. Documentation alone
            # did not stop it, so a focus that means the whole image is simply ignored.
            guard_note = f"\n[note: focus '{focus}' was ignored because it means the whole image]"
            focus = ""
        if focus.strip():
            box, label, raw, seconds = locate(target, focus)
            calls, total = calls + 1, total + seconds
            if box is None:
                return not_found(target, focus, calls, total, raw)
            area = (box[2] - box[0]) * (box[3] - box[1])
            if strict and area < _ECHO_MAX_AREA and located_by_echo(focus, label):
                # Runs 18-21: "OLED interface", "the modulation with the lowest Eb/N0", "the humor in
                # the comments" were each placed on a small box labelled with the request itself, and
                # every answer from that view was wrong. Such a box is treated as not located.
                result = not_found(target, focus, calls, total, raw)
                result["status"] = "not_located"
                result["echo"] = True
                return result
            location = ",".join(f"{v:.3f}" for v in box)
            # Run 16: "OLED" located the FTDI header U4. Showing what was found lets the main model notice.
            found_as = f", identified as '{label}'" if label else ""
            if (box[2] - box[0]) * (box[3] - box[1]) > _FOCUS_MAX_AREA:
                # Run 15: focus 'the tweet thread' covered 95% of the image; cropping only
                # cost an extra call. A focus that is most of the image means the whole image.
                focus_note = f"\n[note: '{focus}' covers most of the image ({location}), so the whole image was used]"
            else:
                # Run 18: a focus on "the GPIO pins connected to OLED" gave a 107x35 pixel crop
                # with no readable labels. A crop has a minimum size so its surroundings stay in view.
                padded = tuple(float(v) for v in padded_region(box, _FOCUS_PADDING).split(","))
                region = widened_region(padded, _FOCUS_MIN_SIDE)
                used_box = box
                focus_note = (
                    f"\n[note: focused on '{focus}' found at {location}{found_as}. "
                    "If that is not the part you meant, retry with the label printed on it]"
                )
        image = prepare_image(target, config.max_side, region)
        prompt = question + (NOTES_SUFFIX.format(notes=scan_notes) if scan_notes else "")
        thinking = reasoning and reasoning_client is not None and not state["reasoning_error"]
        answer, seconds, tokens = ask(image, prompt, reasoning=reasoning)
        calls, total = calls + 1, total + seconds
        if thinking and state["reasoning_error"]:
            guard_note += f"\n[note: the thinking model failed ({state['reasoning_error']}); the standard vision model answered]"
        elif thinking:
            guard_note += f"\n[note: answered by the thinking model {getattr(reasoning_client, 'model', '')}]"
        if scan_notes:
            guard_note += "\n[note: text from the tile scan was given to the vision model]"
        width, height = image.sent_size
        details = [f"{image.source_format} {width}x{height}", f"{total:.1f} s"]
        if calls > 1:
            details.append(f"{calls} vision calls")
        if tokens:
            details.append(f"{tokens} input tokens")
        header = f"[describe_image result for {target.name}: {', '.join(details)}. This is tool output, not the user's words]"
        notes = guard_note + focus_note + "".join(f"\n[note: {n}]" for n in image.notes)
        answer = answer or "[the vision model returned no text]"
        return {
            "status": "ok", "answer": answer, "seconds": total, "box": used_box, "region": region,
            "label": label if used_box else "", "text": f"{header}{notes}\n{answer}",
        }

    def read_text(path: str, target: str) -> dict:
        """Core of read_text_in_image. Returns a dict with status, readings and the formatted tool text."""
        image_path = find_image(path)
        total_seconds, calls = 0.0, 0

        # 1. Locate. Qwen-VL models answer grounding requests with boxes on a 0-1000 scale.
        box, label, located, seconds = locate(image_path, target, largest=bool(_GENERIC_READ.search(target)))
        total_seconds, calls = total_seconds + seconds, calls + 1
        if box is None:
            return not_found(image_path, target, calls, total_seconds, located)

        # 2. Read twice: a tight crop (strongly enlarged) and a wider crop (more context).
        readings = []
        for padding in _PADDING:
            region = padded_region(box, padding)
            crop = prepare_image(image_path, config.max_side, region)
            text, seconds, _ = ask(crop, READ_PROMPT.format(target=target))
            total_seconds, calls = total_seconds + seconds, calls + 1
            if repeats_request(text, target):
                text = "[no text]"
            readings.append((region, crop.sent_size, text.strip() or "[no text]"))

        # 3. Compare. Agreement is evidence, not proof; disagreement must be reported, not hidden.
        agree = _normalize_reading(readings[0][2]) == _normalize_reading(readings[1][2])
        same_characters = _characters_only(readings[0][2]) == _characters_only(readings[1][2])
        unclear = any("?" in r[2] for r in readings)
        nearby = _nearby_lines(readings[0][2], readings[1][2])
        if agree and not unclear:
            status, verdict = "confirmed", "CONFIRMED: both readings agree."
        elif nearby is not None and not unclear:
            # Run 22: the tight crop read "WONDERWALL"; the wider crop read "WONDERWALL" and the next
            # line "Guitar/Ukulele". The extra lines belong to text around the target, not to it.
            status, verdict = "confirmed", (
                "CONFIRMED: both readings agree on the target; the wider crop also shows nearby lines: "
                + " / ".join(nearby)
            )
        elif same_characters and not unclear:
            # Run 19: "031-715-1544" and "(031)715-1544" were reported as UNCERTAIN.
            status, verdict = "format_differs", (
                "CONFIRMED CHARACTERS: both readings have the same letters and digits; only punctuation or spacing "
                "differs. Report both forms."
            )
        elif not unclear and _one_is_cut_off(readings[0][2], readings[1][2]):
            # Run 20: "AMS1117" (tight crop) vs "AMS1117-3V3" (wider crop) was reported as UNCERTAIN.
            status, verdict = "cut_off", (
                "PARTLY CONFIRMED: one reading stops early. Where the readings overlap they agree; the rest was "
                "read only once. Report the longer reading as not fully confirmed."
            )
        elif same_characters:
            status, verdict = "partly_unclear", "PARTLY UNCLEAR: both readings agree, but some characters were marked '?' as unreadable."
        else:
            status, verdict = "uncertain", "UNCERTAIN: the two readings differ. Report both to the user and do not pick one."

        location = ",".join(f"{v:.3f}" for v in box)
        found_as = f", identified as '{label}'" if label else ""
        lines = [
            f"[read_text_in_image result for {image_path.name}: found '{target}' at {location}{found_as}, "
            f"{calls} vision calls, {total_seconds:.1f} s. This is tool output, not the user's words]"
        ]
        for i, (region, size, text) in enumerate(readings, 1):
            kind = "tight crop" if i == 1 else "wider crop"
            lines.append(f"Reading {i} ({kind} {region}, sent {size[0]}x{size[1]}):\n{text}")
        lines.append(verdict)
        if _SIGN_TARGET.search(f"{target} {label}"):
            # Run 17: after reading "푸르지오강남" the 8B main model again claimed the photo was taken
            # in Gangnam, Seoul. A reminder right next to the reading works better than the system prompt.
            lines.append("Note: text on a sign names a business or brand; it is not evidence of where the photo was taken.")
        return {
            "status": status,
            "readings": [r[2] for r in readings],
            "nearby": nearby or [],
            "seconds": total_seconds,
            "text": "\n".join(lines),
        }

    def brief(
        path: str, questions: list[str], region: str = "full", scale: float = 1.0, reasoning: bool = False
    ) -> dict:
        """Short answers to each question from one view, for code to compare between views."""
        target = find_image(path)
        image = prepare_image(target, max(256, int(config.max_side * scale)), region)
        lines = "\n".join(f"{i}: <answer to: {q}>" for i, q in enumerate(questions, 1))
        answer, seconds, _ = ask(image, BRIEF_PROMPT.format(lines=lines), reasoning=reasoning)
        return {
            "answers": parse_brief(answer, len(questions)), "seconds": seconds, "raw": answer,
            "view": f"{region} at {image.sent_size[0]}x{image.sent_size[1]}"
            + (" (thinking model)" if reasoning and reasoning_client is not None and not state["reasoning_error"] else ""),
        }

    scan_cache: dict[str, dict] = {}

    def scan(path: str) -> dict:
        """Transcribe the four zoomed quarters of an image that had to be downscaled. Cached per image."""
        target = find_image(path)
        key = str(target)
        if key in scan_cache:
            return scan_cache[key]
        overview = prepare_image(target, config.max_side)
        if not any(n.startswith("downscaled") for n in overview.notes):
            result = {"notes": "", "seconds": 0.0, "tiles": 0, "reason": "the whole image already fits the pixel budget"}
        else:
            seen, lines, total = set(), [], 0.0
            for name, region in _TILES:
                tile = prepare_image(target, config.max_side, region)
                text, seconds, _ = ask(tile, TILE_PROMPT)
                total += seconds
                for line in text.splitlines():
                    clean = line.strip().lstrip("-*• ").strip()
                    key_line = "".join(ch for ch in clean.lower() if ch.isalnum())
                    if not clean or clean == "[no text]" or clean.startswith("[warning") or key_line in seen:
                        continue
                    seen.add(key_line)
                    lines.append(f"({name}) {clean}")
            result = {"notes": "\n".join(lines[:150]), "seconds": total, "tiles": len(_TILES), "reason": ""}
        scan_cache[key] = result
        return result

    @registry.register
    def describe_image(
        path: str,
        question: str = "Describe this image in detail and read all visible text exactly.",
        focus: str = "",
        region: str = "full",
    ) -> str:
        """Look at an image file and answer a question about it. You cannot see images yourself, so use this for any .png .jpg .jpeg .gif .webp .bmp .tif file: photos, screenshots, scanned pages, slides, charts, diagrams, schematics, formulas, handwriting, sheet music, comment threads.
        For a question about one part of a detailed image, set focus to that visible part: it is found, zoomed in, and question is answered from the zoomed view. Use one call per part, and ask only about that part in the question. For a schematic, look at each component separately (first 'Micro SD Card module U5', then 'OLED display SSD1306 U3').
        Leave focus empty when the question is about the whole image: a summary, all comments, the whole page, or describing a photo.
        To read a short piece of text exactly (one sign, label, phone number, price), use read_text_in_image instead.

        Args:
            path: Image file path relative to the workspace root, e.g. 'evals/vision/images/10_night_street_photo.jpg'.
            question: The question in the user's own language; do not translate it. With focus, ask only about that part (e.g. 'SD 카드 모듈의 CS, MOSI, SCK, MISO 핀에는 각각 어떤 GPIO가 연결돼 있어?'), not the user's whole multi-part question.
            focus: Optional visible part to find and zoom into. Best is the text printed on it, usually English: 'ESP-WROOM-32', 'SSD1306 OLED display U3', 'Micro SD Card U5', 'AMS1117 regulator U1', 'the chart legend'. A thing you can point at, never the question itself. Leave empty for the whole image.
            region: Optional fixed area instead of focus: full, top, bottom, left, right, center, top-left, top-right, bottom-left, bottom-right, or 'left,top,right,bottom' fractions.
        """
        return describe(path, question, focus, region)["text"]

    @registry.register
    def read_text_in_image(path: str, target: str) -> str:
        """Read one short piece of text in an image exactly: a sign, label, phone number, price, pin name, title or caption. It finds where the text is, zooms in, reads it twice at two zoom levels and reports whether the readings agree. Use it whenever exact characters or numbers of one item matter, also when the user asks to describe a photo and read a sign in it. Not for transcribing a whole page, slide or comment thread; use describe_image for that.

        Args:
            path: Image file path relative to the workspace root.
            target: Where and what kind of text, e.g. 'the shop sign on the right side', 'the phone number on that sign', 'the part number of U1'. Never put the text you expect to read in the target.
        """
        return read_text(path, target)["text"]

    # Structured access for code-level callers such as the image question planner.
    registry.vision = SimpleNamespace(
        describe=describe, read_text=read_text, brief=brief, scan=scan,
        has_reasoning=reasoning_client is not None, state=state,
    )
