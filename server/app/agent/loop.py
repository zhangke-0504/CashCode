# -*- coding: utf-8 -*-
"""SimpleAgentLoop：读取 InboundMessage，调用 DeepSeek（含工具），再发布 OutboundMessage。

V2 变更：
- MCP server 不再在启动时连接，只读取配置 + disk cache
- 每轮绑定 ActivatedToolSet（懒加载自 session metadata）
- 工具传 DeferredAwareRegistry，MCP 工具默认 deferred
- 内置 ToolSearchTool + MCPPrepareTool（永远可见）
- 轮次结束时写回 session metadata 到磁盘
"""
from __future__ import annotations

import asyncio
import json
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
from .tools.registry import ToolRegistry
from .tools.mcp import lazy_connect, load_mcp_tools, MCPConnectionHandle, MCPToolWrapper
from .tools.mcp_cache import read_cache, write_cache
from .tools.tool_search import (
    ActivatedToolSet,
    DeferredAwareRegistry,
    ToolSearchTool,
    MCPPrepareTool,
    use_activated_set,
)
from .tools.memory import SaveMemoryTool
from .tools.web import WebFetchTool, WebSearchTool
from .tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .tools.search import GlobTool, GrepTool
from .tools.shell import ExecTool

logger = logging.getLogger(__name__)

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
    """最简 Agent 循环（V2）：MCP 工具延迟激活，按需连接。

    每轮处理流程：
      1. 懒加载会话历史 + session metadata。
      2. 绑定 ActivatedToolSet 到当前 async task。
      3. Phase 1：SimpleAgentRunner 工具循环（传 DeferredAwareRegistry）。
      4. Phase 2：Fake streaming 发给前端。
      5. 持久化对话历史 + session metadata。
      6. 上下文压缩检查。
    """

    _STREAM_CHUNK_SIZE: int = 15

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._last_consolidated: dict[str, int] = {}
        self._session_metadata: dict[str, dict] = {}   # V2: per-chat_id 元数据缓存
        self._store = MemoryStore(Path("memory"))

        api_key  = os.environ.get("DEEPSEEK_API_KEY", "")
        api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        self._model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set — add it to server/.env")

        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        self._consolidator = SimpleConsolidator(self._client, self._model, self._store)

        workspace = Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()

        # FullRegistry：内置工具（MCP 工具在 mcp_prepare 后动态注册进来）
        self._registry = ToolRegistry()
        for tool in [
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
        ]:
            self._registry.register(tool)

        # V2: DeferredAwareRegistry 包装 FullRegistry
        self._deferred_registry = DeferredAwareRegistry(self._registry)

        # V2: MCP 配置（只存配置，不建连接）
        self._mcp_config: dict[str, dict] = {}
        self._mcp_handles: dict[str, MCPConnectionHandle] = {}

        # V2: ToolSearchTool 和 MCPPrepareTool 注册到 DeferredAwareRegistry（永远可见）
        self._deferred_registry.register(
            ToolSearchTool(self._registry, self._mcp_config)
        )
        self._deferred_registry.register(
            MCPPrepareTool(self._prepare_mcp_server, self._registry)
        )

        self._runner = SimpleAgentRunner(
            self._client, self._model,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )
        self._running = False

    # ------------------------------------------------------------------
    # MCP 初始化（V2：只读配置，不建连接）
    # ------------------------------------------------------------------

    async def _setup_mcp(self) -> None:
        """读取 mcp_config.json，存入 self._mcp_config，不建立任何连接。

        disk cache 里的工具 schema 会预先加载，使 tool_search 在首次连接前也能搜索。
        """
        _project_root = Path(__file__).resolve().parent.parent.parent.parent
        config_path = _project_root / "mcp_servers" / "mcp_config.json"
        if not config_path.exists():
            logger.info("MCP config not found at %s, no MCP servers configured", config_path)
            return

        try:
            servers: dict = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse MCP config: %s", exc)
            return

        if not isinstance(servers, dict) or not servers:
            return

        # 将相对 args 路径转为绝对路径
        for cfg in servers.values():
            if not isinstance(cfg, dict):
                continue
            cfg["args"] = [
                str((_project_root / Path(a)).resolve()) if not Path(a).is_absolute() else a
                for a in cfg.get("args", [])
            ]

        self._mcp_config.update(servers)
        logger.info(
            "MCP config loaded (lazy mode): %d server(s) configured, no connections yet",
            len(servers),
        )

    # ------------------------------------------------------------------
    # prepare callback（注入给 MCPPrepareTool）
    # ------------------------------------------------------------------

    async def _prepare_mcp_server(self, server_name: str) -> bool:
        """MCPPrepareTool 的回调：按需连接 server + list_tools + write_cache + register."""
        cfg = self._mcp_config.get(server_name)
        if cfg is None:
            logger.warning("_prepare_mcp_server: '%s' not in config", server_name)
            return False

        ok = await lazy_connect(server_name, cfg, self._mcp_handles)
        if not ok:
            return False

        session = self._mcp_handles[server_name].session
        if session is None:
            return False

        try:
            result = await session.list_tools()
        except Exception as exc:
            logger.warning("_prepare_mcp_server: list_tools failed for '%s': %s", server_name, exc)
            return False

        tools_data: list[dict] = []
        for tool_def in result.tools:
            wrapper = MCPToolWrapper(session, server_name, tool_def)
            self._registry.register(wrapper)
            tools_data.append({
                "name": tool_def.name,
                "description": tool_def.description or "",
                "inputSchema": tool_def.inputSchema or {},
            })
        write_cache(server_name, cfg, tools_data)
        logger.info("_prepare_mcp_server: '%s' ready, %d tool(s)", server_name, len(tools_data))
        return True

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        logger.info("SimpleAgentLoop starting (model=%s, MCP=lazy)", self._model)
        await self._setup_mcp()
        logger.info("SimpleAgentLoop started")
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
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
        for name, handle in self._mcp_handles.items():
            asyncio.create_task(handle.aclose())
            logger.info("MCP '%s': close requested", name)

    # ------------------------------------------------------------------
    # WS 通知回调
    # ------------------------------------------------------------------

    async def _on_tool_call(self, chat_id: str, stream_id: int, tool_name: str, kwargs: dict) -> None:
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket", chat_id=chat_id, content="",
            metadata={"_tool_call": True, "_tool_name": tool_name, "_stream_id": stream_id},
        ))

    async def _on_tool_result(self, chat_id: str, stream_id: int, tool_name: str, result: str) -> None:
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket", chat_id=chat_id, content="",
            metadata={"_tool_result": True, "_tool_name": tool_name,
                      "_result": result[:200], "_stream_id": stream_id},
        ))

    # ------------------------------------------------------------------
    # Fake streaming
    # ------------------------------------------------------------------

    async def _stream_text(self, text: str, chat_id: str, stream_id: int) -> None:
        size = self._STREAM_CHUNK_SIZE
        for i in range(0, len(text), size):
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket", chat_id=chat_id, content=text[i:i+size],
                metadata={"_stream_delta": True, "_stream_id": stream_id},
            ))
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket", chat_id=chat_id, content="",
            metadata={"_stream_delta": True, "_stream_end": True, "_stream_id": stream_id},
        ))

    # ------------------------------------------------------------------
    # 单轮处理（V2 核心：绑定 ActivatedToolSet）
    # ------------------------------------------------------------------

    async def _handle_turn(self, msg: InboundMessage) -> None:
        chat_id   = msg.chat_id
        stream_id = id(msg)
        t_start   = time.monotonic()

        # 懒加载消息历史
        if chat_id not in self._sessions:
            messages, lc = self._store.load_history_smart(chat_id)
            self._sessions[chat_id] = messages
            self._last_consolidated[chat_id] = lc

        # 懒加载 session metadata（V2）
        if chat_id not in self._session_metadata:
            self._session_metadata[chat_id] = self._store.read_session_metadata(chat_id)

        history  = self._sessions[chat_id]
        metadata = self._session_metadata[chat_id]

        # 第一轮时若无 title，自动截取用户消息前 40 字符作为默认标题
        if not metadata.get("title"):
            metadata["title"] = msg.content.strip()[:40] or "新对话"

        history.append({"role": "user", "content": msg.content})

        soul   = self._store.read_soul() or _DEFAULT_SOUL
        memory = self._store.read_memory()
        system_content = f"{soul}\n\n## 你已经记住的信息\n{memory}" if memory else soul
        messages_to_send = [{"role": "system", "content": system_content}, *history]

        # V2：构建本轮激活集，绑定到当前 task
        activated_set = ActivatedToolSet.from_session(metadata)

        try:
            with use_activated_set(activated_set):
                full_reply, updated_messages = await self._runner.run(
                    messages_to_send,
                    self._deferred_registry,
                    chat_id=chat_id,
                    stream_id=stream_id,
                )
        except Exception as exc:
            logger.exception("Agent turn failed for chat_id=%s", chat_id)
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket", chat_id=chat_id,
                content=str(exc), metadata={"_user_error": True},
            ))
            if history and history[-1]["role"] == "user":
                history.pop()
            return

        await self._stream_text(full_reply, chat_id, stream_id)

        # 提取工具链，同步到 in-memory history
        new_messages = updated_messages[len(messages_to_send):]
        tool_calls_msg: dict[str, Any] | None = None
        tool_results: list[dict[str, Any]] = []
        for m in new_messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tool_calls_msg = m
            elif m.get("role") == "tool":
                tool_results.append(m)
        for m in new_messages:
            history.append(m)
        history.append({"role": "assistant", "content": full_reply})

        # 持久化对话历史
        if tool_calls_msg and tool_results:
            self._store.append_tool_turn(chat_id, msg.content, tool_calls_msg, tool_results, full_reply)
        else:
            self._store.append_turn(chat_id, msg.content, full_reply)

        # V2：写回 session metadata（含 activated_tools）
        self._store.write_session_metadata(chat_id, metadata)

        # 上下文压缩
        try:
            lc = await self._consolidator.maybe_consolidate(
                chat_id, history,
                last_consolidated=self._last_consolidated.get(chat_id, 0),
            )
            self._last_consolidated[chat_id] = lc
        except Exception:
            logger.warning("Consolidator raised for chat_id=%s", chat_id, exc_info=True)

        duration = time.monotonic() - t_start
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket", chat_id=chat_id, content=full_reply,
            metadata={"_turn_done": True, "_duration_sec": duration},
        ))
        logger.info(
            "Turn done: chat_id=%s duration=%.2fs chars=%d tool_calls=%d",
            chat_id, duration, len(full_reply), len(tool_results),
        )
