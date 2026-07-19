# -*- coding: utf-8 -*-
"""MCP 连接层：连接外部 MCP server，并将其工具包装为 CashCode Tool。

参考 spore ``core.agent.tools.mcp``，大幅简化：
- 去掉鉴权、审批、backoff、generation 等复杂机制
- 只支持 stdio 传输（V1）
- 保留 owner-task 模式：transport 的 AnyIO cancel scope 必须在同一 task 内开启/关闭

暴露三个公共接口：
  establish_mcp_sessions(mcp_servers) → dict[str, MCPConnectionHandle]
  load_mcp_tools(handles, registry)   → None
  MCPToolWrapper(Tool)                → 单个 MCP 工具的适配器
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from .base import Tool

logger = logging.getLogger(__name__)

_MCP_CONNECT_TIMEOUT = 30.0   # 握手超时（秒）
_MCP_TOOL_TIMEOUT    = 30.0   # 单次工具调用超时（秒）


# ---------------------------------------------------------------------------
# MCPConnectionHandle：持有单个 MCP server 的连接生命周期
# ---------------------------------------------------------------------------

@dataclass
class MCPConnectionHandle:
    """对外暴露的连接句柄。

    内部由一个专属 owner task 持有 AsyncExitStack（transport + session），
    外部通过 session 属性调用工具，通过 aclose() 优雅关闭。
    """
    name: str
    _ready: asyncio.Future            # True = 连接就绪；False = 连接失败
    _close_requested: asyncio.Event   # set() 触发 owner task 关闭
    _owner_task: asyncio.Task
    _holder: dict = field(default_factory=dict)  # {"session": ClientSession | None}

    @property
    def session(self) -> Any | None:
        """返回 MCP ClientSession，连接未就绪时为 None。"""
        return self._holder.get("session")

    async def wait_ready(self, timeout: float = _MCP_CONNECT_TIMEOUT) -> bool:
        """等待连接就绪，返回 True 表示成功，False 表示失败/超时。"""
        try:
            return await asyncio.wait_for(asyncio.shield(self._ready), timeout=timeout)
        except asyncio.TimeoutError:
            return False

    async def aclose(self) -> None:
        """发送关闭信号并等待 owner task 结束。"""
        self._close_requested.set()
        try:
            await asyncio.wait_for(self._owner_task, timeout=10.0)
        except asyncio.TimeoutError:
            self._owner_task.cancel()
            await asyncio.gather(self._owner_task, return_exceptions=True)


# ---------------------------------------------------------------------------
# establish_mcp_sessions：为每个 server 建立连接
# ---------------------------------------------------------------------------

async def establish_mcp_sessions(
    mcp_servers: dict[str, dict],
) -> dict[str, MCPConnectionHandle]:
    """为配置中的每个 MCP server 建立 stdio 连接。

    每个 server 启动一个后台 asyncio.Task（owner task），
    在其内部用 AsyncExitStack 持有 transport + session 的整个生命周期。
    owner task 连接成功后通过 ready Future 通知，然后挂起等待关闭信号。

    Args:
        mcp_servers: {server_name: {type, command, args, env?, ...}}

    Returns:
        {server_name: MCPConnectionHandle}，只包含连接成功的 server。
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
        """owner task：负责连接 → 通知就绪 → 等待关闭 → 清理。"""
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            # 传输类型推断（与 spore 保持一致）
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
                read, write = await stack.enter_async_context(stdio_client(params))

            elif transport_type == "sse":
                from mcp.client.sse import sse_client
                url = cfg["url"]
                read, write = await stack.enter_async_context(sse_client(url))

            else:
                raise ValueError(f"MCP '{name}': unsupported transport type '{transport_type}' (streamableHttp not yet implemented)")

            # 建立 MCP session 并握手
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=_MCP_CONNECT_TIMEOUT)

            holder["session"] = session
            ready.set_result(True)
            logger.info("MCP '%s': connected", name)

            # 挂起，等待关闭信号
            await close_requested.wait()
            logger.info("MCP '%s': closing", name)
            await stack.aclose()

        except asyncio.CancelledError:
            try:
                await stack.aclose()
            except Exception:
                pass
            raise
        except Exception as exc:
            logger.warning("MCP '%s': connection failed — %s: %s", name, type(exc).__name__, exc)
            try:
                await stack.aclose()
            except Exception:
                pass
        finally:
            holder.pop("session", None)
            if not ready.done():
                ready.set_result(False)

    # 启动所有 owner tasks
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

    # 等待每个 server 就绪（或超时/失败）
    accepted: dict[str, MCPConnectionHandle] = {}
    for name, handle in pending.items():
        ok = await handle.wait_ready(timeout=_MCP_CONNECT_TIMEOUT)
        if ok:
            accepted[name] = handle
        else:
            logger.warning("MCP '%s': skipped (timeout or connect failure)", name)
            # 取消 owner task，避免泄漏
            handle._owner_task.cancel()
            await asyncio.gather(handle._owner_task, return_exceptions=True)

    return accepted


