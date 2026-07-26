"""支持 MCP 与本地 Skill 懒加载的 CashCode Agent 循环。"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..bus.events import InboundMessage, OutboundMessage
from ..llm.models import LLMNotConfiguredError
from ..logging_config import log_context, log_event, safe_exception_info
from ..llm.runtime import LLMRuntime
from ..bus.queue import MessageBus
from ..memory.consolidator import ConsolidationPlan, SimpleConsolidator
from ..memory.store import MemoryStore
from ..paths import DataPaths
from ..skills.activation import ActivatedSkillSet, TurnSkillContext, use_skill_context
from ..skills.authoring import AgentSkillManageTool
from ..skills.catalog import SkillCatalog
from ..skills.store import SkillStore
from ..skills.tools import (
    SkillLoadTool,
    SkillReadResourceTool,
    SkillSearchTool,
    parse_explicit_skill,
    render_activated_skill_summary,
)
from .runner import SimpleAgentRunner
from .tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from .tools.mcp import MCPConnectionHandle, MCPToolWrapper, establish_mcp_sessions
from .tools.mcp_cache import delete_cache, read_cache, write_cache
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
    use_temporary_tools,
)
from .tools.web import WebFetchTool, WebSearchTool

logger = logging.getLogger(__name__)

_DEFAULT_SOUL = """You are CashCode, a capable local-first AI assistant with persistent memory.

## Tool rules
- When the user explicitly asks you to remember durable information, call save_memory.
- Do not save temporary queries or casual conversation as long-term memory.
"""


def first_session_title(content: str) -> str:
    """Return the deterministic title for a session's first accepted task."""

    return " ".join(content.split())[:40]


