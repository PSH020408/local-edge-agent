"""Answer writer: a small local model turns a diagnosis report into a short answer; code checks it.

The model receives only the facts and findings, already formatted by code, and is told to copy
numbers. Every number in the answer is then compared with the numbers in the report and the
question. An answer with an unsupported number is written again once with the offending numbers
named; if it still has one, the answer is built by code from the findings instead (a template),
so a wrong number never reaches the user.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .diagnosis import Report

SYSTEM = """You explain a diagnosis of the user's MacBook, made from its own sensor readings.
Rules:
- Use only the facts and findings given. Copy numbers exactly as written; do not compute, convert or round them.
- Answer in the language of the question (Korean for a Korean question).
- 3 to 6 sentences: the state, the cause if there is a problem, and what to do. Most important first.
- Mention problems and warnings before information. Give only the causes stated in the findings; do not add your own.
- Keep each fact's meaning: available memory is not used memory, free storage is not used storage, a macOS estimate is not the agent's own estimate.
- No headings, no lists, no closing offers."""

# Run D3: qwen3:4b-instruct translated terms freely ("High Power Mode" as "high capacity mode", vents as
# "valves", fans as "pump") and mixed available with used memory, so the Korean terms are given.
# Run D4: given all at once, the terms primed the model: it named High Power Mode on battery reports in
# Automatic mode and mentioned energy modes in performance answers. Only the terms in the report are given.
KOREAN_TERMS = (
    ("High Power", "고성능 모드"), ("Low Power", "저전력 모드"), ("Automatic", "자동"),
    ("memory available", "사용 가능한 메모리 (not 사용량)"),
    ("storage free", "남은 저장 공간"), ("maximum capacity (macOS)", "최대 용량(macOS)"),
    ("full-charge capacity / design capacity", "설계 용량 대비 완충 용량"),
    ("charge cycles", "충전 횟수"), ("cell voltages", "셀 전압"), ("spread", "편차"),
    ("vents", "통풍구"), ("fans", "팬"), ("thermal pressure", "열 압력"), ("power drawn", "소비 전력"),
    ("of one core", "한 코어의 시간 기준 (200% = 코어 두 개가 꽉 참; 전체 CPU 사용률에는 쓰지 말 것)"),
    ("not measured", "측정하지 않음"), ("not handled", "다루지 않음 (사용자 설정에 맡김)"),
    ("resident", "실제 점유 (공유 메모리는 프로세스마다 중복 집계)"), ("unified memory", "통합 메모리"), ("memory bandwidth", "메모리 대역폭"),
)


def korean_terms(report_text_: str) -> str:
    lines = [f"{en} = {ko}" for en, ko in KOREAN_TERMS if en.lower() in report_text_.lower()]
    return "Use these Korean terms:\n" + "\n".join(lines) if lines else ""


_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[float]:
    found = []
    for m in _NUMBER.finditer(text):
        try:
            found.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return found


def report_text(report: Report) -> str:
    lines = ["Facts:"] + [f"- {k}: {v}" for k, v in report.facts.items()]
    lines.append("Findings (most severe first):")
    order = {"problem": 0, "warning": 1, "info": 2}
    for item in sorted(report.findings, key=lambda x: order.get(x.severity, 3)):
        evidence = "; ".join(f"{k}: {v}" for k, v in item.evidence.items())
        lines.append(f"- [{item.severity}] {item.title}. Evidence: {evidence or '-'}. Advice: {item.advice}")
    return "\n".join(lines)


def unsupported(answer: str, report: Report, question: str) -> list[str]:
    """Numbers in the answer that are not in the report or the question (within rounding)."""
    allowed = numbers(report_text(report)) + numbers(question)
    out = []
    for value in numbers(answer):
        if any(abs(value - a) <= max(0.051, 0.006 * abs(a)) for a in allowed):
            continue
        if value in (1, 2, 3) and abs(value) < 4:  # counting words written as digits ("2 things")
            continue
        out.append(f"{value:g}")
    return out


_LATIN = re.compile(r"[A-Za-z][A-Za-z-]+")
_COMMON = {"mac", "macbook", "macos", "apple", "ok"}


def stray_words(answer: str, report: Report, question: str) -> list[str]:
    """Latin words in a Korean answer that are in neither the report nor the question.

    Run D3, L05: a rewritten answer held a broken fragment ("2. tqdm.") that the number check let through.
    """
    if not re.search(r"[가-힣]", answer):
        return []
    known = (report_text(report) + " " + question).lower()
    return sorted({w for w in _LATIN.findall(answer) if w.lower() not in known and w.lower() not in _COMMON})


_REASONING = re.compile(r"^\s*(okay|ok|alright|let me|first,|so,|hmm|wait)\b|let me (tackle|check|think|look)|the user is asking",
                        re.I)


def clean(text: str) -> str:
    """Removes a <think> block; Run D1: qwen3:4b is the thinking variant and wrote its reasoning as the answer."""
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()


def looks_like_reasoning(text: str) -> bool:
    return bool(_REASONING.search(text[:300]))


# Run D5, L05: the template answered a Korean question in English without saying why.
TEMPLATE_LEAD_KO = "답변 문장을 만들지 못해 진단 결과를 그대로 보여 드립니다: "


def template(report: Report, korean: bool = False) -> str:
    order = {"problem": 0, "warning": 1, "info": 2}
    parts = [TEMPLATE_LEAD_KO.strip()] if korean else []
    for item in sorted(report.findings, key=lambda x: order.get(x.severity, 3))[:3]:
        evidence = ", ".join(f"{k} {v}" for k, v in list(item.evidence.items())[:3])
        parts.append(f"{item.title}" + (f" ({evidence})" if evidence else "") + f". {item.advice}")
    return " ".join(parts)


@dataclass
class Written:
    text: str
    method: str          # "model", "model-retry", "template" or "template-no-model"
    unsupported: list[str]
    seconds: float
    first: str = ""      # the model's first answer when it was rejected (kept for the run report)
    reason: str = ""     # why it was rejected


def _problem(text: str, report: Report, question: str) -> tuple[str, list[str]]:
    """The reason an answer is not usable ("" if it is) and its unsupported numbers."""
    if looks_like_reasoning(text):
        return "it describes its reasoning instead of answering", []
    bad = unsupported(text, report, question)
    if bad:
        return f"these numbers are not in the facts: {', '.join(bad)}", bad
    words = stray_words(text, report, question)
    if words:
        return f"these words are not in the facts: {', '.join(words)}", []
    return "", []


def write(report: Report, question: str, llm=None) -> Written:
    started = time.perf_counter()
    if llm is None:
        return Written(template(report), "template-no-model", [], time.perf_counter() - started)
    # Run D2: English questions were answered in Korean; the language is stated by code, not left to the model.
    korean = bool(re.search(r"[가-힣]", question))
    text = report_text(report)
    terms = korean_terms(text) if korean else ""
    content = f"Question: {question}\n\n{text}\n\n" + (terms + "\n\n" if terms else "") + f"Answer in {'Korean' if korean else 'English'}."
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    try:
        first = clean(llm.chat(messages)["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        return Written(template(report, korean), "template", [], time.perf_counter() - started, reason=f"model failed: {exc}")
    problem, bad = _problem(first, report, question)
    if not problem:
        return Written(first, "model", [], time.perf_counter() - started)
    retry = messages + [{"role": "assistant", "content": first},
                        {"role": "user", "content": f"The answer is not usable: {problem}. "
                                                    "Write only the answer, copying numbers only from the facts."}]
    try:
        second = clean(llm.chat(retry)["message"]["content"])
    except Exception:  # noqa: BLE001
        second = ""
    problem_again, bad_again = _problem(second, report, question) if second else (problem, bad)
    if second and not problem_again:
        return Written(second, "model-retry", bad, time.perf_counter() - started, first=first, reason=problem)
    return Written(template(report, korean), "template", bad_again, time.perf_counter() - started, first=first, reason=problem)
