"""Minimal HTTP client for the Ollama chat API (standard library only)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Every model call is appended here: which model, how long loading, reading the prompt and
# writing the answer took, and the memory the model held. The log is the profile of where the
# time of a run goes (logs/ is not committed). Set to None to turn it off.
CALL_LOG: Path | None = Path(__file__).resolve().parent.parent / "logs" / "model_calls.jsonl"


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        think: bool = False,
        options: dict | None = None,
        timeout: float = 300,
        keep_alive: str | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.think = think
        self.options = options or {}
        self.timeout = timeout
        self.keep_alive = keep_alive  # e.g. "5m", or "0" to unload the model right after the call

    def chat(self, messages: list[dict], tools: list[dict] | None = None, format: dict | str | None = None) -> dict:
        """Send one chat request. Returns {"message": {...}, "stats": {...}}.

        format: a JSON schema (or "json") that forces the reply into that structure
        (Ollama structured outputs). Used by the planner so a small model cannot drift.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "options": self.options,
        }
        if tools:
            payload["tools"] = tools
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        if format is not None:
            payload["format"] = format
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise LLMError(f"Ollama returned HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(
                f"Cannot reach Ollama at {self.host}. Is it running? (brew services start ollama)"
            ) from exc

        eval_s = data.get("eval_duration", 0) / 1e9
        prompt_s = data.get("prompt_eval_duration", 0) / 1e9
        stats = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "total_s": round(data.get("total_duration", 0) / 1e9, 2),
            "gen_tok_per_s": round(data.get("eval_count", 0) / eval_s, 1) if eval_s else None,
            "load_s": round(data.get("load_duration", 0) / 1e9, 2),
            "prompt_s": round(prompt_s, 2),
            "gen_s": round(eval_s, 2),
        }
        self._log_call(messages, stats, time.monotonic() - started)
        return {"message": data["message"], "stats": stats}

    def _log_call(self, messages: list[dict], stats: dict, wall_s: float) -> None:
        """One line per call in CALL_LOG; never lets logging break a call."""
        if CALL_LOG is None:
            return
        try:
            record = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": self.model,
                "images": sum(len(m.get("images") or []) for m in messages),
                "num_ctx": self.options.get("num_ctx"),
                "wall_s": round(wall_s, 2),
                **stats,
                "loaded": self._loaded(),
            }
            CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CALL_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except Exception:  # noqa: BLE001 - profiling only
            pass

    def _loaded(self) -> list[dict]:
        """Models Ollama holds in memory after the call (GB), from /api/ps."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/ps", timeout=2) as response:
                models = json.loads(response.read()).get("models", [])
            return [{"model": m.get("name"), "gb": round(m.get("size", 0) / 1e9, 1),
                     "gpu_gb": round(m.get("size_vram", 0) / 1e9, 1)} for m in models]
        except Exception:  # noqa: BLE001
            return []
