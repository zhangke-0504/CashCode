"""SaveMemoryTool：LLM 主动将重要事实即时写入全局 MEMORY.md。

参考 spore ``core.agent.tools.memory.SaveMemoryTool``，去掉 scope/confidence/project 等
复杂机制，保留核心功能：追加一条带时间戳的事实到 MEMORY.md，并去重。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .base import Tool

if TYPE_CHECKING:
    from app.memory.store import MemoryStore


class SaveMemoryTool(Tool):
    """即时保存重要事实到全局 MEMORY.md。

    触发时机（由 LLM 判断）：
    - 用户明确要求记住某事（"帮我记住..."、"记一下..."）
    - LLM 判断某信息对未来会话有长期价值（用户身份、偏好、项目背景等）
    不应用于：临时性问答、闲聊内容。
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return (
            "将重要信息即时保存到长期记忆，使其在未来的所有对话中都可被访问。"
            "适用场景：用户明确要求记住某事，或你判断某信息具有跨会话的长期价值"
            "（如用户姓名、职业、偏好、正在进行的项目等）。"
            "不要对临时性闲聊、单次查询结果使用此工具。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "要保存的事实，写成清晰的陈述句。"
                        "例如：'用户叫张珂，是 Python 开发工程师'"
                        "或 '用户正在开发 CashCode 项目，参考 spore 架构'"
                    ),
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str, **kwargs: Any) -> str:
        content = content.strip()
        if not content:
            return "内容为空，未保存。"

        existing = self._store.read_memory()
        if content in existing:
            return "该信息已存在于长期记忆中，无需重复保存。"

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{ts}] {content}"

        new_memory = (existing.rstrip("\n") + "\n" + entry + "\n") if existing else (entry + "\n")
        self._store.write_memory(new_memory)

        return f"已保存到长期记忆：{content}"
