"""SimpleConsolidator：字符数触发的轻量上下文压缩。

这是 spore ``core.agent.memory.Consolidator`` 的精简版本（Step 2），
用字符数近似 token 数，省去精确估算链和多轮压缩逻辑。
适用于 DeepSeek-chat（64K context 窗口，中文场景字符数 ≈ token 数）。

触发策略：
  - 总字符数超过 CHAR_THRESHOLD（40,000）时触发
  - 保留最近 KEEP_RATIO（50%）字符量的消息
  - 其余旧消息通过 LLM 摘要后 in-place 替换内存历史
  - 摘要同时 append 到 history.jsonl（role: "summary"）
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI

from .store import MemoryStore

logger = logging.getLogger(__name__)


class SimpleConsolidator:
    """字符数触发的轻量上下文压缩器。

    设计约束：
    - 不持有独立 LLM 客户端，复用 AgentLoop 的 AsyncOpenAI 实例
    - 压缩在每轮 _turn_done 发布前执行，失败时静默跳过（不中断对话）
    - in-place 修改 history 列表（clear + extend），AgentLoop 持有的引用感知到变化
    """

    CHAR_THRESHOLD: int = 500  # 触发压缩的字符数阈值, 测试用500, 默认40_000
    KEEP_RATIO: float = 0.5        # 保留最近消息的字符比例（目标：50%）

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        store: MemoryStore,
    ) -> None:
        self._client = client
        self._model = model
        self._store = store
        # per-chat-id 并发锁，防止同一会话的两个并发请求同时触发压缩（参考 spore）
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # 估算与边界
    # ------------------------------------------------------------------

    def _estimate_chars(self, history: list[dict[str, Any]]) -> int:
        """返回所有消息 content 的字符总数。"""
        return sum(len(m.get("content", "")) for m in history)

    def _find_keep_boundary(self, history: list[dict[str, Any]]) -> int:
        """从后往前累计字符，找到保留约 KEEP_RATIO 字符量的边界索引。

        返回 keep_from：
          - history[keep_from:] 是保留的近期消息
          - history[:keep_from] 是待压缩的旧消息

        边界向后对齐至 role == "user"，确保保留序列以 user 消息开头
        （避免 LLM 看到孤立的 assistant 消息）。
        """
        total_chars = self._estimate_chars(history)
        target_keep = int(total_chars * self.KEEP_RATIO)

        accumulated = 0
        keep_from = len(history)  # 默认：不压缩

        for i in range(len(history) - 1, -1, -1):
            accumulated += len(history[i].get("content", ""))
            if accumulated >= target_keep:
                keep_from = i
                break

        # 向后移动，直到对齐 user 边界
        while keep_from < len(history) and history[keep_from].get("role") != "user":
            keep_from += 1

        # 兜底：对齐后越界（最后一条是 assistant 且无后续 user）时，
        # 回退到最后一条 user 消息，确保至少保留最近一个完整轮次。
        if keep_from >= len(history):
            for i in range(len(history) - 1, -1, -1):
                if history[i].get("role") == "user":
                    keep_from = i
                    break

        return keep_from

    # ------------------------------------------------------------------
    # 格式化与摘要
    # ------------------------------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        """将消息列表格式化为可读文本，供 LLM 摘要使用。

        格式参考 spore 的 _format_messages：``[timestamp] ROLE: content``。
        tool_calls / tool 类型消息输出摘要标记，避免 Consolidator 崩溃。
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = []
        for m in messages:
            role = m.get("role", "unknown")

            # 工具调用消息：输出摘要标记
            if role == "assistant" and m.get("tool_calls"):
                names = [
                    c.get("function", {}).get("name", "?")
                    for c in m["tool_calls"]
                    if isinstance(c, dict)
                ]
                lines.append(f"[{ts}] ASSISTANT: [TOOL_CALLS: {', '.join(names)}]")
                continue

            if role == "tool":
                content = m.get("content", "").strip()
                lines.append(f"[{ts}] TOOL_RESULT: {content[:200]}")
                continue

            content = m.get("content", "").strip()
            if content:
                lines.append(f"[{ts}] {role.upper()}: {content}")
        return "\n".join(lines)

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """非流式调用 LLM 生成对话摘要。失败时抛出异常（由 maybe_consolidate 捕获）。"""
        formatted = self._format_messages(messages)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个对话摘要助手。请将以下对话历史总结为完整的摘要，"
                        "保留所有关键信息（用户的每一个问题、助手的核心回答、用户提及的个人信息等）。\n\n"
                        "重要规则：\n"
                        "1. 如果输入中包含「[历史摘要]」标记的内容，这是之前对话的摘要，"
                        "必须将其中的所有信息完整保留并整合进新摘要，不得省略任何一条。\n"
                        "2. 新增的对话内容追加到摘要中，不替换旧内容。\n"
                        "3. 摘要使用第三人称，按时间顺序描述，不超过 800 字。"
                    ),
                },
                {"role": "user", "content": formatted},
            ],
            stream=False,
        )
        return response.choices[0].message.content or "[无法生成摘要]"

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def maybe_consolidate(
        self,
        chat_id: str,
        history: list[dict[str, Any]],
        last_consolidated: int = 0,
    ) -> int:
        """检查全量上下文大小，在必要时进行累计压缩并归档摘要。

        累计压缩：to_compress = history[:keep_from]（含任何已有摘要前缀），
        确保每条 summary 是完整历史快照，避免重启后丢失更早摘要。

        Args:
            chat_id: 会话标识
            history: 内存消息列表（in-place 修改）
            last_consolidated: 0（无摘要前缀）或 1（有一条摘要前缀），
                               累计模式下内存中最多只有1条 summary

        Returns:
            0（未压缩）或 1（成功压缩且持久化）。
            只有 append_summary 成功后才返回 1，修复原子性问题。

        用 per-chat-id asyncio.Lock 确保同一会话的并发调用串行执行。
        """
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            return await self._do_consolidate(chat_id, history, last_consolidated)

    async def _do_consolidate(
        self,
        chat_id: str,
        history: list[dict[str, Any]],
        last_consolidated: int,
    ) -> int:
        # 全量估算（含摘要前缀），避免阈值盲区
        total_chars = self._estimate_chars(history)
        if total_chars < self.CHAR_THRESHOLD:
            return last_consolidated

        # 边界基于完整 history（累计压缩）
        keep_from = self._find_keep_boundary(history)
        to_compress = history[:keep_from]   # 含旧摘要前缀
        to_keep = history[keep_from:]

        if not to_compress:
            logger.debug(
                "Consolidator: no-op for chat_id=%s "
                "(all messages within keep boundary, keep_from=%d)",
                chat_id, keep_from,
            )
            return last_consolidated

        # 计算 keep_from_cursor：从 history.jsonl 查询 to_keep 第一条消息的 cursor
        # 内存中的 history 消息不含 cursor 字段，需要读文件推导
        keep_from_cursor = self._store.get_keep_from_cursor(chat_id, len(to_keep))

        logger.info(
            "Consolidator: starting for chat_id=%s "
            "(total_chars=%d >= threshold=%d, compress=%d msgs, keep=%d msgs, "
            "keep_from_cursor=%s)",
            chat_id, total_chars, self.CHAR_THRESHOLD,
            len(to_compress), len(to_keep), keep_from_cursor,
        )

        # LLM 摘要（累计：to_compress 包含旧摘要前缀，让 LLM 看到完整历史）
        try:
            summary = await self._summarize(to_compress)
        except Exception:
            logger.warning(
                "Consolidator: summarization failed for chat_id=%s, skipping",
                chat_id, exc_info=True,
            )
            return last_consolidated

        # 原子持久化：先写磁盘，成功后才替换内存历史
        try:
            self._store.append_summary(chat_id, summary, keep_from_cursor=keep_from_cursor)
        except Exception:
            logger.warning(
                "Consolidator: failed to persist summary for chat_id=%s, "
                "rolling back in-memory state",
                chat_id, exc_info=True,
            )
            return last_consolidated  # 不更新内存，保持一致性

        # 持久化成功后才更新内存：累计模式每次只保留一条摘要前缀
        history.clear()
        history.append({"role": "assistant", "content": f"[历史摘要] {summary}"})
        history.extend(to_keep)

        logger.info(
            "Consolidator: done for chat_id=%s, history now %d msgs "
            "(1 cumulative summary + %d to_keep)",
            chat_id, len(history), len(to_keep),
        )
        return 1  # 累计模式：压缩后 last_consolidated 恒为 1
