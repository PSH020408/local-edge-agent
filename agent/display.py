"""Terminal display of tool calls, with guard interventions made visible.

Tool results carry the effects of code-level guards as notes and verdicts (an ignored
focus, a downscaled image, a cut-off loop, a blocked repeat, CONFIRMED / UNCERTAIN).
The plain preview cut results at 200 characters, so these were usually invisible.
Each such line is now printed in full on its own, marked with a gear.
"""

from __future__ import annotations

import json

DIM, YELLOW, RESET = "\033[2m", "\033[33m", "\033[0m"

GUARD_PREFIXES = (
    "[note:", "[warning:", "Note:", "NOT FOUND:", "NOT LOCATED:",
    "CONFIRMED:", "CONFIRMED CHARACTERS:", "PARTLY CONFIRMED:", "PARTLY UNCLEAR:", "UNCERTAIN:", "Error: you already made this exact call",
)


def guard_lines(result: str) -> list[str]:
    """Lines of a tool result that report a guard or a verdict."""
    lines = []
    for line in result.splitlines():
        text = line.strip()
        if text.startswith(GUARD_PREFIXES):
            lines.append(text.strip("[]").replace("note: ", "").replace("warning: ", "warning: "))
    return lines


def format_event(message: str, color: bool = True) -> str:
    """A planner step (plan, check, retry), shown like a guard line."""
    yellow, reset = (YELLOW, RESET) if color else ("", "")
    return f"{yellow}  \u2699 {message}{reset}"


def format_tool_call(name: str, args: dict, result: str, color: bool = True) -> str:
    dim, yellow, reset = (DIM, YELLOW, RESET) if color else ("", "", "")
    guards = guard_lines(result)
    rest = "\n".join(l for l in result.splitlines() if l.strip() and not l.strip().startswith(GUARD_PREFIXES))
    preview = rest if len(rest) < 200 else rest[:200] + "..."
    out = [f"{dim}  -> {name}({json.dumps(args, ensure_ascii=False)}){reset}"]
    out += [f"{yellow}     \u2699 {g}{reset}" for g in guards]
    if preview:
        out.append(f"{dim}     {preview}{reset}")
    return "\n".join(out)
