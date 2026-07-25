"""MCP 配置领域模型，以及名称、SSE 地址和请求头的安全校验。"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

MASKED_HEADER_VALUE = "********"
SERVER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")

MAX_DISPLAY_NAME = 100
MAX_DESCRIPTION = 1000
MAX_URL = 2048
MAX_HEADERS = 32
MAX_HEADER_VALUE = 4096


class MCPError(ValueError):
    """MCP 管理领域异常的基类。"""


class MCPValidationError(MCPError):
    pass


class MCPConflictError(MCPError):
    pass


class MCPNotFoundError(MCPError):
    pass


class MCPPermissionError(MCPError):
    pass


def validate_server_name(value: Any) -> str:
    """校验并返回可用于持久化和工具命名的稳定服务标识。"""

    name = str(value or "").strip()
    if not SERVER_NAME_RE.fullmatch(name):
        raise MCPValidationError(
            "name must start with a lowercase letter or digit and contain only "
            "lowercase letters, digits, underscores, or hyphens (max 64)"
        )
    return name


def validate_sse_url(value: Any) -> str:
    """校验 SSE 地址为不含内嵌凭据的绝对 HTTP(S) URL。"""

    url = str(value or "").strip()
    if not url or len(url) > MAX_URL:
        raise MCPValidationError("url is required and must be at most 2048 characters")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MCPValidationError("url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise MCPValidationError("url must not contain embedded credentials")
    return url


def normalize_headers(
    raw: Any,
    *,
    existing: Mapping[str, str] | None = None,
    allow_masked: bool = False,
) -> dict[str, str]:
    """校验请求头，并在编辑时按掩码占位符保留已存密钥。"""

    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise MCPValidationError("headers must be an object")
    if len(raw) > MAX_HEADERS:
        raise MCPValidationError(f"headers may contain at most {MAX_HEADERS} entries")

    normalized: dict[str, str] = {}
    existing = existing or {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name or "").strip()
        if not HEADER_NAME_RE.fullmatch(name):
            raise MCPValidationError(f"invalid header name: {name!r}")
        if not isinstance(raw_value, str):
            raise MCPValidationError(f"header {name!r} must have a string value")
        if raw_value == MASKED_HEADER_VALUE:
            if allow_masked and name in existing:
                normalized[name] = existing[name]
                continue
            raise MCPValidationError(f"header {name!r} uses a masked value without a stored secret")
        if not raw_value or len(raw_value) > MAX_HEADER_VALUE:
            raise MCPValidationError(
                f"header {name!r} must be non-empty and at most {MAX_HEADER_VALUE} characters"
            )
        if "\r" in raw_value or "\n" in raw_value:
            raise MCPValidationError(f"header {name!r} must not contain newlines")
        normalized[name] = raw_value
    return normalized


def masked_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """生成只暴露请求头名称、不暴露值的公开投影。"""

    return {name: MASKED_HEADER_VALUE for name in sorted(headers)}


@dataclass(frozen=True, slots=True)
class MCPServerRecord:
    """统一表示只读内置服务和可变用户服务的规范化记录。"""

    name: str
    type: str
    display_name: str
    description: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    builtin: bool = False

    @property
    def mutable(self) -> bool:
        """标识该记录是否允许通过管理 API 修改。"""

        return not self.builtin

    @classmethod
    def from_builtin(cls, name: str, raw: Any) -> "MCPServerRecord":
        """从源码目录配置构建允许 stdio 或 SSE 的内置记录。"""

        name = validate_server_name(name)
        if not isinstance(raw, Mapping):
            raise MCPValidationError(f"built-in MCP {name!r} must be an object")
        transport = str(raw.get("type") or "").strip()
        command = str(raw.get("command") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not transport:
            transport = "stdio" if command else "sse" if url.endswith("/sse") else "streamableHttp"
        if transport not in {"stdio", "sse"}:
            raise MCPValidationError(f"built-in MCP {name!r} uses unsupported transport {transport!r}")
        if transport == "stdio" and not command:
            raise MCPValidationError(f"built-in stdio MCP {name!r} requires command")
        if transport == "sse":
            url = validate_sse_url(url)
        display_name = str(raw.get("display_name") or name).strip()[:MAX_DISPLAY_NAME] or name
        description = str(raw.get("description") or "").strip()[:MAX_DESCRIPTION]
        args = raw.get("args") or []
        env = raw.get("env") or {}
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise MCPValidationError(f"built-in MCP {name!r} args must be a string list")
        if not isinstance(env, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()
        ):
            raise MCPValidationError(f"built-in MCP {name!r} env must be a string map")
        return cls(
            name=name,
            type=transport,
            display_name=display_name,
            description=description,
            url=url,
            headers=normalize_headers(raw.get("headers")),
            command=command,
            args=tuple(args),
            env=dict(env),
            builtin=True,
        )

    @classmethod
    def from_user(
        cls,
        raw: Any,
        *,
        name: str | None = None,
        existing: "MCPServerRecord | None" = None,
    ) -> "MCPServerRecord":
        """从用户请求构建仅允许 SSE 的记录，并支持保留掩码请求头。"""

        if not isinstance(raw, Mapping):
            raise MCPValidationError("MCP payload must be an object")
        server_name = validate_server_name(name if name is not None else raw.get("name"))
        transport = str(raw.get("type") or "sse").strip()
        if transport != "sse":
            raise MCPValidationError("user MCP servers support only the sse transport")
        display_name = str(raw.get("display_name") or raw.get("displayName") or "").strip()
        if not display_name or len(display_name) > MAX_DISPLAY_NAME:
            raise MCPValidationError("display_name is required and must be at most 100 characters")
        description = str(raw.get("description") or "").strip()
        if len(description) > MAX_DESCRIPTION:
            raise MCPValidationError("description must be at most 1000 characters")
        existing_headers = existing.headers if existing is not None else None
        return cls(
            name=server_name,
            type="sse",
            display_name=display_name,
            description=description,
            url=validate_sse_url(raw.get("url")),
            headers=normalize_headers(
                raw.get("headers"),
                existing=existing_headers,
                allow_masked=existing is not None,
            ),
            builtin=False,
        )

    def to_storage(self) -> dict[str, Any]:
        """生成包含真实本地配置值的持久化结构。"""

        data: dict[str, Any] = {
            "type": self.type,
            "display_name": self.display_name,
            "description": self.description,
        }
        if self.url:
            data["url"] = self.url
        if self.headers:
            data["headers"] = dict(self.headers)
        if self.command:
            data["command"] = self.command
        if self.args:
            data["args"] = list(self.args)
        if self.env:
            data["env"] = dict(self.env)
        return data

    def to_runtime(self, project_root: Path) -> dict[str, Any]:
        """生成运行时配置，并将内置 stdio 的相对参数路径转为绝对路径。"""

        data = copy.deepcopy(self.to_storage())
        if self.type == "stdio":
            data["args"] = [
                str((project_root / value).resolve()) if not Path(value).is_absolute() else value
                for value in self.args
            ]
        return data

    def to_public(self, status: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """生成前端 DTO，其中请求头值始终使用掩码。"""

        status = status or {}
        lifecycle = str(status.get("status") or "disconnected")
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "type": self.type,
            "url": self.url,
            "headers": masked_headers(self.headers),
            "builtin": self.builtin,
            "mutable": self.mutable,
            "status": lifecycle,
            "connected": lifecycle == "connected",
            "status_error": status.get("status_error"),
            "tool_count": int(status.get("tool_count") or 0),
        }
