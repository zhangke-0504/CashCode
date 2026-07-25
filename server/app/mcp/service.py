"""协调 MCP 目录持久化与 Agent 实时连接状态的应用服务。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .models import MCPPermissionError, MCPServerRecord
from .store import MCPServerCatalog


class MCPManagementService:
    """在同一服务边界内协调目录变更与 Agent 运行时清理。"""

    def __init__(
        self,
        catalog: MCPServerCatalog,
        agent: Any,
        project_root: Path,
    ) -> None:
        self.catalog = catalog
        self.agent = agent
        self.project_root = project_root.resolve()
        self._mutation_lock = asyncio.Lock()

    def _public(self, record: MCPServerRecord) -> dict[str, Any]:
        """把目录记录和当前连接状态合成为公开 DTO。"""

        return record.to_public(self.agent.get_mcp_status(record.name))

    async def list_servers(self) -> list[dict[str, Any]]:
        """列出合并目录及每个服务的实时生命周期状态。"""

        return [self._public(record) for record in self.catalog.list()]

    async def create_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        """串行创建配置，并把新配置发布给 Agent，但不自动连接。"""

        async with self._mutation_lock:
            record = self.catalog.create(payload)
            await self.agent.replace_mcp_config(
                record.name, record.to_runtime(self.project_root)
            )
            return self._public(record)

    async def update_server(
        self, name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """串行替换用户配置，并让 Agent 清理旧连接和工具。"""

        async with self._mutation_lock:
            current = self.catalog.get(name)
            if not current.mutable:
                raise MCPPermissionError("built-in MCP servers are read-only")
            record = self.catalog.update(name, payload)
            await self.agent.replace_mcp_config(
                record.name, record.to_runtime(self.project_root)
            )
            return self._public(record)

    async def delete_server(self, name: str) -> None:
        """先完成运行时清理，再从用户目录删除配置。"""

        async with self._mutation_lock:
            current = self.catalog.get(name)
            if not current.mutable:
                raise MCPPermissionError("built-in MCP servers are read-only")
            await self.agent.remove_mcp_config(name)
            self.catalog.delete(name)

    async def connect_server(self, name: str) -> dict[str, Any]:
        """连接并发现指定服务的工具。"""

        record = self.catalog.get(name)
        await self.agent.connect_mcp_server(name)
        return self._public(record)

    async def disconnect_server(self, name: str) -> dict[str, Any]:
        """断开指定服务，并返回清理后的权威状态。"""

        record = self.catalog.get(name)
        await self.agent.disconnect_mcp_server(name)
        return self._public(record)

    async def list_tools(self, name: str) -> dict[str, Any]:
        """查询服务工具，并补充稳定名称和显示名称。"""

        record = self.catalog.get(name)
        data = self.agent.get_mcp_tools(name)
        return {
            "server": name,
            "display_name": record.display_name,
            **data,
        }
