"""SimpleAgentLoop：读取 InboundMessage，调用 DeepSeek（含工具），再发布 OutboundMessage。

这是 spore ``core.agent.loop.AgentLoop`` 的精简版本，包含：
- 纯 LLM 对话循环（无工具时直接流式）
- 工具调用循环（通过 SimpleAgentRunner，Phase 1 非流式 + Phase 2 fake streaming）
- SaveMemoryTool：LLM 主动将重要事实写入 MEMORY.md
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from ..bus.events import InboundMessage, OutboundMessage
from ..bus.queue import MessageBus
from ..memory.store import MemoryStore
from ..memory.consolidator import SimpleConsolidator
from .runner import SimpleAgentRunner
from .tools.memory import SaveMemoryTool
from .tools.web import WebFetchTool, WebSearchTool
from .tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .tools.search import GlobTool, GrepTool
from .tools.shell import ExecTool

logger = logging.getLogger(__name__)

# 当 memory/SOUL.md 不存在时使用的默认 Agent 身份。
# 存在 SOUL.md 时该常量不生效，用户可直接编辑文件调整 Agent 人格。
_DEFAULT_SOUL = (
    "你是 CashCode，一个具备跨会话持久记忆能力的 AI 助手。"
    "你与用户的对话会被后台自动整理成长期记忆，并在新会话中自动恢复，"
    "因此你能够跨会话记住用户的身份和偏好。\n\n"
    "## 工具使用规则\n"
    "- 当用户明确要求记住某事（如「帮我记住...」、「记一下...」），"
    "立即调用 save_memory 工具将其保存到长期记忆。\n"
    "- 不要对临时查询、闲聊内容使用此工具。"
)


class SimpleAgentLoop:
    """最简 Agent 循环：维护 chat_id → 对话历史，并调用 DeepSeek API。

    每轮处理流程（含工具）：
      1. 懒加载会话历史。
      2. Phase 1：SimpleAgentRunner 工具循环（非流式），每次工具调用通过 WS 通知用户。
      3. Phase 2：将最终回复以分块 fake streaming 方式发给用户。
      4. 持久化（含工具链或普通轮次）。
      5. 上下文压缩检查（Consolidator）。
    """

    # Fake streaming 每块的字符数
    _STREAM_CHUNK_SIZE: int = 15

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        # 以 chat_id 为键、保存在内存中的对话历史（运行时缓存）。
        # 首次遇到某 chat_id 时从 MemoryStore 懒加载，后续轮次直接读缓存。
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        # Consolidator 的压缩边界指针：记录每个 chat_id 内存历史中已压缩的消息数量。
        # 重启后通过 load_history_smart() 重新推导，运行时由 maybe_consolidate 返回值更新。
        self._last_consolidated: dict[str, int] = {}
        # 持久化层：history.jsonl 按 chat_id 分目录存储在 memory/ 下。
        self._store = MemoryStore(Path("memory"))

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        self._model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY not set — add it to server/.env"
            )

        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        # 上下文压缩器：在 client/model 初始化完成后注入，字符数超阈值时自动摘要旧消息。
        self._consolidator = SimpleConsolidator(self._client, self._model, self._store)
        # 工作目录：文件系统工具和 ExecTool 限制在此目录内。
        workspace = Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()
        # 工具列表：SaveMemoryTool + Web + 文件系统 + 搜索 + Shell。
        self._tools = [
            SaveMemoryTool(self._store),
            WebFetchTool(),
            WebSearchTool(),
            ReadFileTool(workspace),
            WriteFileTool(workspace),
            EditFileTool(workspace),
            ListDirTool(workspace),
            GlobTool(workspace),
            GrepTool(workspace),
            ExecTool(workspace),
        ]
        # ReAct 循环 Runner：工具调用阶段使用非流式 API。
        self._runner = SimpleAgentRunner(
            self._client, self._model,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )
        self._running = False

    async def run(self) -> None:
        """主循环：消费入站消息，并为每轮对话创建任务。"""
        self._running = True
        logger.info("SimpleAgentLoop started (model=%s)", self._model)
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(
                        self.bus.consume_inbound(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                asyncio.create_task(self._handle_turn(msg))
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("SimpleAgentLoop stopped")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # WS 工具调用通知回调（供 SimpleAgentRunner 调用）
    # ------------------------------------------------------------------

    async def _on_tool_call(
        self, chat_id: str, stream_id: int, tool_name: str, kwargs: dict[str, Any]
    ) -> None:
        """LLM 发起工具调用时通知前端。"""
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={
                "_tool_call": True,
                "_tool_name": tool_name,
                "_stream_id": stream_id,
            },
        ))

    async def _on_tool_result(
        self, chat_id: str, stream_id: int, tool_name: str, result: str
    ) -> None:
        """工具执行完成后通知前端。"""
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={
                "_tool_result": True,
                "_tool_name": tool_name,
                "_result": result[:200],  # 截断，避免 WS 消息过大
                "_stream_id": stream_id,
            },
        ))

    # ------------------------------------------------------------------
    # Fake streaming helper
    # ------------------------------------------------------------------

    async def _stream_text(
        self, text: str, chat_id: str, stream_id: int
    ) -> None:
        """将文字切块以 fake streaming 方式发给前端。

        效果与真实 streaming 相同：前端收到一系列 _stream_delta 事件，
        文字逐步出现。无需额外 API 调用。
        """
        size = self._STREAM_CHUNK_SIZE
        for i in range(0, len(text), size):
            chunk = text[i:i + size]
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=chunk,
                metadata={"_stream_delta": True, "_stream_id": stream_id},
            ))
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={"_stream_delta": True, "_stream_end": True, "_stream_id": stream_id},
        ))

    async def _handle_turn(self, msg: InboundMessage) -> None:
        """处理一轮用户消息，返回 LLM 回复（含工具调用时走 Runner）。"""
        chat_id = msg.chat_id
        if chat_id not in self._sessions:
            messages, lc = self._store.load_history_smart(chat_id)
            self._sessions[chat_id] = messages
            self._last_consolidated[chat_id] = lc
        history = self._sessions[chat_id]
        history.append({"role": "user", "content": msg.content})

        t_start = time.monotonic()
        stream_id = id(msg)

        # System prompt：从 SOUL.md 读取 Agent 身份，无文件时回落 _DEFAULT_SOUL 常量。
        # MEMORY.md 有内容时追加"已记住的信息"段落。
        soul = self._store.read_soul() or _DEFAULT_SOUL
        memory = self._store.read_memory()
        if memory:
            system_content = f"{soul}\n\n## 你已经记住的信息\n{memory}"
        else:
            system_content = soul

        messages_to_send = [
            {"role": "system", "content": system_content},
            *history,
        ]

        # ------------------------------------------------------------------
        # Phase 1：Runner 工具循环（非流式）
        # ------------------------------------------------------------------
        try:
            full_reply, updated_messages = await self._runner.run(
                messages_to_send,
                self._tools,
                chat_id=chat_id,
                stream_id=stream_id,
            )
        except Exception as exc:
            logger.exception("Agent turn failed for chat_id=%s", chat_id)
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=str(exc),
                metadata={"_user_error": True},
            ))
            if history and history[-1]["role"] == "user":
                history.pop()
            return

        # ------------------------------------------------------------------
        # Phase 2：Fake streaming（把 final_reply 切块发给前端）
        # ------------------------------------------------------------------
        await self._stream_text(full_reply, chat_id, stream_id)

        # ------------------------------------------------------------------
        # 提取工具链（若有），同步到 in-memory history
        # ------------------------------------------------------------------
        new_messages = updated_messages[len(messages_to_send):]  # tool chain (excl. system+history)
        tool_calls_msg: dict[str, Any] | None = None
        tool_results: list[dict[str, Any]] = []
        for m in new_messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tool_calls_msg = m
            elif m.get("role") == "tool":
                tool_results.append(m)

        # 将工具链消息追加到 in-memory history，再加最终回复
        for m in new_messages:
            history.append(m)
        history.append({"role": "assistant", "content": full_reply})

        # ------------------------------------------------------------------
        # 持久化（原子写入）
        # ------------------------------------------------------------------
        if tool_calls_msg and tool_results:
            self._store.append_tool_turn(
                chat_id, msg.content, tool_calls_msg, tool_results, full_reply
            )
        else:
            self._store.append_turn(chat_id, msg.content, full_reply)

        # ------------------------------------------------------------------
        # 上下文压缩
        # ------------------------------------------------------------------
        try:
            lc = await self._consolidator.maybe_consolidate(
                chat_id, history,
                last_consolidated=self._last_consolidated.get(chat_id, 0),
            )
            self._last_consolidated[chat_id] = lc
        except Exception:
            logger.warning("Consolidator raised unexpectedly for chat_id=%s", chat_id, exc_info=True)

        duration = time.monotonic() - t_start
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content=full_reply,
            metadata={"_turn_done": True, "_duration_sec": duration},
        ))
        logger.info(
            "Turn done: chat_id=%s duration=%.2fs chars=%d tool_calls=%d",
            chat_id, duration, len(full_reply), len(tool_results),
        )
