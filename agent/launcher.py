"""The terminal front door: a menu of what the agent does, a mode per kind of question, and files dropped in from
anywhere on the Mac.

    edge                         -> the menu; pick a mode by number, or just type a question
    edge 배터리 상태 어때           -> answered at once (mode detected), then the session goes on in that mode
    배터리 상태 어때               -> the same, with the shell hook installed (scripts/install_shell.sh)

Why modes: a question asked inside a mode skips the router and goes straight to its agent, and choosing a mode
loads that mode's models in the background while you type (Ollama keeps them warm), so the first answer does
not wait for a model to load.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .device.router import route as device_route

IMAGE_EXT = r"png|jpe?g|gif|webp|bmp|tiff?|heic"
DOC_EXT = r"pdf|pptx"
# A path typed or dropped into the terminal: absolute, ~ or relative, spaces escaped with "\ " or quoted.
PATH = re.compile(rf"""(?:'([^']+\.(?:{IMAGE_EXT}|{DOC_EXT}))'|"([^"]+\.(?:{IMAGE_EXT}|{DOC_EXT}))"|((?:[~/.]|[\w-])(?:[^\s'"]|\\ )*\.(?:{IMAGE_EXT}|{DOC_EXT})))""", re.I)


@dataclass
class Mode:
    key: str
    number: str
    title: str
    scope: str
    engine: str
    examples: list[str] = field(default_factory=list)


MODES = [
    Mode("device", "1", "디바이스 진단 (This Mac)", "배터리 수명·충전 · 전원 모드 · CPU/GPU 부하 · 발열 · 메모리 · 저장장치·포트",
         "센서 판독 + qwen3:4b", ["배터리 교체해야 해?", "왜 이렇게 뜨거워?", "지금 4K 영상 편집 돼?"]),
    Mode("network", "2", "네트워크 진단 (Wi-Fi · Bluetooth)", "연결 품질 · 게임/화상회의/4K 가능 여부 · 공유기 추천 · 블루투스 끊김",
         "실측(핑·속도·스캔) + qwen3:4b", ["게임 해도 돼?", "여기서 어떤 와이파이가 좋아?", "에어팟 자꾸 끊겨"]),
    Mode("image", "3", "이미지 분석 (Vision)", "사진 설명 · 회로/보드 · 도표·그래프 · 손글씨·표지판 · 수식 → LaTeX",
         "qwen3-vl:8b + 계획 qwen3:14b", ["board.jpg 이 보드의 MCU는?", "formula.png 수식을 LaTeX로"]),
    Mode("document", "4", "문서·논문 분석 (PDF · PPT)", "요약 · 수식 해설 · 표·재무제표 계산 · 시험 문제 · 쪽 번호 인용",
         "qwen3:14b + 페이지 판독", ["paper.pdf 요약해줘", "lecture.pdf 시험 문제 3개 만들어줘"]),
    Mode("math", "5", "공학 계산 (Math · Units · Time)", "단위 계산 · dB/링크 버짓 · 회로 · 복소수 · 날짜·시간대",
         "도구 계산 + qwen3:8b ↔ 14b", ["2 W 송신, 10 dBi, 경로손실 100 dB면 수신 전력은?", "뉴욕은 지금 몇 시?"]),
    Mode("auto", "6", "자유 질문 (Auto)", "질문을 보고 알맞은 기능으로 자동 연결", "자동 분류", []),
]
BY_KEY = {m.key: m for m in MODES}
BY_NUMBER = {m.number: m for m in MODES}
MODE_MODELS = {"device": ["device_writer", "device_router"], "network": ["device_writer"],
               "image": ["planner", "vision"], "document": ["planner", "vision"], "math": ["light"], "auto": ["light"]}


def menu() -> str:
    lines = ["", "  Local Edge Agent — 무엇을 도와드릴까요?  (모든 처리는 이 맥 안에서만)", ""]
    for m in MODES:
        lines.append(f"   {m.number}  {m.title}")
        lines.append(f"      {m.scope}")
        lines.append(f"      ↳ {m.engine}")
    lines += ["", "   번호를 고르거나, 바로 질문을 입력하세요.   ?  예시   /menu  메뉴   /exit  종료", ""]
    return "\n".join(lines)


def examples() -> str:
    lines = [""]
    for m in MODES:
        if m.examples:
            lines.append(f"  {m.number} {m.title}")
            lines += [f"     · {e}" for e in m.examples]
    lines.append("  이미지·문서는 파일을 터미널로 끌어다 놓으면 경로가 들어가요.")
    return "\n".join(lines + [""])


