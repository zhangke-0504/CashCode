# -*- coding: utf-8 -*-
"""MCP 连接层：连接外部 MCP 服务，并将其工具包装为 CashCode 工具。

参考 spore ``core.agent.tools.mcp``，大幅简化：
- 去掉鉴权、审批、退避重试、连接代次等复杂机制
- 支持内置 stdio 和用户 SSE 传输
- 保留所有者任务模式：传输层的 AnyIO 取消作用域必须在同一任务内开启和关闭

暴露三个公共接口：
  establish_mcp_sessions(mcp_servers) → 连接句柄字典
  load_mcp_tools(handles, registry)   → 注册工具
  MCPToolWrapper(Tool)                → 单个 MCP 工具的适配器
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from ...logging_config import log_event, redact_sensitive_text
from .base import Tool

logger = logging.getLogger(__name__)

_MCP_CONNECT_TIMEOUT = 30.0   # 握手超时（秒）
_MCP_TOOL_TIMEOUT    = 30.0   # 单次工具调用超时（秒）


# ---------------------------------------------------------------------------
# MCPConnectionHandle：持有单个 MCP 服务的连接生命周期
# ---------------------------------------------------------------------------

class _MCPStderrSink:
    """Bridge child stderr signals to metadata-only application events."""

    encoding = "utf-8"

    def __init__(self, server_name: str) -> None:
        self._server_name = server_name

    def write(self, value: str) -> int:
        if value.strip():
            log_event(
                logger,
                logging.WARNING,
                "mcp.stdio.stderr",
                server=self._server_name,
                chars=len(value),
                lines=value.count("\n") or 1,
            )
        return len(value)

    def flush(self) -> None:
        return None


@dataclass
class MCPConnectionHandle:
    """对外暴露的连接句柄。

    内部由一个专属所有者任务持有 AsyncExitStack（传输 + 会话），
    外部通过 session 属性调用工具，通过 aclose() 优雅关闭。
    """
    name: str
    _ready: asyncio.Future            # True = 连接就绪；False = 连接失败
    _close_requested: asyncio.Event   # 调用 set() 触发所有者任务关闭。
    _owner_task: asyncio.Task
    _holder: dict = field(default_factory=dict)  # 保存当前会话或脱敏连接错误。

    @property
    def session(self) -> Any | None:
        """返回 MCP ClientSession，连接未就绪时为 None。"""
        return self._holder.get("session")

    @property
    def error(self) -> str | None:
        """返回连接阶段记录的脱敏错误；成功连接时为 None。"""

        value = self._holder.get("error")
        return value if isinstance(value, str) else None

    async def wait_ready(self, timeout: float = _MCP_CONNECT_TIMEOUT) -> bool:
        """等待连接就绪，返回 True 表示成功，False 表示失败/超时。"""
        try:
            return await asyncio.wait_for(asyncio.shield(self._ready), timeout=timeout)
        except asyncio.TimeoutError:
            return False

    async def aclose(self) -> None:
        """发送关闭信号并等待所有者任务结束。"""
        self._close_requested.set()
        try:
            await asyncio.wait_for(self._owner_task, timeout=10.0)
        except asyncio.TimeoutError:
            self._owner_task.cancel()
            await asyncio.gather(self._owner_task, return_exceptions=True)


# ---------------------------------------------------------------------------
# establish_mcp_sessions：为每个服务建立连接
# ---------------------------------------------------------------------------

async def establish_mcp_sessions(
    mcp_servers: dict[str, dict],
    errors_out: dict[str, str] | None = None,
) -> dict[str, MCPConnectionHandle]:
    """为配置中的每个 MCP 服务建立 stdio 或 SSE 连接。

    每个服务启动一个后台 asyncio.Task 作为所有者任务，
    在其内部用 AsyncExitStack 持有 transport + session 的整个生命周期。
    所有者任务连接成功后通过就绪 Future 通知，然后挂起等待关闭信号。

    参数：
        mcp_servers: ``{服务名: {type, command, args, env?, ...}}``

    返回：
        ``{服务名: MCPConnectionHandle}``，只包含连接成功的服务。
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def owner(
        name: str,
        cfg: dict,
        ready: asyncio.Future,
        close_requested: asyncio.Event,
        holder: dict,
    ) -> None:
        """所有者任务：负责连接、通知就绪、等待关闭并清理资源。"""
        started = time.monotonic()
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            # 传输类型推断规则与 spore 保持一致。
            transport_type = cfg.get("type")
            if not transport_type:
                if cfg.get("command"):
                    transport_type = "stdio"
                elif cfg.get("url", "").rstrip("/").endswith("/sse"):
                    transport_type = "sse"
                elif cfg.get("url"):
                    transport_type = "streamableHttp"
                else:
                    raise ValueError(f"MCP '{name}': no command or url configured")

            if transport_type == "stdio":
                command = cfg.get("command", "python")
                args    = cfg.get("args", [])
                env     = cfg.get("env") or None
                params  = StdioServerParameters(command=command, args=args, env=env)
                read, write = await stack.enter_async_context(
                    stdio_client(params, errlog=_MCPStderrSink(name))
                )

            elif transport_type == "sse":
                from mcp.client.sse import sse_client
                url = cfg["url"]
                headers = cfg.get("headers") or None
                read, write = await stack.enter_async_context(
                    sse_client(url, headers=headers)
                )

            else:
                raise ValueError(f"MCP '{name}': unsupported transport type '{transport_type}' (streamableHttp not yet implemented)")

            # 建立 MCP 会话并完成初始化握手。
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=_MCP_CONNECT_TIMEOUT)

            holder["session"] = session
            ready.set_result(True)
            log_event(
                logger,
                logging.INFO,
                "mcp.connection.connected",
                server=name,
                transport=transport_type,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )

            # 挂起，等待关闭信号
            await close_requested.wait()
            log_event(
                logger,
                logging.INFO,
                "mcp.connection.closing",
                server=name,
                lifetime_ms=round((time.monotonic() - started) * 1000, 2),
            )
            await stack.aclose()

        except asyncio.CancelledError:
            try:
                await stack.aclose()
            except Exception:
                pass
            raise
        except Exception as exc:
            safe_error = _sanitize_connection_error(exc, cfg)
            holder["error"] = safe_error
            if errors_out is not None:
                errors_out[name] = safe_error
            log_event(
                logger,
                logging.WARNING,
                "mcp.connection.failed",
                server=name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
                detail=safe_error,
            )
            try:
                await stack.aclose()
            except Exception:
                pass
        finally:
            holder.pop("session", None)
            if not ready.done():
                ready.set_result(False)

    # 为每个服务启动独立的所有者任务。
    pending: dict[str, MCPConnectionHandle] = {}
    loop = asyncio.get_running_loop()

    for name, cfg in mcp_servers.items():
        ready           = loop.create_future()
        close_requested = asyncio.Event()
        holder: dict    = {}
        task = asyncio.create_task(
            owner(name, cfg, ready, close_requested, holder),
            name=f"mcp-owner:{name}",
        )
        pending[name] = MCPConnectionHandle(
            name=name,
            _ready=ready,
            _close_requested=close_requested,
            _owner_task=task,
            _holder=holder,
        )

    # 等待每个服务就绪，或确认其超时、失败。
    accepted: dict[str, MCPConnectionHandle] = {}
    for name, handle in pending.items():
        ok = await handle.wait_ready(timeout=_MCP_CONNECT_TIMEOUT)
        if ok:
            accepted[name] = handle
        else:
            logger.warning("MCP '%s': skipped (timeout or connect failure)", name)
            # 取消未就绪的所有者任务，避免资源泄漏。
            handle._owner_task.cancel()
            await asyncio.gather(handle._owner_task, return_exceptions=True)

    return accepted


