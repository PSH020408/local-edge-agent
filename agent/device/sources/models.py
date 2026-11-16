"""Models that Ollama holds in memory (`/api/ps`), a large and easily freed part of this Mac's memory.

Run D6 (2026-11-17): the live cases found memory short (16% available, swapping), and the cause was the
agent's own models, still loaded from the speed check and the answers before (qwen3:14b alone is about
10 GB). A memory diagnosis that cannot see them blames "large apps"; the admission check, which
assumed every job loads its model, counted a model that was already loaded as needed twice.
"""

from __future__ import annotations

import json

from ..readings import Reading, now, reading


def parse(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    try:
        models = json.loads(text).get("models", []) if text.strip() else None
    except (ValueError, AttributeError):
        models = None
    if models is None:
        return [reading("models.loaded", None, "text", time), reading("models.loaded_bytes", None, "bytes", time)]
    listing = "; ".join(f"{m.get('name')} {m.get('size', 0) / 1e9:.1f} GB" for m in models)
    return [reading("models.loaded", listing, "text", time),
            reading("models.loaded_bytes", sum(m.get("size", 0) for m in models), "bytes", time)]


def loaded(text: str) -> dict[str, int]:
    """{model name: bytes} from the /api/ps output."""
    try:
        return {m.get("name"): m.get("size", 0) for m in json.loads(text).get("models", [])}
    except (ValueError, AttributeError):
        return {}


def read(shell) -> tuple[list[Reading], dict[str, int]]:
    out = shell.run("ollama_ps")
    text = out.text if out.ok else ""
    return parse(text), loaded(text)
