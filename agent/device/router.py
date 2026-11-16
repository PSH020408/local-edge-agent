"""Question router: sends a device question to its agent, by rules first.

Rules are keyword patterns in Korean and English. A general-knowledge question that does not point
at this machine → none. One topic matched → that topic, in well under a millisecond. Several or none
matched → the small model (qwen3:1.7b) chooses with a JSON schema; without a model, the topic with
the most matches wins and "none" stays none. "none" means the
question is not about the device and goes to the general agent loop.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

# English words are bounded by ASCII letters only: in "CPU를" the Korean particle counts as a word
# character for \b, so \bcpu\b would not match.
TOPICS = {
    "battery": [
        r"배터리", r"충전", r"완충", r"방전", r"어댑터", r"고성능\s*모드", r"저전력", r"에너지\s*모드", r"전원\s*모드",
        r"얼마나\s*(더\s*)?(버티|버텨|갈|쓸)", r"남은\s*시간", r"닳", r"교체", r"사이클",
        r"(?<![a-z])battery(?![a-z])", r"(?<![a-z])charg", r"(?<![a-z])adapter(?![a-z])", r"high power mode", r"low power mode", r"power mode",
        r"how long .*last", r"drain",
    ],
    "performance": [
        r"느려", r"느린", r"버벅", r"렉", r"뜨거", r"발열", r"\b팬\b", r"팬이", r"팬 ", r"메모리", r"\b램\b", r"스왑",
        r"(?<![a-z])cpu(?![a-z])", r"(?<![a-z])gpu(?![a-z])", r"칩", r"주파수", r"(?<!고)(?<!저)성능", r"돌려도", r"돌릴", r"실행해도", r"저장\s*공간",
        r"디스크", r"(?<![a-z])ssd(?![a-z])", r"(?<!배터리 )용량이?\s*(부족|없|남)", r"프로세스", r"과열",
        r"(?<![a-z])slow(?![a-z])", r"(?<![a-z])hot(?![a-z])", r"(?<![a-z])fans?(?![a-z])", r"(?<![a-z])memory(?![a-z])", r"(?<![a-z])ram(?![a-z])", r"(?<![a-z])swap", r"(?<![a-z])disk(?![a-z])", r"storage",
        r"can i run", r"throttl", r"overheat",
    ],
}
# A keyword alone is not enough when the question asks about a subject in general ("explain how
# batteries work", "the memory chip market"): such a question goes to the general agent loop,
# unless it also points at this machine. Run D1: qwen3:1.7b sent "explain the chemistry of
# lithium-ion batteries" to the battery agent, so this is decided by the rules, not the model.
GENERAL = [r"원리", r"설명해", r"시장", r"전망", r"역사", r"뉴스", r"주가", r"차이(가|점)?", r"종류", r"란\??$", r"이란",
           r"what is", r"explain", r"how do(es)? .* work", r"market", r"history", r"difference"]
THIS_MACHINE = [r"내\s", r"내가", r"맥", r"노트북", r"컴퓨터", r"지금", r"이\s*(기기|컴|노트북)", r"(?<![a-z])my(?![a-z])", r"\bthis (mac|laptop|computer)\b", r"(?<![a-z])now(?![a-z])"]

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string", "enum": ["battery", "performance", "none"]}},
    "required": ["topic"],
}
ROUTE_PROMPT = """Classify a question to a MacBook assistant.
battery: battery health, charge, charging, power adapter, energy mode, how long the battery lasts.
performance: the Mac is slow or hot, fans, CPU, GPU, memory, storage, whether a job can run now.
none: anything else (not about this computer's hardware).
Question: {question}
Answer with JSON: {{"topic": "battery" | "performance" | "none"}}"""


@dataclass
class Route:
    topic: str | None  # "battery", "performance" or None
    method: str        # "rules", "model", "rules-tie" or "none"
    matches: dict
    seconds: float


def rule_matches(question: str) -> dict[str, int]:
    q = question.lower()
    return {topic: sum(1 for p in patterns if re.search(p, q)) for topic, patterns in TOPICS.items()}


def route(question: str, llm=None) -> Route:
    started = time.perf_counter()
    matches = rule_matches(question)
    hit = [t for t, n in matches.items() if n]
    q = question.lower()
    general = any(re.search(p, q) for p in GENERAL) and not any(re.search(p, q) for p in THIS_MACHINE)
    if general:
        return Route(None, "rules-general", matches, time.perf_counter() - started)
    if len(hit) == 1:
        return Route(hit[0], "rules", matches, time.perf_counter() - started)
    if llm is not None:
        try:
            reply = llm.chat([{"role": "user", "content": ROUTE_PROMPT.format(question=question)}], format=ROUTE_SCHEMA)
            topic = json.loads(reply["message"]["content"]).get("topic")
            return Route(None if topic == "none" else topic, "model", matches, time.perf_counter() - started)
        except Exception:  # noqa: BLE001 - fall back to the rules
            pass
    if hit:
        best = max(hit, key=lambda t: matches[t])
        return Route(best, "rules-tie", matches, time.perf_counter() - started)
    return Route(None, "none", matches, time.perf_counter() - started)
