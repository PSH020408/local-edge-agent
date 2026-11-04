"""Default tools available to the agent."""

from __future__ import annotations

from pathlib import Path

from .math_tools import register_math_tools
from .time_tools import register_time_tools
from .tools import ToolRegistry
from .vision_tools import IMAGE_EXTENSIONS, VisionConfig, register_vision_tools

_MAX_READ_CHARS = 8000


def build_default_registry(
    workspace: Path,
    vision_client=None,
    vision_config: VisionConfig | None = None,
    reasoning_client=None,
) -> ToolRegistry:
    """Build all tools. describe_image is added only when a vision client is given."""
    workspace = workspace.resolve()
    registry = ToolRegistry()

    def _resolve_inside_workspace(path: str) -> Path:
        target = (workspace / path).resolve()
        if target != workspace and workspace not in target.parents:
            raise PermissionError(f"'{path}' is outside the workspace")
        return target

    register_time_tools(registry)
    register_math_tools(registry)
    if vision_client is not None:
        register_vision_tools(
            registry, _resolve_inside_workspace, vision_client, vision_config or VisionConfig(), reasoning_client
        )

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
        if target.suffix.lower() in IMAGE_EXTENSIONS:
            raise ValueError(f"'{path}' is an image. Use describe_image to look at it.")
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            raise ValueError(f"'{path}' is a binary file and cannot be read as text.")
        text = raw.decode("utf-8", errors="replace")
        if len(text) > _MAX_READ_CHARS:
            return text[:_MAX_READ_CHARS] + f"\n... [truncated, {len(text)} chars total]"
        return text

    return registry
