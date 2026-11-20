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
        r"can i run", r"throttl", r"overheat", r"전송\s*속도", r"대역폭", r"(?<![a-z])bandwidth", r"throughput",
        r"화면\s*밝기", r"조도", r"키보드\s*(백라이트|조명|밝기)", r"brightness", r"ambient light",
        r"(cpu|gpu|칩|코어)\s*(의\s*)?(온도|몇\s*도)", r"(cpu|gpu|chip) temperature", r"rpm", r"앱별", r"어떤\s*앱", r"which app",
        r"(?<![a-z])usb", r"썬더볼트", r"thunderbolt", r"포트", r"(?<![a-z])ports?(?![a-z])", r"버스", r"연결된\s*(장치|기기)", r"외장",
        r"connected devices?", r"peripheral",
        r"어떤\s*작업", r"무슨\s*작업", r"뭘\s*할\s*수", r"what can i (do|run)", r"영상\s*편집", r"동영상\s*편집", r"게임", r"(?<![a-z])gam(e|es|ing)(?![a-z])",
        r"3d", r"렌더링", r"블렌더", r"blender", r"(?<![a-z])render", r"딥러닝", r"학습", r"(?<![a-z])training", r"train a", r"deep.?learning", r"컴파일", r"빌드", r"compil",
        r"사진\s*편집", r"라이트룸", r"lightroom", r"photo edit", r"video edit", r"edit(ing)? (4k )?video", r"화상\s*(통화|회의)", r"video call",
    ],
}
TOPICS["network"] = [
    r"와이파이", r"와이 파이", r"(?<![a-z])wi-?fi(?![a-z])", r"인터넷", r"네트워크", r"공유기", r"라우터", r"(?<![가-힣])핑", r"레이턴시",
    r"끊겨", r"끊김", r"끊기", r"끊어", r"신호\s*(세기|강도)?", r"채널", r"블루투스", r"에어팟", r"에어드롭", r"(?<![a-z])dns(?![a-z])",
    r"온라인\s*게임", r"(?<![가-힣])롤(?!백|러|링|케)", r"리그\s*오브\s*레전드", r"발로란트", r"배그", r"배틀\s*그라운드", r"오버워치",
    r"(?<![a-z])lol(?![a-z])", r"league of legends", r"valorant", r"(?<![a-z])pubg(?![a-z])", r"overwatch",
    # Online games by name, and asking whether to play now: a question about the connection (the Mac's own load
    # stays with the performance agent: "게임 돌려도 돼?", "게임하면 발열 심해?").
    r"피파\s*온라인", r"(?<![a-z])fc\s*온라인", r"메이플", r"로스트\s*아크", r"서든\s*어택", r"스타크래프트", r"에이펙스", r"포트나이트",
    r"카운터\s*스트라이크", r"도타", r"마인크래프트", r"던전\s*앤\s*파이터", r"던파", r"이터널\s*리턴", r"롤토체스", r"원신", r"디아블로", r"철권",
    r"(?<![a-z])apex(?![a-z])", r"fortnite", r"(?<![a-z])cs2(?![a-z])", r"counter-?strike", r"(?<![a-z])dota", r"minecraft", r"genshin", r"diablo", r"tekken",
    r"게임\s*(해도|할\s*수|하기|하려|할까|해\s*도|중에?\s*(핑|렉|끊))", r"(?<![a-z])play(ing)?\s+(a\s+)?(games?|online)",
    r"다운로드\s*속도", r"업로드\s*속도", r"인터넷\s*속도", r"통신",
    r"(?<![a-z])internet(?![a-z])", r"(?<![a-z])network(?![a-z])", r"(?<![a-z])router(?![a-z])", r"(?<![a-z])ping(?![a-z])",
    r"latency", r"jitter", r"packet loss", r"(?<![a-z])signal(?![a-z])", r"(?<![a-z])channel(?![a-z])", r"bluetooth", r"airpods", r"airdrop",
    r"online gam", r"download speed", r"upload speed", r"connection",
    r"화상\s*(통화|회의)", r"video call", r"(?<![a-z])zoom(?![a-z])", r"facetime", r"페이스타임",
]
# A keyword alone is not enough when the question asks about a subject in general ("explain how
# batteries work", "the memory chip market"): such a question goes to the general agent loop,
# unless it also points at this machine. Run D1: qwen3:1.7b sent "explain the chemistry of
# lithium-ion batteries" to the battery agent, so this is decided by the rules, not the model.
GENERAL = [r"원리", r"설명해", r"시장", r"전망", r"역사", r"뉴스", r"주가", r"차이(가|점)?", r"종류", r"란\??$", r"이란",
           r"what is", r"explain", r"how do(es)? .* work", r"market", r"history", r"difference"]
THIS_MACHINE = [r"내\s", r"내가", r"맥", r"노트북", r"컴퓨터", r"지금", r"이\s*(기기|컴|노트북)", r"(?<![a-z])my(?![a-z])", r"\bthis (mac|laptop|computer)\b", r"(?<![a-z])now(?![a-z])"]

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string", "enum": ["battery", "performance", "network", "none"]}},
    "required": ["topic"],
}
ROUTE_PROMPT = """Classify a question to a MacBook assistant.
battery: battery health, charge, charging, power adapter, energy mode, how long the battery lasts.
performance: the Mac is slow or hot, fans, CPU, GPU, memory, storage, whether a job can run now.
network: Wi-Fi, the internet connection, the router, latency, Bluetooth devices.
none: anything else (not about this computer's hardware).
Question: {question}
Answer with JSON: {{"topic": "battery" | "performance" | "network" | "none"}}"""


@dataclass
class Route:
    topic: str | None  # "battery", "performance", "network" or None
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
    # "Can I play an online game on this Wi-Fi?": a network word decides against performance (the work is
    # about the connection); with battery words it stays a tie for the model.
    if "network" in hit and "battery" not in hit:
        return Route("network", "rules-network", matches, time.perf_counter() - started)
    # "How long can I game on battery?": a kind of work named with battery words is a question for the
    # performance agent, which gives the time on battery for that work.
    from .diagnosis import work_from_question
    if "performance" in hit and work_from_question(question) not in (None, "overview"):
        return Route("performance", "rules-work", matches, time.perf_counter() - started)
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
