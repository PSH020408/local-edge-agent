"""Default tools available to the agent."""

from __future__ import annotations

from pathlib import Path

from .math_tools import register_math_tools
from .time_tools import register_time_tools
from .tools import ToolRegistry

_MAX_READ_CHARS = 8000


def build_default_registry(workspace: Path) -> ToolRegistry:
    workspace = workspace.resolve()
    registry = ToolRegistry()

    def _resolve_inside_workspace(path: str) -> Path:
        target = (workspace / path).resolve()
        if target != workspace and workspace not in target.parents:
            raise PermissionError(f"'{path}' is outside the workspace")
        return target

    register_time_tools(registry)
    register_math_tools(registry)

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