def import_files(question: str, workspace: Path, cwd: Path) -> tuple[str, list[str]]:
    """Copy files named in the question from outside the workspace into workspace/inbox, so the sandboxed tools can
    read them, and rewrite the question with the new path. Only files the user named are copied."""
    workspace = workspace.resolve()
    copied = []
    for match in list(PATH.finditer(question)):
        raw = next(g for g in match.groups() if g)
        candidate = Path(raw.replace("\\ ", " ")).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file() or workspace in resolved.parents:
            if resolved.is_file():
                question = question.replace(match.group(0), str(resolved.relative_to(workspace)))
            continue
        inbox = workspace / "inbox"
        inbox.mkdir(exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", resolved.name)
        target = inbox / safe
        if not target.exists() or target.stat().st_size != resolved.stat().st_size:
            shutil.copy2(resolved, target)
        question = question.replace(match.group(0), f"inbox/{safe}")
        copied.append(f"inbox/{safe}")
    return question, copied


def detect_mode(question: str, has_image, has_document) -> str:
    """The mode a question belongs to: a file decides first, then the device router's keyword rules."""
    if has_image(question):
        return "image"
    if has_document(question):
        return "document"
    topic = device_route(question).topic
    if topic == "network":
        return "network"
    if topic in ("battery", "performance"):
        return "device"
    return "math"


def device_topic(mode: str, question: str) -> str:
    """The device agent's topic inside a mode, with no model call: the keyword rules when they are sure (a battery
    question asked in the network mode is still a battery question), otherwise the mode decides."""
    r = device_route(question)
    if r.topic:
        return r.topic
    if mode == "network":
        return "network"
    return "battery" if r.matches.get("battery", 0) > r.matches.get("performance", 0) else "performance"


def warm(host: str, models: list[str], keep_alive: str = "15m") -> threading.Thread:
    """Load models into Ollama in the background (an empty generate request loads a model and keeps it)."""
    def run():
        for model in models:
            try:
                body = json.dumps({"model": model, "keep_alive": keep_alive}).encode()
                urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", data=body,
                                                              headers={"Content-Type": "application/json"}), timeout=120).read()
            except Exception:  # noqa: BLE001 - warming is an optimisation only
                pass
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


class Session:
    """Answers questions in one mode; "auto" detects the mode per question."""

    def __init__(self, agent, planner, chooser, workspace: Path, cwd: Path, models: dict[str, str], host: str,
                 on_event=lambda message: None) -> None:
        self.agent, self.planner, self.chooser = agent, planner, chooser
        self.workspace, self.cwd, self.models, self.host = workspace, cwd, models, host
        self.on_event = on_event
        self.mode = "auto"

    def set_mode(self, key: str) -> None:
        self.mode = key
        names = [self.models[k] for k in MODE_MODELS.get(key, []) if self.models.get(k)]
        if names:
            warm(self.host, list(dict.fromkeys(names)))

    def _has(self, kind):
        part = getattr(self.planner, kind, None) if self.planner else None
        return (lambda q: part.applies(q) is not None) if part else (lambda q: False)

    def ask(self, question: str) -> tuple[str, str]:
        """(answer, mode used)."""
        question, copied = import_files(question, self.workspace, self.cwd)
        for path in copied:
            self.on_event(f"file copied into the workspace: {path}")
        mode = self.mode
        if mode == "auto":
            mode = detect_mode(question, self._has("images"), self._has("documents"))
            self.on_event(f"mode: {BY_KEY[mode].title}")
        answer = self._dispatch(mode, question)
        return answer, mode

    def _dispatch(self, mode: str, question: str) -> str:
        p = self.planner
        if mode in ("device", "network") and p and p.device:
            answer = p.device.diagnose(question, device_topic(mode, question)).answer
        elif mode == "image" and p and p.images:
            if not p.images.applies(question):
                return "이미지 파일 경로를 질문에 함께 넣어 주세요. 파일을 터미널로 끌어다 놓으면 경로가 들어가요."
            answer = p.images.run(question)
        elif mode == "document" and p and p.documents:
            if not p.documents.applies(question):
                return "PDF나 PPT 파일 경로를 질문에 함께 넣어 주세요. 파일을 터미널로 끌어다 놓으면 경로가 들어가요."
            answer = p.documents.run(question)
        else:
            return self.chooser.run(question) if self.chooser else self.agent.run(question)
        self.agent.remember(question, answer)
        return answer
