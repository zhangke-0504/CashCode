"""Shell tool: ExecTool (执行 shell 命令).

参考 spore ``core.agent.tools.shell``，简化版：
- asyncio subprocess，cwd=WORKSPACE_DIR
- timeout 30秒，stdout+stderr 合并截断 4096 字符
- 不传递危险环境变量，但继承用户进程的基本环境
"""
from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Any

from .base import Tool

_EXEC_TIMEOUT = 30.0
_OUTPUT_MAX = 4096


class ExecTool(Tool):
    """在工作目录中执行 shell 命令。"""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return (
            "在工作目录中执行 shell 命令，返回 stdout + stderr 合并输出（最多 4096 字符）。"
            "适用于运行脚本、git 操作、列出进程、安装依赖等。"
            "⚠️ 命令在本机执行，请谨慎使用破坏性操作。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令，如 `git status`、`python script.py`",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str, **kwargs: Any) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=PIPE,
                stderr=PIPE,
                cwd=str(self._workspace),
            )
        except Exception as e:
            return f"启动命令失败：{e}"

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_EXEC_TIMEOUT
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return f"命令执行超时（{_EXEC_TIMEOUT}s）：{command}"

        output = (stdout + stderr).decode("utf-8", errors="replace")
        if len(output) > _OUTPUT_MAX:
            output = output[:_OUTPUT_MAX] + f"\n\n[输出已截断，共 {len(output)} 字符]"

        exit_code = proc.returncode
        prefix = f"$ {command}\n退出码：{exit_code}\n\n"
        return prefix + (output or "(无输出)")
