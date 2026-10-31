"""The agent loop: ask the model, run requested tools, feed results back, repeat."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .tools import ToolRegistry

DEFAULT_SYSTEM_PROMPT = """You are a local assistant running on the user's Mac.
You can call tools to get real information. Rules:
- Use a tool whenever it gives a more accurate answer than guessing (time, math, files).
- For dates, weekdays, durations and time zones, always use the date tools. Never do calendar math yourself or with the calculator.
- Report dates and numbers exactly as the tool returned them. Never convert units, angles or rounding in your head; if you need another form, call a tool again.
- Never invent file contents; read the file first.
- If a tool returns an error, fix the arguments or explain the problem.
- Keep final answers short and direct. Answer in the user's language."""


class ChatModel(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict: ...


class TraceLogger:
    """Writes every step of a session to a JSONL file for debugging and evaluation."""

    def __init__(self, log_dir: Path | None) -> None:
        self.path = None
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            self.path = log_dir / f"session_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def log(self, event: str, **data) -> None:
        if self.path is None:
            return
        record = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class Agent:
    def __init__(
        self,
        llm: ChatModel,
        registry: ToolRegistry,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = 8,
        max_repeated_failures: int = 2,
        confirm: Callable[[str, dict], bool] | None = None,
        on_tool_call: Callable[[str, dict, str], None] | None = None,
        logger: TraceLogger | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.max_repeated_failures = max_repeated_failures
        self.confirm = confirm or (lambda name, args: False)
        self.on_tool_call = on_tool_call
        self.logger = logger or TraceLogger(None)
        self.reset()

    def reset(self) -> None:
        self.messages: list[dict] = [{"role": "system", "content": self.system_prompt}]

    def run(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        self.logger.log("user", content=user_input)
        # Run 6: qwen3:14b sent the same failing calculator call six times in a row.
        # Track failed calls so a repeat gets a clear "change your approach" message.
        self._failed_calls: dict[str, int] = {}
        empty_retries = 0

        for step in range(1, self.max_steps + 1):
            response = self.llm.chat(self.messages, tools=self.registry.schemas())
            message = response["message"]
            tool_calls = message.get("tool_calls") or []
            self.messages.append(
                {"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls}
            )
            self.logger.log(
                "assistant",
                step=step,
                content=message.get("content", ""),
                tool_calls=tool_calls,
                stats=response.get("stats"),
            )

            if not tool_calls:
                content = message.get("content", "").strip()
                if content or empty_retries >= 1:
                    return content or "[The model returned an empty answer.]"
                # Run 8: qwen3:8b returned an empty reply with no tool call. Ask once more.
                empty_retries += 1
                self.messages.append(
                    {"role": "user", "content": "Your last reply was empty. Answer the question, or call a tool if you need one."}
                )
                self.logger.log("empty_reply_retry", step=step)
                continue

            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments") or {}
                if isinstance(args, str):  # some models return arguments as a JSON string
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                if self._failed_calls.get(key, 0) >= self.max_repeated_failures:
                    self.logger.log("stopped", reason="repeated_failure", call=key)
                    return (
                        f"[Stopped: the same {name} call failed {self._failed_calls[key]} times. "
                        "The question may need a different tool or approach.]"
                    )
                if key in self._failed_calls:
                    result = (
                        "Error: you already made this exact call and it failed. Do not repeat it. "
                        "Change the arguments or use a different tool."
                    )
                else:
                    result = self._execute(name, args)
                if result.startswith("Error"):
                    self._failed_calls[key] = self._failed_calls.get(key, 0) + 1
                self.messages.append({"role": "tool", "tool_name": name, "content": result})
                self.logger.log("tool", step=step, name=name, arguments=args, result=result)
                if self.on_tool_call:
                    self.on_tool_call(name, args, result)

        self.logger.log("stopped", reason="max_steps")
        return f"[Stopped after {self.max_steps} steps without a final answer.]"

    def _execute(self, name: str, args: dict) -> str:
        tool = self.registry.get(name)
        if tool is not None and tool.requires_confirmation and not self.confirm(name, args):
            return "Error: the user denied this action."
        return self.registry.call(name, args)
