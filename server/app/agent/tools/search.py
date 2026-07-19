"""Search tools: GlobTool (文件名模式匹配) and GrepTool (内容搜索).

参考 spore ``core.agent.tools.search``，简化版：
- GlobTool: pathlib rglob，最多100条结果
- GrepTool: 正则搜索文件内容，最多50条结果
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool
from .filesystem import _safe_path

_GLOB_MAX = 100
_GREP_MAX = 50
_BINARY_THRESHOLD = 8192  # skip files larger than 8KB for grep, or binary-looking


def _is_likely_binary(path: Path) -> bool:
    """Quick heuristic: read first 512 bytes and check for null bytes."""
    try:
        chunk = path.read_bytes()[:512]
        return b"\x00" in chunk
    except OSError:
        return True


class GlobTool(Tool):
    """按文件名模式在 workspace 中查找文件。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "按文件名模式在工作目录中查找文件。"
            "pattern 支持 glob 语法，如 `**/*.py`（所有 Python 文件）、`src/*.ts`。"
            "返回匹配的相对路径列表（最多100条）。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，如 `**/*.py`、`*.json`",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起点（相对路径，留空则从工作目录根开始）",
                    "default": "",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = "", **kwargs: Any) -> str:
        try:
            base = _safe_path(self._workspace, path) if path else self._workspace.resolve()
        except PermissionError as e:
            return str(e)
        if not base.is_dir():
            return f"目录不存在：{path or '工作目录'}"

        try:
            matches = sorted(base.rglob(pattern))[:_GLOB_MAX]
        except Exception as e:
            return f"匹配失败：{e}"

        if not matches:
            return f"未找到匹配 `{pattern}` 的文件"

        lines = [f"匹配 `{pattern}`（共 {len(matches)} 条）：\n"]
        for m in matches:
            try:
                rel = m.relative_to(self._workspace)
            except ValueError:
                rel = m
            tag = "/" if m.is_dir() else ""
            lines.append(f"  {rel}{tag}")

        return "\n".join(lines)


class GrepTool(Tool):
    """在 workspace 文件内容中搜索正则表达式。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "在工作目录的文件内容中搜索正则表达式。"
            "返回匹配行（格式：文件名:行号: 内容），最多50条。"
            "可用 file_pattern 限制搜索的文件类型，如 `*.py`。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式，如 `import torch`、`def \\w+`",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起点（相对路径，留空则从根开始）",
                    "default": "",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "文件名 glob 过滤，如 `*.py`、`*.ts`（留空则搜索所有文本文件）",
                    "default": "",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str = "",
        file_pattern: str = "",
        **kwargs: Any,
    ) -> str:
        try:
            base = _safe_path(self._workspace, path) if path else self._workspace.resolve()
        except PermissionError as e:
            return str(e)

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"无效的正则表达式：{e}"

        file_glob = file_pattern or "**/*"
        try:
            candidates = [p for p in base.rglob(file_glob) if p.is_file()]
        except Exception as e:
            return f"搜索失败：{e}"

        results: list[str] = []
        for file_path in candidates:
            if _is_likely_binary(file_path):
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    try:
                        rel = file_path.relative_to(self._workspace)
                    except ValueError:
                        rel = file_path
                    results.append(f"{rel}:{lineno}: {line.rstrip()}")
                    if len(results) >= _GREP_MAX:
                        break
            if len(results) >= _GREP_MAX:
                break

        if not results:
            return f"未找到匹配 `{pattern}` 的内容"

        header = f"匹配 `{pattern}`（共 {len(results)} 条）：\n"
        return header + "\n".join(results)
