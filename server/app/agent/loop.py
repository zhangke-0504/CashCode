"""支持 MCP 与本地 Skill 懒加载的 CashCode Agent 循环。"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from ..bus.events import InboundMessage, OutboundMessage
from ..bus.queue import MessageBus
from ..memory.consolidator import SimpleConsolidator
from ..memory.store import MemoryStore
from ..paths import DataPaths
from ..skills.activation import ActivatedSkillSet, TurnSkillContext, use_skill_context
from ..skills.catalog import SkillCatalog
from ..skills.tools import (
    SkillLoadTool,
    SkillReadResourceTool,
    SkillSearchTool,
    parse_explicit_skill,
    render_activated_skill_summary,
)
from .runner import SimpleAgentRunner
from .tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from .tools.mcp import MCPConnectionHandle, MCPToolWrapper, lazy_connect
from .tools.mcp_cache import write_cache
from .tools.memory import SaveMemoryTool
from .tools.registry import ToolRegistry
from .tools.result import ToolExecutionResult
from .tools.search import GlobTool, GrepTool
from .tools.shell import ExecTool
from .tools.tool_search import (
    ActivatedToolSet,
    DeferredAwareRegistry,
    MCPPrepareTool,
    ToolSearchTool,
    use_activated_set,
)
from .tools.web import WebFetchTool, WebSearchTool

logger = logging.getLogger(__name__)

_DEFAULT_SOUL = """You are CashCode, a capable local-first AI assistant with persistent memory.