# ---------------------------------------------------------------------------
# MCPToolWrapper：将单个 MCP 工具适配为 CashCode Tool
# ---------------------------------------------------------------------------

def _normalize_schema(raw: Any) -> dict[str, Any]:
    """将 MCP inputSchema 标准化为 OpenAI 接受的格式。

    主要处理：{"type": ["string", "null"]} → {"type": "string", "nullable": true}
    """
    if not isinstance(raw, dict):
        return {"type": "object", "properties": {}, "required": []}

    schema = dict(raw)

    # 处理 type 为列表（nullable）的情况
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        non_null = [t for t in raw_type if t != "null"]
        if "null" in raw_type and len(non_null) == 1:
            schema["type"] = non_null[0]
            schema["nullable"] = True

    # 递归处理 properties
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
    """把外部 MCP server 的单个工具包装成 CashCode Tool。

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

    # Tool 抽象属性实现

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def parameters(self) -> dict[str, Any]:
        return self._params

    async def execute(self, **kwargs: Any) -> str:
        """调用 MCP server 工具，返回文本结果。超时或异常时返回错误字符串。"""
        from mcp.types import TextContent
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP tool '%s' timed out after %.0fs", self._name, self._timeout)
            return f"(MCP tool '{self._name}' timed out after {self._timeout:.0f}s)"
        except Exception as exc:
            logger.warning("MCP tool '%s' failed: %s: %s", self._name, type(exc).__name__, exc)
            return f"(MCP tool '{self._name}' failed: {type(exc).__name__}: {exc})"

        parts = []
        for block in result.content:
            if isinstance(block, TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


# ---------------------------------------------------------------------------
# load_mcp_tools：连接后列举工具并注册进 ToolRegistry
# ---------------------------------------------------------------------------

async def load_mcp_tools(
    handles: dict[str, MCPConnectionHandle],
    registry: Any,            # ToolRegistry，避免循环导入用 Any
) -> None:
    """对每个已连接的 MCP server，列举其工具并注册进 registry。"""
    for server_name, handle in handles.items():
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
            logger.info(
                "MCP '%s': %d tool(s) loaded", server_name, len(result.tools)
            )
        except Exception as exc:
            logger.warning(
                "MCP '%s': list_tools failed — %s: %s", server_name, type(exc).__name__, exc
            )


# ---------------------------------------------------------------------------
# lazy_connect — V2 按需连接单个 server
# ---------------------------------------------------------------------------

async def lazy_connect(
    server_name: str,
    config: dict,
    handles: "dict[str, MCPConnectionHandle]",
) -> bool:
    """按需建立单个 MCP server 的连接，合并进 handles dict。

    如果 server 已在 handles 中且连接仍可用，直接返回 True（不重连）。
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
