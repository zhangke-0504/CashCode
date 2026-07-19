"""Filesystem tools: read, write, edit, list.

参考 spore ``core.agent.tools.filesystem``，简化版：
- 安全策略：所有路径校验限制在 WORKSPACE_DIR 内
- 去掉多媒体处理、session 路径、技能文件系统等复杂机制
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool


def _safe_path(workspace: Path, path: str) -> Path:
    """Resolve path relative to workspace and verify it stays inside.

    Raises PermissionError if the resolved path escapes the workspace.
    """
    resolved = (workspace / path).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        raise PermissionError(f"路径 {path!r} 超出工作目录，拒绝访问")
    return resolved


class ReadFileTool(Tool):
    """读取 workspace 内的文件内容。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "读取工作目录中指定文件的内容。path 使用相对于工作目录的路径。"
            "适用于查看代码、配置文件、日志等。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对于工作目录的文件路径"},
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            file_path = _safe_path(self._workspace, path)
        except PermissionError as e:
            return str(e)
        if not file_path.exists():
            return f"文件不存在：{path}"
        if not file_path.is_file():
            return f"{path} 不是文件"
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if len(lines) > 500:
                content = "\n".join(lines[:500]) + f"\n\n[内容已截断，共 {len(lines)} 行]"
            return content
        except OSError as e:
            return f"读取失败：{e}"


class WriteFileTool(Tool):
    """在 workspace 内创建或覆盖文件。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "在工作目录中创建或覆盖文件。path 使用相对路径，不存在的父目录会自动创建。"
            "⚠️ 会直接覆盖已有内容，修改现有文件请用 edit_file。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对于工作目录的文件路径"},
                "content": {"type": "string", "description": "写入的文件内容"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            file_path = _safe_path(self._workspace, path)
        except PermissionError as e:
            return str(e)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"已写入 {path}（{len(content)} 字符）"
        except OSError as e:
            return f"写入失败：{e}"


class EditFileTool(Tool):
    """在 workspace 内的文件中精确替换字符串。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "在文件中替换第一处 old_string 为 new_string。"
            "old_string 必须在文件中唯一存在；不存在时返回错误，文件不被修改。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对于工作目录的文件路径"},
                "old_string": {"type": "string", "description": "要替换的原始字符串（必须精确匹配）"},
                "new_string": {"type": "string", "description": "替换后的新字符串"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, path: str, old_string: str, new_string: str, **kwargs: Any) -> str:
        try:
            file_path = _safe_path(self._workspace, path)
        except PermissionError as e:
            return str(e)
        if not file_path.exists():
            return f"文件不存在：{path}"
        try:
            original = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"读取失败：{e}"

        count = original.count(old_string)
        if count == 0:
            return f"未找到要替换的内容，请检查 old_string 是否正确（文件：{path}）"
        if count > 1:
            return (
                f"old_string 在文件中出现 {count} 次，请提供更多上下文使其唯一"
            )

        updated = original.replace(old_string, new_string, 1)
        try:
            file_path.write_text(updated, encoding="utf-8")
            return f"已替换 {path} 中的指定内容"
        except OSError as e:
            return f"写入失败：{e}"


class ListDirTool(Tool):
    """列出 workspace 内目录的内容。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return (
            "列出工作目录中指定目录的文件和子目录。"
            "path 留空则列出工作目录根目录。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于工作目录的目录路径，留空则列出根目录",
                    "default": "",
                },
            },
            "required": [],
        }

    async def execute(self, path: str = "", **kwargs: Any) -> str:
        try:
            dir_path = _safe_path(self._workspace, path) if path else self._workspace.resolve()
        except PermissionError as e:
            return str(e)
        if not dir_path.exists():
            return f"目录不存在：{path or '（工作目录）'}"
        if not dir_path.is_dir():
            return f"{path} 不是目录"
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = [f"目录：{path or '（工作目录）'}\n"]
            for item in items[:200]:
                tag = "文件" if item.is_file() else " 目录"
                lines.append(f"[{tag}] {item.name}")
            if len(items) > 200:
                lines.append(f"\n（仅显示前 200 条，共 {len(items)} 项）")
            return "\n".join(lines)
        except OSError as e:
            return f"列目录失败：{e}"