## Tool rules
- When the user explicitly asks you to remember durable information, call save_memory.
- Do not save temporary queries or casual conversation as long-term memory.
"""


class SimpleAgentLoop:
    _STREAM_CHUNK_SIZE = 15

    def __init__(
        self,
        bus: MessageBus,
        *,
        data_paths: DataPaths | None = None,
        skill_catalog: SkillCatalog | None = None,
    ) -> None:
        self.bus = bus
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._last_consolidated: dict[str, int] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._turn_lock_users: dict[str, int] = {}
        self._turn_tasks: set[asyncio.Task] = set()

        server_root = Path(__file__).resolve().parents[2]
        memory_root = Path(os.environ.get("MEMORY_DIR", str(server_root / "memory"))).resolve()
        workspace = Path(os.environ.get("WORKSPACE_DIR", str(server_root))).resolve()
        self._store = MemoryStore(memory_root)
        self._data_paths = data_paths or DataPaths.from_environment()
        self._data_paths.ensure()

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        self._model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set; add it to server/.env")
        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        self._consolidator = SimpleConsolidator(self._client, self._model, self._store)

        self._registry = ToolRegistry()
        for tool in (
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
        ):
            self._registry.register(tool)

        self._deferred_registry = DeferredAwareRegistry(self._registry)
        self._mcp_config: dict[str, dict[str, Any]] = {}
        self._mcp_handles: dict[str, MCPConnectionHandle] = {}

        builtin_root = Path(__file__).resolve().parents[1] / "skills" / "builtin"
        self._skill_catalog = skill_catalog or SkillCatalog(
            builtin_root,
            self._data_paths.skills_user,
            self._data_paths.skills_agent,
        )
        self._skill_catalog.set_runtime_sources(
            tool_names=lambda: self._registry.tool_names,
            mcp_servers=lambda: self._mcp_config.keys(),
        )

        self._deferred_registry.register(ToolSearchTool(self._registry, self._mcp_config))
        self._deferred_registry.register(MCPPrepareTool(self._prepare_mcp_server, self._registry))
        self._skill_load_tool = SkillLoadTool(
            self._skill_catalog, self._registry, self._prepare_mcp_server
        )
        self._deferred_registry.register(SkillSearchTool(self._skill_catalog))
        self._deferred_registry.register(self._skill_load_tool)
        self._deferred_registry.register(SkillReadResourceTool(self._skill_catalog))

        self._runner = SimpleAgentRunner(
            self._client,
            self._model,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )
        self._skill_evolution: Any | None = None
        self._running = False

    @property
    def skill_catalog(self) -> SkillCatalog:
        return self._skill_catalog

    def set_skill_evolution(self, service: Any) -> None:
        self._skill_evolution = service

    async def _setup_mcp(self) -> None:
        project_root = Path(__file__).resolve().parents[3]
        config_path = project_root / "mcp_servers" / "mcp_config.json"
        if not config_path.exists():
            logger.info("MCP config not found at %s", config_path)
            self._skill_catalog.refresh()
            return
        try:
            servers = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse MCP config: %s", exc)
            return
        if not isinstance(servers, dict):
            return
        for config in servers.values():
            if not isinstance(config, dict):
                continue
            config["args"] = [
                str((project_root / value).resolve()) if not Path(value).is_absolute() else value
                for value in config.get("args", [])
            ]
        self._mcp_config.update(servers)
        self._skill_catalog.refresh()

    async def _prepare_mcp_server(self, server_name: str) -> bool:
        config = self._mcp_config.get(server_name)
        if config is None:
            return False
        if not await lazy_connect(server_name, config, self._mcp_handles):
            return False
        session = self._mcp_handles[server_name].session
        if session is None:
            return False
        try:
            result = await session.list_tools()
        except Exception:
            logger.warning("Failed to list tools for MCP '%s'", server_name, exc_info=True)
            return False
        tools_data: list[dict[str, Any]] = []
        for definition in result.tools:
            wrapper = MCPToolWrapper(session, server_name, definition)
            self._registry.register(wrapper)
            tools_data.append({
                "name": definition.name,
                "description": definition.description or "",
                "inputSchema": definition.inputSchema or {},
            })
        write_cache(server_name, config, tools_data)
        return True

    async def run(self) -> None:
        self._running = True
        await self._setup_mcp()
        logger.info("SimpleAgentLoop started (model=%s, MCP=lazy, Skills=lazy)", self._model)
        try:
            while self._running:
                try:
                    message = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                task = asyncio.create_task(self._handle_turn(message))
                self._turn_tasks.add(task)
                task.add_done_callback(self._turn_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
        for handle in self._mcp_handles.values():
            asyncio.create_task(handle.aclose())

    async def _on_tool_call(
        self, chat_id: str, stream_id: int, tool_name: str, params: dict[str, Any]
    ) -> None:
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={"_tool_call": True, "_tool_name": tool_name, "_stream_id": stream_id},
        ))

    async def _on_tool_result(
        self, chat_id: str, stream_id: int, tool_name: str, result: str
    ) -> None:
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={
                "_tool_result": True,
                "_tool_name": tool_name,
                "_result": result[:200],
                "_stream_id": stream_id,
            },
        ))

    async def _stream_text(self, text: str, chat_id: str, stream_id: int) -> None:
        for offset in range(0, len(text), self._STREAM_CHUNK_SIZE):
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=text[offset:offset + self._STREAM_CHUNK_SIZE],
                metadata={"_stream_delta": True, "_stream_id": stream_id},
            ))
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={"_stream_delta": True, "_stream_end": True, "_stream_id": stream_id},
        ))

    async def _handle_turn(self, message: InboundMessage) -> None:
        chat_id = message.chat_id
        lock = self._turn_locks.setdefault(chat_id, asyncio.Lock())
        self._turn_lock_users[chat_id] = self._turn_lock_users.get(chat_id, 0) + 1
        try:
            async with lock:
                await self._handle_turn_locked(message)
        finally:
            remaining = self._turn_lock_users.get(chat_id, 1) - 1
            if remaining <= 0:
                self._turn_lock_users.pop(chat_id, None)
                if self._turn_locks.get(chat_id) is lock:
                    self._turn_locks.pop(chat_id, None)
            else:
                self._turn_lock_users[chat_id] = remaining

    async def _handle_turn_locked(self, message: InboundMessage) -> None:
        chat_id = message.chat_id
        stream_id = id(message)
        started = time.monotonic()
        if chat_id not in self._sessions:
            history, last_consolidated = self._store.load_history_smart(chat_id)
            self._sessions[chat_id] = history
            self._last_consolidated[chat_id] = last_consolidated
        if chat_id not in self._session_metadata:
            self._session_metadata[chat_id] = self._store.read_session_metadata(chat_id)

        history = self._sessions[chat_id]
        metadata = self._session_metadata[chat_id]
        metadata_before_turn = copy.deepcopy(metadata)
        if not metadata.get("title"):
            metadata["title"] = message.content.strip()[:40] or "New conversation"
        history.append({"role": "user", "content": message.content})

        activated_tools = ActivatedToolSet.from_session(metadata)
        activated_skills = ActivatedSkillSet.from_session(metadata)
        skill_context = TurnSkillContext(activated_skills)
        explicit_skill, task_content = parse_explicit_skill(message.content)

        soul = self._store.read_soul() or _DEFAULT_SOUL
        memory = self._store.read_memory()
        system_content = soul
        if memory:
            system_content += f"\n\n## Remembered information\n{memory}"
        system_content += (
            "\n\n## Skill usage\nSearch installed workflows with skill_search, then call "
            "skill_load with an exact result. Skill bodies are current-turn-only and must "
            "be reloaded in a later turn when full guidance is needed."
        )
        recent = render_activated_skill_summary(self._skill_catalog, activated_skills)
        if recent:
            system_content += f"\n\n{recent}"
        model_history = [
            *history[:-1],
            {"role": "user", "content": task_content or message.content},
        ]
        messages = [{"role": "system", "content": system_content}, *model_history]

        try:
            with use_activated_set(activated_tools), use_skill_context(skill_context):
                explicit_receipt: dict[str, Any] | None = None
                if explicit_skill:
                    selected = ToolExecutionResult.coerce(
                        await self._skill_load_tool.execute(name=explicit_skill)
                    )
                    error = None
                    if selected.model_content.lstrip().startswith("{"):
                        try:
                            error = json.loads(selected.model_content).get("error")
                        except json.JSONDecodeError:
                            pass
                    if error:
                        raise ValueError(f"Unable to load @{explicit_skill}: {selected.model_content}")
                    messages.insert(1, {
                        "role": "system",
                        "content": "The user explicitly selected this Skill:\n\n" + selected.model_content,
                    })
                    explicit_receipt = {"role": "assistant", "content": selected.persisted}
                trace = await self._runner.run(
                    messages,
                    self._deferred_registry,
                    chat_id=chat_id,
                    stream_id=stream_id,
                )
                if explicit_receipt:
                    trace.durable_messages.insert(0, explicit_receipt)
        except Exception as exc:
            logger.exception("Agent turn failed for chat_id=%s", chat_id)
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=str(exc),
                metadata={"_user_error": True},
            ))
            if history and history[-1].get("role") == "user":
                history.pop()
            self._session_metadata[chat_id] = metadata_before_turn
            return

        await self._stream_text(trace.final_text, chat_id, stream_id)
        history.extend(trace.durable_messages)
        history.append({"role": "assistant", "content": trace.final_text})
        if trace.durable_messages:
            self._store.append_traced_turn(
                chat_id, message.content, trace.durable_messages, trace.final_text
            )
        else:
            self._store.append_turn(chat_id, message.content, trace.final_text)
        self._store.write_session_metadata(chat_id, metadata)
        if self._skill_evolution is not None:
            self._skill_evolution.schedule_turn(
                chat_id=chat_id,
                user_content=message.content,
                final_content=trace.final_text,
                tools_used=trace.tools_used,
                durable_messages=trace.durable_messages,
                persisted=trace.success,
            )

        try:
            value = await self._consolidator.maybe_consolidate(
                chat_id,
                history,
                last_consolidated=self._last_consolidated.get(chat_id, 0),
            )
            self._last_consolidated[chat_id] = value
        except Exception:
            logger.warning("Consolidator failed for chat_id=%s", chat_id, exc_info=True)

        duration = time.monotonic() - started
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content=trace.final_text,
            metadata={"_turn_done": True, "_duration_sec": duration},
        ))
        logger.info(
            "Turn done: chat_id=%s duration=%.2fs chars=%d tool_calls=%d",
            chat_id,
            duration,
            len(trace.final_text),
            len(trace.tools_used),
        )
