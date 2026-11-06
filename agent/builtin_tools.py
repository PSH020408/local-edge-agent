"""Default tools available to the agent."""

from __future__ import annotations

from pathlib import Path

from .document_tools import DOCUMENT_EXTENSIONS, load_document
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
        if target.suffix.lower() in DOCUMENT_EXTENSIONS:
            raise ValueError(f"'{path}' is a document. Use read_document to read its pages.")
        raw = target.read_bytes()
        if b"\x00" in raw[:4096]:
            raise ValueError(f"'{path}' is a binary file and cannot be read as text.")
        text = raw.decode("utf-8", errors="replace")
        if len(text) > _MAX_READ_CHARS:
            return text[:_MAX_READ_CHARS] + f"\n... [truncated, {len(text)} chars total]"
        return text

    @registry.register
    def read_document(path: str, pages: str = "") -> str:
        """Read the text of a PDF or PowerPoint file page by page, with [p.N] page markers.

        Args:
            path: Document path relative to the workspace root (.pdf or .pptx).
            pages: Optional pages to read, such as "3" or "2-5" or "1,4,7". Empty reads from the start.
        """
        target = _resolve_inside_workspace(path)
        document = load_document(target)
        selected = _parse_pages(pages, len(document.pages)) if pages else [p.number for p in document.pages]
        blocks, size = [], 0
        for number in selected:
            page = document.page(number)
            flags = (" (equations are not reliable in this text)" if page.math else "") + (
                " (has a figure; use the document planner or describe_image for it)" if page.images else ""
            )
            block = f"[p.{number}] {page.title}{flags}\n{page.text}"
            if size + len(block) > _MAX_READ_CHARS:
                blocks.append(f"... [stopped at p.{number}; ask for later pages with pages=\"{number}-{selected[-1]}\"]")
                break
            blocks.append(block)
            size += len(block)
        return f"{target.name}: {document.summary()}\n\n" + "\n\n".join(blocks)

    return registry


def _parse_pages(spec: str, count: int) -> list[int]:
    numbers: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            low, high = part.split("-", 1)
            numbers.extend(range(int(low), int(high) + 1))
        elif part:
            numbers.append(int(part))
    valid = [n for n in dict.fromkeys(numbers) if 1 <= n <= count]
    if not valid:
        raise ValueError(f"no valid pages in '{spec}'; the document has {count} pages")
    return valid
