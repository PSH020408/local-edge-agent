"""Default tools available to the agent."""

from __future__ import annotations

import ast
import operator
from pathlib import Path

from .time_tools import register_time_tools
from .tools import ToolRegistry

_MAX_READ_CHARS = 8000

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Evaluate arithmetic only. Names, calls and attributes are rejected."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only numbers and + - * / // % ** are allowed")


def build_default_registry(workspace: Path) -> ToolRegistry:
    workspace = workspace.resolve()
    registry = ToolRegistry()

    def _resolve_inside_workspace(path: str) -> Path:
        target = (workspace / path).resolve()
        if target != workspace and workspace not in target.parents:
            raise PermissionError(f"'{path}' is outside the workspace")
        return target

    register_time_tools(registry)

    @registry.register
    def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression exactly. Use this instead of doing math yourself. Numbers only: never use it for dates or times; use the date tools instead.

        Args:
            expression: Arithmetic expression, e.g. "(12.5 * 4) / 3".
        """
        result = _safe_eval(ast.parse(expression, mode="eval"))
        # Trim float noise such as 180390.33333333334 -> 180390.3333333333
        if isinstance(result, float):
            result = int(result) if result.is_integer() else float(f"{result:.10g}")
        return str(result)

    @registry.register
    def list_files(path: str = ".") -> str:
        """List files and folders in a directory inside the workspace.

        Args:
            path: Directory path relative to the workspace root.
        """
        target = _resolve_inside_workspace(path)
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        lines = [f"{e.name}/" if e.is_dir() else e.name for e in entries if not e.name.startswith(".")]
        return "\n".join(lines) or "(empty directory)"

    @registry.register
    def read_file(path: str) -> str:
        """Read a text file inside the workspace.

        Args:
            path: File path relative to the workspace root.
        """
        target = _resolve_inside_workspace(path)
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > _MAX_READ_CHARS:
            return text[:_MAX_READ_CHARS] + f"\n... [truncated, {len(text)} chars total]"
        return text

    return registry
