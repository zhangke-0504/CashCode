"""MCP 市场管理 API：提供目录 CRUD、连接生命周期和工具查询接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ..mcp.models import (
    MCPConflictError,
    MCPError,
    MCPNotFoundError,
    MCPPermissionError,
    MCPValidationError,
)
from ..mcp.service import MCPManagementService

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPServerCreateRequest(BaseModel):
    """用户新建 SSE MCP 服务时提交的配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str = "sse"
    display_name: str
    description: str = ""
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class MCPServerUpdateRequest(BaseModel):
    """用户更新既有 SSE MCP 服务时提交的配置。"""

    model_config = ConfigDict(extra="forbid")

    type: str = "sse"
    display_name: str
    description: str = ""
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


def _service(request: Request) -> MCPManagementService:
    """从应用状态中取得启动阶段初始化的 MCP 管理服务。"""

    value = getattr(request.app.state, "mcp_service", None)
    if value is None:
        raise HTTPException(status_code=503, detail="MCP service is unavailable")
    return value


def _raise_mcp_error(exc: Exception) -> None:
    """将领域异常转换为稳定、可供前端处理的 HTTP 状态码。"""

    if isinstance(exc, MCPPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, MCPConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, MCPNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MCPValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, MCPError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/servers")
async def list_mcp_servers(request: Request) -> dict[str, Any]:
    """返回合并后的内置与用户 MCP 服务目录。"""

    return {"servers": await _service(request).list_servers()}


@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    request: Request, body: MCPServerCreateRequest
) -> dict[str, Any]:
    """创建一个仅支持 SSE 传输的用户 MCP 服务。"""

    try:
        return await _service(request).create_server(body.model_dump())
    except Exception as exc:
        _raise_mcp_error(exc)


@router.put("/servers/{name}")
async def update_mcp_server(
    request: Request, name: str, body: MCPServerUpdateRequest
) -> dict[str, Any]:
    """更新可变 MCP 配置，并清理该服务的旧运行时连接。"""

    try:
        return await _service(request).update_server(name, body.model_dump())
    except Exception as exc:
        _raise_mcp_error(exc)


@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(request: Request, name: str) -> Response:
    """清理运行时状态后删除指定的用户 MCP 服务。"""

    try:
        await _service(request).delete_server(name)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _raise_mcp_error(exc)


@router.post("/servers/{name}/connect")
async def connect_mcp_server(request: Request, name: str) -> dict[str, Any]:
    """显式连接服务，并在工具发现成功后返回权威状态。"""

    try:
        return await _service(request).connect_server(name)
    except Exception as exc:
        _raise_mcp_error(exc)


@router.post("/servers/{name}/disconnect")
async def disconnect_mcp_server(request: Request, name: str) -> dict[str, Any]:
    """显式断开服务并移除该服务拥有的实时工具。"""

    try:
        return await _service(request).disconnect_server(name)
    except Exception as exc:
        _raise_mcp_error(exc)


@router.get("/servers/{name}/tools")
async def list_mcp_server_tools(request: Request, name: str) -> dict[str, Any]:
    """查询指定服务的实时工具或指纹仍有效的缓存工具。"""

    try:
        return await _service(request).list_tools(name)
    except Exception as exc:
        _raise_mcp_error(exc)
