"""合并只读内置目录与本地用户目录，并原子持久化用户 MCP 配置。"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .models import (
    MCPConflictError,
    MCPNotFoundError,
    MCPPermissionError,
    MCPServerRecord,
    MCPValidationError,
)


class MCPServerCatalog:
    """管理只读内置记录和以原子方式持久化的用户记录。"""

    def __init__(self, builtin_path: Path, user_path: Path) -> None:
        self.builtin_path = builtin_path.resolve()
        self.user_path = user_path.resolve()
        self._builtins: dict[str, MCPServerRecord] = {}
        self._users: dict[str, MCPServerRecord] = {}
        self.refresh()

    def refresh(self) -> None:
        """从两个目录来源重新加载并校验全部记录。"""

        self._builtins = self._read_builtins()
        self._users = self._read_users(self._builtins)

    def _read_json_mapping(self, path: Path, *, missing_ok: bool) -> dict[str, Any]:
        """读取以服务名为键的 JSON 对象，并统一处理文件或格式错误。"""

        if not path.exists():
            if missing_ok:
                return {}
            raise MCPValidationError(f"MCP catalog not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MCPValidationError(f"unable to read MCP catalog {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise MCPValidationError(f"MCP catalog {path.name} must contain an object")
        return data

    def _read_builtins(self) -> dict[str, MCPServerRecord]:
        """读取源码内置目录，并将每一项规范化为只读记录。"""

        raw = self._read_json_mapping(self.builtin_path, missing_ok=True)
        return {name: MCPServerRecord.from_builtin(name, value) for name, value in raw.items()}

    def _read_users(
        self, builtins: dict[str, MCPServerRecord]
    ) -> dict[str, MCPServerRecord]:
        """读取用户目录，同时阻止用户名称遮蔽内置服务。"""

        raw = self._read_json_mapping(self.user_path, missing_ok=True)
        users: dict[str, MCPServerRecord] = {}
        for name, value in raw.items():
            record = MCPServerRecord.from_user(value, name=name)
            if record.name in builtins:
                raise MCPConflictError(f"user MCP name conflicts with built-in: {record.name}")
            users[record.name] = record
        return users

    def list(self) -> list[MCPServerRecord]:
        """按稳定名称返回合并后的目录。"""

        return sorted([*self._builtins.values(), *self._users.values()], key=lambda row: row.name)

    def get(self, name: str) -> MCPServerRecord:
        """按名称读取记录，不存在时抛出领域异常。"""

        record = self._builtins.get(name) or self._users.get(name)
        if record is None:
            raise MCPNotFoundError(f"MCP server not found: {name}")
        return record

    def create(self, payload: Any) -> MCPServerRecord:
        """校验并原子写入一个新的用户服务。"""

        record = MCPServerRecord.from_user(payload)
        if record.name in self._builtins or record.name in self._users:
            raise MCPConflictError(f"MCP server already exists: {record.name}")
        next_users = {**self._users, record.name: record}
        self._write_users(next_users)
        self._users = next_users
        return record

    def update(self, name: str, payload: Any) -> MCPServerRecord:
        """更新用户服务；内置服务在存储层仍会被强制拒绝。"""

        if name in self._builtins:
            raise MCPPermissionError("built-in MCP servers are read-only")
        existing = self._users.get(name)
        if existing is None:
            raise MCPNotFoundError(f"MCP server not found: {name}")
        record = MCPServerRecord.from_user(payload, name=name, existing=existing)
        next_users = {**self._users, name: record}
        self._write_users(next_users)
        self._users = next_users
        return record

    def delete(self, name: str) -> None:
        """从用户目录删除服务；内置服务不可删除。"""

        if name in self._builtins:
            raise MCPPermissionError("built-in MCP servers are read-only")
        if name not in self._users:
            raise MCPNotFoundError(f"MCP server not found: {name}")
        next_users = dict(self._users)
        del next_users[name]
        self._write_users(next_users)
        self._users = next_users

    def runtime_configs(self, project_root: Path) -> dict[str, dict[str, Any]]:
        """生成供 Agent 启动和热更新使用的合并运行时配置。"""

        return {record.name: record.to_runtime(project_root) for record in self.list()}

    def _write_users(self, users: dict[str, MCPServerRecord]) -> None:
        """先写临时文件再原子替换，避免中断时损坏用户目录。"""

        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            name: record.to_storage()
            for name, record in sorted(users.items())
        }
        tmp = self.user_path.with_name(
            f".{self.user_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, self.user_path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
