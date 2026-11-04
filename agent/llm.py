"""Minimal HTTP client for the Ollama chat API (standard library only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


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
        stats = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "total_s": round(data.get("total_duration", 0) / 1e9, 2),
            "gen_tok_per_s": round(data.get("eval_count", 0) / eval_s, 1) if eval_s else None,
        }
        return {"message": data["message"], "stats": stats}