class SimpleAgentLoop:
    _STREAM_CHUNK_SIZE = 15

    def __init__(
        self,
        bus: MessageBus,
        *,
        data_paths: DataPaths | None = None,
        skill_catalog: SkillCatalog | None = None,
        skill_store: SkillStore | None = None,
        llm_runtime: LLMRuntime | None = None,
    ) -> None:
        self.bus = bus
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._last_consolidated: dict[str, int] = {}
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._turn_locks: dict[str, asyncio.Lock] = {}
        self._turn_lock_users: dict[str, int] = {}
        self._turn_tasks: set[asyncio.Task[Any]] = set()
        self._auxiliary_tasks: set[asyncio.Task[Any]] = set()
        self._consolidation_tasks: dict[str, asyncio.Task[Any]] = {}

        server_root = Path(__file__).resolve().parents[2]
        memory_root = Path(os.environ.get("MEMORY_DIR", str(server_root / "memory"))).resolve()
        workspace = Path(os.environ.get("WORKSPACE_DIR", str(server_root))).resolve()
        self._store = MemoryStore(memory_root)
        self._data_paths = data_paths or DataPaths.from_environment()
        self._data_paths.ensure()

        self._llm_runtime = llm_runtime or LLMRuntime()
        self._consolidator = SimpleConsolidator(self._llm_runtime, self._store)

        self._registry = ToolRegistry()
        for tool in (
            SaveMemoryTool(self._store),
            WebFetchTool(),
            WebSearchTool(),
            ReadFileTool(workspace),
            WriteFileTool(
                workspace,
                protected_roots=(
                    self._data_paths.skills_user,
                    self._data_paths.skills_agent,
                ),
            ),
            EditFileTool(
                workspace,
                protected_roots=(
                    self._data_paths.skills_user,
                    self._data_paths.skills_agent,
                ),
            ),
            ListDirTool(workspace),
            GlobTool(workspace),
            GrepTool(workspace),
            ExecTool(workspace),
        ):
            self._registry.register(tool)

        self._deferred_registry = DeferredAwareRegistry(self._registry)
        self._mcp_config: dict[str, dict[str, Any]] = {}
        self._mcp_handles: dict[str, MCPConnectionHandle] = {}
        self._mcp_tool_names: dict[str, set[str]] = {}
        self._mcp_status: dict[str, dict[str, Any]] = {}
        self._mcp_locks: dict[str, asyncio.Lock] = {}

        builtin_root = Path(__file__).resolve().parents[1] / "skills" / "builtin"
        self._skill_catalog = skill_catalog or (
            skill_store.catalog
            if skill_store is not None
            else SkillCatalog(
                builtin_root,
                self._data_paths.skills_user,
                self._data_paths.skills_agent,
            )
        )
        if skill_store is not None and skill_store.catalog is not self._skill_catalog:
            raise ValueError("skill_store and skill_catalog must share the same catalog")
        self._skill_store = skill_store or SkillStore(
            self._skill_catalog, self._data_paths.skill_snapshots
        )
        self._registry.register(AgentSkillManageTool(self._skill_store))
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
            self._llm_runtime,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )
        self._skill_evolution: Any | None = None
        self._running = False

    @property
    def skill_catalog(self) -> SkillCatalog:
        return self._skill_catalog

    @property
    def skill_store(self) -> SkillStore:
        return self._skill_store

    @property
    def llm_runtime(self) -> LLMRuntime:
        return self._llm_runtime

    def rename_session(self, chat_id: str, title: str) -> str:
        """Persist a user title and synchronize any metadata loaded by the Agent."""

        normalized = title.strip()
        if not normalized:
            raise ValueError("title must not be empty")
        if not (self._store.base_dir / chat_id).is_dir():
            raise FileNotFoundError(chat_id)

        metadata = self._session_metadata.get(chat_id)
        if metadata is None:
            metadata = self._store.read_session_metadata(chat_id)
            self._session_metadata[chat_id] = metadata
        metadata["title"] = normalized
        persisted = self._store.read_session_metadata(chat_id)
        persisted["title"] = normalized
        self._store.write_session_metadata(chat_id, persisted)
        return normalized

    def set_skill_evolution(self, service: Any) -> None:
        self._skill_evolution = service

    async def _setup_mcp(self) -> None:
        if self._mcp_config:
            self._skill_catalog.refresh()
            return
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
        for name in servers:
            self._mcp_status.setdefault(name, self._disconnected_mcp_status())
        self._skill_catalog.refresh()

    async def _prepare_mcp_server(self, server_name: str) -> bool:
        status = await self.connect_mcp_server(server_name)
        return status["status"] == "connected"

    @staticmethod
    def _disconnected_mcp_status(error: str | None = None) -> dict[str, Any]:
        """构造未连接状态，并可附带清理阶段产生的有界错误。"""

        return {
            "status": "disconnected",
            "status_error": error,
            "tool_count": 0,
        }

    def load_mcp_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """安装规范化启动配置，但不主动建立任何连接。"""

        self._mcp_config.clear()
        self._mcp_config.update(copy.deepcopy(configs))
        self._mcp_status = {
            name: self._disconnected_mcp_status() for name in self._mcp_config
        }
        self._skill_catalog.refresh()

    def get_mcp_status(self, server_name: str) -> dict[str, Any]:
        """结合状态记录和实际句柄，返回指定服务的权威生命周期状态。"""

        status = dict(
            self._mcp_status.get(server_name, self._disconnected_mcp_status())
        )
        handle = self._mcp_handles.get(server_name)
        if handle is None or handle.session is None:
            if status.get("status") == "connected":
                status = self._disconnected_mcp_status("connection is no longer available")
        else:
            status["status"] = "connected"
            status["status_error"] = None
            status["tool_count"] = len(self._mcp_tool_names.get(server_name, ()))
        return status

    async def connect_mcp_server(self, server_name: str) -> dict[str, Any]:
        """按服务名串行执行幂等连接，避免重复句柄和工具包装器。"""

        started = time.monotonic()
        log_event(logger, logging.DEBUG, "mcp.management.connect_started", server=server_name)
        lock = self._mcp_locks.setdefault(server_name, asyncio.Lock())
        try:
            async with lock:
                status = await self._connect_mcp_server_unlocked(server_name)
        except Exception as exc:
            logger.error(
                "event=mcp.management.connect_failed server=%s duration_ms=%.2f error_type=%s",
                server_name,
                (time.monotonic() - started) * 1000,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            raise
        log_event(
            logger,
            logging.INFO,
            "mcp.management.connect_completed",
            server=server_name,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            status=status.get("status"),
            tool_count=status.get("tool_count"),
        )
        return status

    async def _connect_mcp_server_unlocked(self, server_name: str) -> dict[str, Any]:
        """在调用方持有服务锁时完成连接、握手、工具发现和状态发布。"""

        config = self._mcp_config.get(server_name)
        if config is None:
            status = {
                "status": "error",
                "status_error": "MCP server is not configured",
                "tool_count": 0,
            }
            self._mcp_status[server_name] = status
            return dict(status)

        existing = self._mcp_handles.get(server_name)
        if existing is not None and existing.session is not None:
            status = {
                "status": "connected",
                "status_error": None,
                "tool_count": len(self._mcp_tool_names.get(server_name, ())),
            }
            self._mcp_status[server_name] = status
            return dict(status)

        await self._disconnect_mcp_server_unlocked(server_name, purge_activations=False)
        self._mcp_status[server_name] = {
            "status": "connecting",
            "status_error": None,
            "tool_count": 0,
        }
        errors: dict[str, str] = {}
        handles = await establish_mcp_sessions(
            {server_name: config}, errors_out=errors
        )
        handle = handles.get(server_name)
        if handle is None or handle.session is None:
            status = {
                "status": "error",
                "status_error": errors.get(server_name, "MCP connection failed")[:500],
                "tool_count": 0,
            }
            self._mcp_status[server_name] = status
            return dict(status)

        session = handle.session
        try:
            result = await session.list_tools()
        except Exception as exc:
            await handle.aclose()
            status = {
                "status": "error",
                "status_error": f"{type(exc).__name__}: tool discovery failed"[:500],
                "tool_count": 0,
            }
            self._mcp_status[server_name] = status
            logger.warning("Failed to list tools for MCP '%s': %s", server_name, type(exc).__name__)
            return dict(status)

        tools_data: list[dict[str, Any]] = []
        wrappers: list[MCPToolWrapper] = []
        for definition in result.tools:
            wrapper = MCPToolWrapper(session, server_name, definition)
            wrappers.append(wrapper)
            tools_data.append({
                "name": definition.name,
                "description": definition.description or "",
                "inputSchema": definition.inputSchema or {},
            })
        # 工具发现全部成功后再一次性发布句柄和包装器，避免暴露半成品连接。
        for wrapper in wrappers:
            self._registry.register(wrapper)
        self._mcp_handles[server_name] = handle
        self._mcp_tool_names[server_name] = {wrapper.name for wrapper in wrappers}
        write_cache(server_name, config, tools_data)
        status = {
            "status": "connected",
            "status_error": None,
            "tool_count": len(wrappers),
        }
        self._mcp_status[server_name] = status
        return dict(status)

    async def disconnect_mcp_server(
        self, server_name: str, *, purge_activations: bool = True
    ) -> dict[str, Any]:
        """按服务名串行断开连接，并按需清除持久化激活引用。"""

        started = time.monotonic()
        lock = self._mcp_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            status = await self._disconnect_mcp_server_unlocked(
                server_name, purge_activations=purge_activations
            )
        log_event(
            logger,
            logging.INFO,
            "mcp.management.disconnect_completed",
            server=server_name,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            status=status.get("status"),
            purged_activations=purge_activations,
        )
        return status

    async def _disconnect_mcp_server_unlocked(
        self, server_name: str, *, purge_activations: bool
    ) -> dict[str, Any]:
        """在调用方持有服务锁时关闭句柄并注销该服务拥有的工具。"""

        handle = self._mcp_handles.pop(server_name, None)
        owned = self._mcp_tool_names.pop(server_name, set())
        close_error: str | None = None
        try:
            if handle is not None:
                await handle.aclose()
        except Exception as exc:
            close_error = f"{type(exc).__name__}: connection cleanup failed"[:500]
            logger.warning("MCP '%s' cleanup failed: %s", server_name, type(exc).__name__)
        finally:
            # 即使传输关闭报错，也必须移除包装器和旧激活权限。
            for tool_name in owned:
                self._registry.unregister(tool_name)
            if purge_activations and owned:
                self._purge_activated_tools(owned)
        status = self._disconnected_mcp_status(close_error)
        self._mcp_status[server_name] = status
        return dict(status)

    async def replace_mcp_config(
        self, server_name: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """断开旧连接、替换运行时配置并使工具缓存失效。"""

        lock = self._mcp_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            await self._disconnect_mcp_server_unlocked(
                server_name, purge_activations=True
            )
            self._mcp_config[server_name] = copy.deepcopy(config)
            delete_cache(server_name)
            self._skill_catalog.refresh()
            status = self._disconnected_mcp_status()
            self._mcp_status[server_name] = status
            return dict(status)

    async def remove_mcp_config(self, server_name: str) -> None:
        """清理指定服务的连接、工具、缓存和 Skill 依赖状态。"""

        lock = self._mcp_locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            await self._disconnect_mcp_server_unlocked(
                server_name, purge_activations=True
            )
            self._mcp_config.pop(server_name, None)
            self._mcp_status.pop(server_name, None)
            delete_cache(server_name)
            self._skill_catalog.refresh()

    def _purge_activated_tools(self, tool_names: set[str]) -> None:
        """从已加载及磁盘会话元数据中清除精确工具名称。"""

        # 先更新当前进程已加载的会话元数据。
        for metadata in self._session_metadata.values():
            activated = metadata.get("activated_tools")
            if isinstance(activated, dict):
                for tool_name in tool_names:
                    activated.pop(tool_name, None)
        # 再扫描持久化会话，防止同名服务重建后继承旧激活权限。
        for chat_id in self._store.list_chat_ids():
            metadata = self._store.read_session_metadata(chat_id)
            activated = metadata.get("activated_tools")
            if not isinstance(activated, dict):
                continue
            changed = False
            for tool_name in tool_names:
                if activated.pop(tool_name, None) is not None:
                    changed = True
            if changed:
                self._store.write_session_metadata(chat_id, metadata)

    def get_mcp_tools(self, server_name: str) -> dict[str, Any]:
        """优先返回实时工具，否则返回传输指纹仍有效的只读缓存。"""

        if server_name not in self._mcp_config:
            return {"tools": [], "source": "none", **self.get_mcp_status(server_name)}
        live: list[dict[str, Any]] = []
        for tool_name in sorted(self._mcp_tool_names.get(server_name, ())):
            wrapper = self._registry.get(tool_name)
            if wrapper is None:
                continue
            live.append({
                "name": tool_name,
                "original_name": getattr(wrapper, "_original_name", tool_name),
                "description": wrapper.description,
                "input_schema": wrapper.parameters(),
                "source": "live",
                "callable": True,
            })
        if live:
            return {"tools": live, "source": "live", **self.get_mcp_status(server_name)}
        cached = read_cache(server_name, self._mcp_config[server_name]) or []
        tools = [
            {
                "name": f"mcp_{server_name}_{item.get('name', '')}",
                "original_name": item.get("name", ""),
                "description": item.get("description", ""),
                "input_schema": item.get("inputSchema") or {},
                "source": "cache",
                "callable": False,
            }
            for item in cached
            if isinstance(item, dict) and item.get("name")
        ]
        return {"tools": tools, "source": "cache" if tools else "none", **self.get_mcp_status(server_name)}

    async def run(self) -> None:
        self._running = True
        await self._setup_mcp()
        logger.info(
            "SimpleAgentLoop started (LLM=%s, MCP=lazy, Skills=lazy)",
            "configured" if self._llm_runtime.configured else "unconfigured",
        )
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
            await self._cancel_owned_tasks()

    def stop(self) -> None:
        self._running = False
        for task in (*self._turn_tasks, *self._auxiliary_tasks):
            task.cancel()
        for handle in self._mcp_handles.values():
            asyncio.create_task(handle.aclose())

    async def _cancel_owned_tasks(self) -> None:
        current = asyncio.current_task()
        tasks = [
            task
            for task in (*self._turn_tasks, *self._auxiliary_tasks)
            if task is not current and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _release_turn_lock(self, chat_id: str, lock: asyncio.Lock) -> None:
        remaining = self._turn_lock_users.get(chat_id, 1) - 1
        if remaining <= 0:
            self._turn_lock_users.pop(chat_id, None)
            if self._turn_locks.get(chat_id) is lock:
                self._turn_locks.pop(chat_id, None)
        else:
            self._turn_lock_users[chat_id] = remaining

    async def _run_consolidation(
        self,
        plan: ConsolidationPlan,
        *,
        provider: str,
        model: str,
        lock: asyncio.Lock,
    ) -> None:
        completed = await self._consolidator.consolidate(
            plan,
            provider=provider,
            model=model,
        )
        if not completed:
            return

        async with lock:
            history, last_consolidated = self._store.load_history_smart(plan.chat_id)
            if not last_consolidated:
                logger.warning(
                    "Consolidator: persisted summary could not be reloaded for chat_id=%s",
                    plan.chat_id,
                )
                return
            current = self._sessions.get(plan.chat_id)
            if current is not None:
                current.clear()
                current.extend(history)
            self._last_consolidated[plan.chat_id] = last_consolidated

    def _schedule_consolidation(
        self,
        chat_id: str,
        history: list[dict[str, Any]],
        *,
        provider: str,
        model: str,
    ) -> None:
        existing = self._consolidation_tasks.get(chat_id)
        if existing is not None and not existing.done():
            logger.debug("Consolidator: already running for chat_id=%s", chat_id)
            return

        try:
            plan = self._consolidator.prepare(chat_id, history)
        except Exception as exc:
            logger.warning(
                "Consolidator: failed to prepare chat_id=%s",
                chat_id,
                exc_info=safe_exception_info(exc),
            )
            return
        if plan is None:
            return

        lock = self._turn_locks[chat_id]
        self._turn_lock_users[chat_id] = self._turn_lock_users.get(chat_id, 0) + 1
        task = asyncio.create_task(
            self._run_consolidation(
                plan,
                provider=provider,
                model=model,
                lock=lock,
            )
        )
        self._auxiliary_tasks.add(task)
        self._consolidation_tasks[chat_id] = task

        def finish(completed: asyncio.Task[Any]) -> None:
            self._auxiliary_tasks.discard(completed)
            if self._consolidation_tasks.get(chat_id) is completed:
                self._consolidation_tasks.pop(chat_id, None)
            self._release_turn_lock(chat_id, lock)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.warning(
                    "Consolidator: background task failed for chat_id=%s",
                    chat_id,
                    exc_info=safe_exception_info(error),
                )

        task.add_done_callback(finish)

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

    async def _publish_session_updated(self, chat_id: str, title: str) -> None:
        updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content="",
            metadata={
                "_session_updated": True,
                "_title": title,
                "_updated_at": updated_at,
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
        turn_id = uuid.uuid4().hex
        lock = self._turn_locks.setdefault(chat_id, asyncio.Lock())
        self._turn_lock_users[chat_id] = self._turn_lock_users.get(chat_id, 0) + 1
        with log_context(chat_id=chat_id, turn_id=turn_id):
            log_event(
                logger,
                logging.INFO,
                "agent.turn.started",
                channel=message.channel,
                content_chars=len(message.content),
            )
            try:
                async with lock:
                    await self._handle_turn_locked(message)
            except asyncio.CancelledError:
                log_event(logger, logging.INFO, "agent.turn.cancelled")
                raise
            finally:
                self._release_turn_lock(chat_id, lock)

    async def _handle_turn_locked(self, message: InboundMessage) -> None:
        chat_id = message.chat_id
        stream_id = id(message)
        started = time.monotonic()
        llm_selection = message.metadata.get("llm")
        provider = llm_selection.get("provider") if isinstance(llm_selection, dict) else None
        model = llm_selection.get("model") if isinstance(llm_selection, dict) else None
        if (
            not isinstance(provider, str)
            or not isinstance(model, str)
            or not self._llm_runtime.has_provider(provider)
        ):
            log_event(
                logger,
                logging.WARNING,
                "agent.turn.rejected",
                provider=provider,
                reason="llm_not_configured",
            )
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=str(LLMNotConfiguredError(provider)),
                metadata={"_user_error": True},
            ))
            return
        if chat_id not in self._sessions:
            history, last_consolidated = self._store.load_history_smart(chat_id)
            self._sessions[chat_id] = history
            self._last_consolidated[chat_id] = last_consolidated
        if chat_id not in self._session_metadata:
            self._session_metadata[chat_id] = self._store.read_session_metadata(chat_id)

        history = self._sessions[chat_id]
        metadata = self._session_metadata[chat_id]
        metadata_before_turn = copy.deepcopy(metadata)
        if not metadata.get("title") and not history:
            title = first_session_title(message.content)
            metadata["title"] = title
            self._store.write_session_metadata(chat_id, metadata)
            await self._publish_session_updated(chat_id, title)
        history.append({"role": "user", "content": message.content})

        activated_tools = ActivatedToolSet.from_session(metadata)
        activated_skills = ActivatedSkillSet.from_session(metadata)
        skill_context = TurnSkillContext(activated_skills)
        legacy_skill, task_content = parse_explicit_skill(message.content)
        # 结构化选择与旧式开头 @Skill 语法在进入当前轮前统一去重。
        selected_skill_rows = message.metadata.get("mentioned_skills", [])
        selected_mcp_rows = message.metadata.get("selected_mcp_connectors", [])
        selected_skills = [
            row["name"]
            for row in selected_skill_rows
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        ]
        if legacy_skill:
            selected_skills.append(legacy_skill)
        selected_skills = list(dict.fromkeys(selected_skills))
        selected_mcp = list(dict.fromkeys(
            row["server"]
            for row in selected_mcp_rows
            if isinstance(row, dict) and isinstance(row.get("server"), str)
        ))

        soul = self._store.read_soul() or _DEFAULT_SOUL
        memory = self._store.read_memory()
        system_content = soul
        if memory:
            system_content += f"\n\n## Remembered information\n{memory}"
        system_content += (
            "\n\n## Skill usage\nSearch installed workflows with skill_search, then call "
            "skill_load with an exact result. Skill bodies are current-turn-only and must "
            "be reloaded in a later turn when full guidance is needed. For an explicit "
            "request to create a Skill, load skill-creator and use agent_skill_manage; "
            "never create managed Skill files with write_file, edit_file, exec, curl, or "
            "ad hoc HTTP calls. Claim creation succeeded only when the managed tool returns "
            "success=true. If managed validation fails, correct the content and retry only "
            "through agent_skill_manage, or report the failure."
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
                # 显式选择的 MCP 只为当前轮提供临时可见性，不写入会话激活集。
                temporary_tools: set[str] = set()
                for server_name in selected_mcp:
                    status = await self.connect_mcp_server(server_name)
                    if status["status"] != "connected":
                        detail = status.get("status_error") or "connection failed"
                        raise ValueError(
                            f"Unable to prepare MCP {server_name}: {detail}"
                        )
                    owned = self._mcp_tool_names.get(server_name, set())
                    if not owned:
                        raise ValueError(
                            f"Unable to use MCP {server_name}: no tools were discovered"
                        )
                    temporary_tools.update(owned)

                explicit_receipts: list[dict[str, Any]] = []
                selected_bodies: list[str] = []
                for skill_name in selected_skills:
                    selected = ToolExecutionResult.coerce(
                        await self._skill_load_tool.execute(name=skill_name)
                    )
                    error = None
                    if selected.model_content.lstrip().startswith("{"):
                        try:
                            error = json.loads(selected.model_content).get("error")
                        except json.JSONDecodeError:
                            pass
                    if error:
                        raise ValueError(f"Unable to load @{skill_name}: {selected.model_content}")
                    selected_bodies.append(selected.model_content)
                    explicit_receipts.append(
                        {"role": "assistant", "content": selected.persisted}
                    )
                if selected_bodies:
                    messages.insert(1, {
                        "role": "system",
                        "content": (
                            "The user explicitly selected these Skills:\n\n"
                            + "\n\n---\n\n".join(selected_bodies)
                        ),
                    })
                with use_temporary_tools(temporary_tools):
                    trace = await self._runner.run(
                        messages,
                        self._deferred_registry,
                        chat_id=chat_id,
                        stream_id=stream_id,
                        provider=provider,
                        model=model,
                    )
                if explicit_receipts:
                    trace.durable_messages[0:0] = explicit_receipts
        except Exception as exc:
            logger.error(
                "event=agent.turn.failed duration_ms=%.2f error_type=%s",
                (time.monotonic() - started) * 1000,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            await self.bus.publish_outbound(OutboundMessage(
                channel="websocket",
                chat_id=chat_id,
                content=str(exc),
                metadata={"_user_error": True},
            ))
            if history and history[-1].get("role") == "user":
                history.pop()
            current_title = metadata.get("title")
            if current_title:
                metadata_before_turn["title"] = current_title
            self._session_metadata[chat_id] = metadata_before_turn
            return

        await self._stream_text(trace.final_text, chat_id, stream_id)
        history.extend(trace.durable_messages)
        history.append({"role": "assistant", "content": trace.final_text})
        if trace.durable_messages:
            self._store.append_traced_turn(
                chat_id,
                message.content,
                trace.durable_messages,
                trace.final_text,
                user_metadata=message.metadata,
            )
        else:
            self._store.append_turn(
                chat_id,
                message.content,
                trace.final_text,
                user_metadata=message.metadata,
            )
        self._store.write_session_metadata(chat_id, metadata)
        if self._skill_evolution is not None:
            self._skill_evolution.schedule_turn(
                chat_id=chat_id,
                user_content=message.content,
                final_content=trace.final_text,
                tools_used=trace.tools_used,
                durable_messages=trace.durable_messages,
                persisted=trace.success,
                provider=provider,
                model=model,
            )

        duration = time.monotonic() - started
        await self.bus.publish_outbound(OutboundMessage(
            channel="websocket",
            chat_id=chat_id,
            content=trace.final_text,
            metadata={"_turn_done": True, "_duration_sec": duration},
        ))
        log_event(
            logger,
            logging.INFO,
            "agent.turn.completed",
            duration_ms=round(duration * 1000, 2),
            output_chars=len(trace.final_text),
            tool_calls=len(trace.tools_used),
            iterations=trace.iterations,
            success=trace.success,
        )
        self._schedule_consolidation(
            chat_id,
            history,
            provider=provider,
            model=model,
        )
