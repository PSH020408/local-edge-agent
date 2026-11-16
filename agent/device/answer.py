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


_REASONING = re.compile(r"^\s*(okay|ok|alright|let me|first,|so,|hmm|wait)\b|let me (tackle|check|think|look)|the user is asking",
                        re.I)


def clean(text: str) -> str:
    """Removes a <think> block; Run D1: qwen3:4b is the thinking variant and wrote its reasoning as the answer."""
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()


def looks_like_reasoning(text: str) -> bool:
    return bool(_REASONING.search(text[:300]))


def template(report: Report) -> str:
    order = {"problem": 0, "warning": 1, "info": 2}
    parts = []
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


def write(report: Report, question: str, llm=None) -> Written:
    started = time.perf_counter()
    if llm is None:
        return Written(template(report), "template-no-model", [], time.perf_counter() - started)
    # Run D2: English questions were answered in Korean; the language is stated by code, not left to the model.
    language = "Korean" if re.search(r"[가-힣]", question) else "English"
    content = f"Question: {question}\n\n{report_text(report)}\n\nAnswer in {language}."
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    try:
        first = clean(llm.chat(messages)["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        return Written(template(report), "template", [], time.perf_counter() - started, reason=f"model failed: {exc}")
    reasoning = looks_like_reasoning(first)
    bad = unsupported(first, report, question)
    if not bad and not reasoning:
        return Written(first, "model", [], time.perf_counter() - started)
    problem = "it describes its reasoning instead of answering" if reasoning else f"these numbers are not in the facts: {', '.join(bad)}"
    retry = messages + [{"role": "assistant", "content": first},
                        {"role": "user", "content": f"The answer is not usable: {problem}. "
                                                    "Write only the answer, copying numbers only from the facts."}]
    try:
        second = clean(llm.chat(retry)["message"]["content"])
    except Exception:  # noqa: BLE001
        second = ""
    bad_again = unsupported(second, report, question) if second else bad
    if second and not bad_again and not looks_like_reasoning(second):
        return Written(second, "model-retry", bad, time.perf_counter() - started, first=first, reason=problem)
    return Written(template(report), "template", bad_again, time.perf_counter() - started, first=first, reason=problem)
