"""Tool registry: turns plain Python functions into LLM-callable tools.

A function's type hints and docstring are converted into a JSON schema,
so adding a new tool only requires writing a normal, documented function.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]
    requires_confirmation: bool = False

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _parse_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Return (summary, {arg_name: description}) from a Google-style docstring."""
    lines = inspect.cleandoc(doc or "").splitlines()
    summary_lines: list[str] = []
    arg_docs: dict[str, str] = {}
    in_args = False
    for line in lines:
        stripped = line.strip()
        if stripped in ("Args:", "Arguments:"):
            in_args = True
            continue
        if in_args:
            if not stripped:
                continue
            if ":" in stripped and line.startswith((" ", "\t")):
                name, desc = stripped.split(":", 1)
                arg_docs[name.strip()] = desc.strip()
                continue
            in_args = False
        if not in_args and stripped and not arg_docs:
            summary_lines.append(stripped)
    return " ".join(summary_lines), arg_docs


def build_tool(func: Callable[..., Any], requires_confirmation: bool = False) -> Tool:
    summary, arg_docs = _parse_docstring(func.__doc__ or "")
    hints = get_type_hints(func)
    properties: dict[str, dict] = {}
    required: list[str] = []
    for name, param in inspect.signature(func).parameters.items():
        prop = {"type": _JSON_TYPES.get(hints.get(name, str), "string")}
        if name in arg_docs:
            prop["description"] = arg_docs[name]
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return Tool(
        name=func.__name__,
        description=summary,
        parameters={"type": "object", "properties": properties, "required": required},
        func=func,
        requires_confirmation=requires_confirmation,
    )


def _coerce(value: Any, json_type: str) -> Any:
    """Models sometimes send numbers or booleans as strings ("100", "true"). Convert them.

    If a string cannot be converted, it is passed through unchanged so the tool
    itself can handle it (for example, convert_units evaluates a formula).
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if json_type in ("integer", "number"):
        try:
            number = float(text)
        except ValueError:
            return value
        return int(number) if json_type == "integer" and number.is_integer() else number
    if json_type == "boolean":
        if text.lower() in ("true", "yes", "1"):
            return True
        if text.lower() in ("false", "no", "0", ""):
            return False
        raise ValueError(f"expected true or false, got '{value}'")
    return value


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, func: Callable | None = None, *, requires_confirmation: bool = False):
        """Register a function as a tool. Usable as @registry.register or @registry.register(...)."""

        def decorator(f: Callable) -> Callable:
            tool = build_tool(f, requires_confirmation)
            self._tools[tool.name] = tool
            return f

        return decorator(func) if func is not None else decorator

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def call(self, name: str, arguments: dict) -> str:
        """Validate arguments and run a tool. Errors are returned as text for the model to see."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'. Available tools: {', '.join(self._tools)}"
        props = tool.parameters["properties"]
        unknown = set(arguments) - set(props)
        if unknown:
            # Run 7: the model sent to_unit to calculator. Point to tools that accept it.
            # Prefer tools that accept every argument given, then any that accept the unknown ones.
            others = [t for t in self._tools.values() if t.name != name]
            owners = [t.name for t in others if set(arguments) <= set(t.parameters["properties"])] or [
                t.name for t in others if unknown <= set(t.parameters["properties"])
            ]
            hint = f" Tools that accept {sorted(unknown)}: {', '.join(owners)}." if owners else ""
            return (
                f"Error: unexpected arguments {sorted(unknown)} for tool '{name}'. "
                f"It accepts: {', '.join(props) or 'no arguments'}.{hint}"
            )
        missing = [p for p in tool.parameters["required"] if p not in arguments]
        if missing:
            return f"Error: missing required arguments {missing} for tool '{name}'."
        try:
            arguments = {k: _coerce(v, props[k]["type"]) for k, v in arguments.items()}
            result = tool.func(**arguments)
        except Exception as exc:  # surface failures to the model instead of crashing
            return f"Error: {type(exc).__name__}: {exc}"
        return str(result)
