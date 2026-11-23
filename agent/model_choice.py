"""Which model answers a general question: the light one, or the heavy one when the question looks hard or the
light one could not finish.

Questions about the Mac, its network, images and documents already go to their own agents and models
(main.QuestionRouter); this is for everything else, the agent loop with its tools. Two steps:

1. Before the run, judged by code from the question alone (no model call, so no time spent):
   - quantities: four or more numbers with the problem (dates count as one) suggest a multi-step calculation;
   - parts: "and", "then", several question marks, or a list of things to find;
   - reasoning words: derive, prove, compare, design, analyse, why, step by step (and the Korean equivalents);
   - length: a long problem statement;
   - lookups: a date, a weekday, the time, a single conversion are light whatever else is in them.
   Two points or more: heavy.
2. After a light run, escalate to the heavy model when the light one did not produce an answer: it stopped at
   the step limit, repeated a failing tool call, or returned nothing. The light attempt is removed from the
   conversation, so the heavy model starts from the question.

Why: the heavy model (qwen3:14b) is slower and needs more memory; most everyday questions are lookups and single
conversions that the light model (qwen3:8b) answers with a tool in seconds. Experiment Q1 (scripts/run_model_choice.py)
compares auto against each model alone on a set with known answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DATE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b")
NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")
PARTS = re.compile(r"\band\b|\bthen\b|그리고|그다음|그 다음|각각|하고 나서|및", re.I)
LIST_AFTER_COLON = re.compile(r":[^:?]*,")
REASONING = re.compile(r"deriv|prove|proof|compar|design|analy[sz]|optimi[sz]|trade-?off|why\b|step by step|explain how"
                       r"|유도|증명|비교|설계|분석|최적|원리|왜|단계별", re.I)
LOOKUP = re.compile(r"what time|time in|what date|which date|days? (after|before|until|between)|weekday|day of the week"
                    r"|몇 시|며칠|요일|날짜|시간대", re.I)
STOPPED = ("[Stopped", "[The model returned an empty answer")


@dataclass
class Assessment:
    level: str                         # light | heavy
    score: int
    reasons: list[str] = field(default_factory=list)


def assess(question: str) -> Assessment:
    q = DATE.sub(" DATE ", question)
    reasons, score = [], 0
    numbers = NUMBER.findall(q)
    if len(numbers) >= 4:
        score += 2
        reasons.append(f"{len(numbers)} quantities")
    elif len(numbers) == 3:
        score += 1
        reasons.append("3 quantities")
    if PARTS.search(q) or q.count("?") >= 2 or LIST_AFTER_COLON.search(q):
        score += 1
        reasons.append("several parts")
    if REASONING.search(q):
        score += 2
        reasons.append("reasoning asked")
    if len(question) >= 160:
        score += 1
        reasons.append("long problem")
    if LOOKUP.search(q):
        score -= 2
        reasons.append("a lookup")
    return Assessment("heavy" if score >= 2 else "light", score, reasons)


def needs_escalation(answer: str) -> bool:
    return answer.strip().startswith(STOPPED)


@dataclass
class Choice:
    model: str
    assessment: Assessment
    escalated: bool = False
    first_answer: str = ""


class ModelChooser:
    """Runs a question on the agent loop with the model the question needs."""

    def __init__(self, agent, light, heavy, on_event=None) -> None:
        self.agent, self.light, self.heavy = agent, light, heavy
        self.on_event = on_event or (lambda message: None)
        self.last: Choice | None = None

    def _name(self, llm) -> str:
        return getattr(llm, "model", str(llm))

    def run(self, question: str) -> str:
        a = assess(question)
        first = self.heavy if a.level == "heavy" else self.light
        why = ", ".join(a.reasons) or "a short question"
        self.on_event(f"model: {self._name(first)} ({a.level}: {why})")
        start = len(self.agent.messages)
        answer = self._run_with(first, question)
        choice = Choice(self._name(first), a)
        if first is self.light and self.light is not self.heavy and needs_escalation(answer):
            self.on_event(f"model: {self._name(self.heavy)} (the light model did not finish: {answer[:60]})")
            del self.agent.messages[start:]
            choice = Choice(self._name(self.heavy), a, escalated=True, first_answer=answer)
            answer = self._run_with(self.heavy, question)
        self.agent.logger.log("model_choice", model=choice.model, level=a.level, score=a.score,
                              reasons=a.reasons, escalated=choice.escalated)
        self.last = choice
        return answer

    def _run_with(self, llm, question: str) -> str:
        saved = self.agent.llm
        self.agent.llm = llm
        try:
            return self.agent.run(question)
        finally:
            self.agent.llm = saved