# ---------------------------------------------------------------------------
# MCPToolWrapper：将单个 MCP 工具适配为 CashCode 工具
# ---------------------------------------------------------------------------

def _normalize_schema(raw: Any) -> dict[str, Any]:
    """将 MCP ``inputSchema`` 标准化为 OpenAI 接受的格式。

    主要处理：{"type": ["string", "null"]} → {"type": "string", "nullable": true}
    """
    if not isinstance(raw, dict):
        return {"type": "object", "properties": {}, "required": []}

    schema = dict(raw)

    # 处理 type 为列表且包含 null 的可空情况。
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        non_null = [t for t in raw_type if t != "null"]
        if "null" in raw_type and len(non_null) == 1:
            schema["type"] = non_null[0]
            schema["nullable"] = True

    # 递归规范化属性集合中的子结构。
    if "properties" in schema and isinstance(schema["properties"], dict):
        schema["properties"] = {
            k: _normalize_schema(v) if isinstance(v, dict) else v
            for k, v in schema["properties"].items()
        }

    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema.setdefault("required", [])
    return schema


class MCPToolWrapper(Tool):
    """把外部 MCP 服务的单个工具包装成 CashCode 工具。

    对外（ToolRegistry、runner）：表现为普通 Tool，有 name/description/parameters/execute。
    对内（execute 时）：通过 session.call_tool() 把调用转发给外部进程。

    工具名命名规则：mcp_{server_name}_{tool_def.name}
    """

    def __init__(
        self,
        session: Any,
        server_name: str,
        tool_def: Any,
        timeout: float = _MCP_TOOL_TIMEOUT,
    ) -> None:
        self._session       = session
        self._server_name   = server_name
        self._original_name = tool_def.name                          # MCP 侧原始名
        self._name          = f"mcp_{server_name}_{tool_def.name}"  # CashCode 侧名
        self._description   = tool_def.description or tool_def.name
        self._params        = _normalize_schema(tool_def.inputSchema or {})
        self._timeout       = timeout

    # 实现 Tool 抽象接口。

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def parameters(self) -> dict[str, Any]:
        return self._params

    async def execute(self, **kwargs: Any) -> str:
        """调用 MCP 服务工具，返回文本结果；超时或异常时返回错误字符串。"""
        from mcp.types import TextContent
        started = time.monotonic()
        log_event(
            logger,
            logging.DEBUG,
            "mcp.tool.started",
            server=self._server_name,
            tool=self._original_name,
        )
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            log_event(
                logger,
                logging.WARNING,
                "mcp.tool.timed_out",
                server=self._server_name,
                tool=self._original_name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                timeout_seconds=self._timeout,
            )
            return f"(MCP tool '{self._name}' timed out after {self._timeout:.0f}s)"
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "mcp.tool.failed",
                server=self._server_name,
                tool=self._original_name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            return f"(MCP tool '{self._name}' failed: {type(exc).__name__}: {exc})"

        parts = []
        for block in result.content:
            if isinstance(block, TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        output = "\n".join(parts) or "(no output)"
        log_event(
            logger,
            logging.INFO,
            "mcp.tool.completed",
            server=self._server_name,
            tool=self._original_name,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            content_blocks=len(result.content),
            result_chars=len(output),
        )
        return output


# ---------------------------------------------------------------------------
# load_mcp_tools：连接后列举工具并注册进 ToolRegistry
# ---------------------------------------------------------------------------

async def load_mcp_tools(
    handles: dict[str, MCPConnectionHandle],
    registry: Any,            # 使用 Any 标注 ToolRegistry，避免循环导入。
) -> None:
    """列举每个已连接 MCP 服务的工具并注册进工具注册表。"""
    for server_name, handle in handles.items():
        started = time.monotonic()
        session = handle.session
        if session is None:
            logger.warning("MCP '%s': session unavailable, skipping tool load", server_name)
            continue
        try:
            result = await session.list_tools()
            for tool_def in result.tools:
                wrapper = MCPToolWrapper(session, server_name, tool_def)
                registry.register(wrapper)
                logger.info("MCP tool registered: %s", wrapper.name)
            log_event(
                logger,
                logging.INFO,
                "mcp.tools.discovered",
                server=server_name,
                tool_count=len(result.tools),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "mcp.tools.discovery_failed",
                server=server_name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )


# ---------------------------------------------------------------------------
# lazy_connect：V2 按需连接单个服务
# ---------------------------------------------------------------------------

async def lazy_connect(
    server_name: str,
    config: dict,
    handles: "dict[str, MCPConnectionHandle]",
) -> bool:
    """按需建立单个 MCP 服务的连接，并合并进句柄字典。

    如果服务已在句柄字典中且连接仍可用，直接返回 True，不重复连接。
    返回 True 表示成功，False 表示连接失败。
    """
    existing = handles.get(server_name)
    if existing is not None and existing.session is not None:
        logger.debug("lazy_connect: '%s' already connected", server_name)
        return True

    logger.info("lazy_connect: connecting '%s'...", server_name)
    new_handles = await establish_mcp_sessions({server_name: config})
    if server_name not in new_handles:
        logger.warning("lazy_connect: '%s' failed to connect", server_name)
        return False

    handles[server_name] = new_handles[server_name]
    logger.info("lazy_connect: '%s' connected", server_name)
    return True


def _sanitize_connection_error(exc: Exception, config: dict[str, Any]) -> str:
    """生成有长度上限的连接错误，并移除配置中的请求头密钥值。"""

    text = f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")
    headers = config.get("headers") or {}
    if isinstance(headers, dict):
        for secret in headers.values():
            if isinstance(secret, str) and secret:
                text = text.replace(secret, "[redacted]")
    configured_env = config.get("env") or {}
    if isinstance(configured_env, dict):
        for key, secret in configured_env.items():
            if (
                isinstance(key, str)
                and any(label in key.lower() for label in ("key", "token", "secret", "password"))
                and isinstance(secret, str)
                and secret
            ):
                text = text.replace(secret, "[redacted]")
    return redact_sensitive_text(text)[:500]
