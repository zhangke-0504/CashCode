# -*- coding: utf-8 -*-
"""MCP 工具结构的磁盘缓存（简化版）。

参考 spore ``core.agent.tools.mcp_cache``，去掉企业目录版本管理，
只保留传输指纹失效机制。

缓存文件：<project_root>/mcp_cache/<server_name>.json
缓存键：sha256(command+args+env+url)[:16]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 项目根目录（从 server/app/agent/tools/ 向上四级）。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CACHE_DIR = _PROJECT_ROOT / "mcp_cache"


def _cache_path(server_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in server_name)
    return _CACHE_DIR / f"{safe}.json"


def compute_transport_fingerprint(config: dict) -> str:
    """计算服务配置的传输指纹，即关键连接字段哈希值的前 16 位。"""
    relevant = {
        "command": config.get("command", ""),
        "args":    config.get("args", []),
        "env":     config.get("env") or {},
        "url":     config.get("url", ""),
    }
    canonical = json.dumps(relevant, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def read_cache(server_name: str, config: dict) -> list[dict[str, Any]] | None:
    """读取缓存；传输指纹不匹配或文件不存在时返回 None。"""
    path = _cache_path(server_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    expected_fp = compute_transport_fingerprint(config)
    if data.get("transport_fingerprint") != expected_fp:
        logger.debug("mcp_cache: '%s' fingerprint mismatch, ignoring", server_name)
        return None
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        return None
    return tools


def write_cache(
    server_name: str,
    config: dict,
    tools: list[dict[str, Any]],
    resources: list[dict[str, Any]] | None = None,
    prompts: list[dict[str, Any]] | None = None,
) -> None:
    """原子写入工具结构缓存。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(server_name)
    data: dict[str, Any] = {
        "transport_fingerprint": compute_transport_fingerprint(config),
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "tools":     tools,
        "resources": resources or [],
        "prompts":   prompts or [],
    }
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        logger.info("mcp_cache: wrote %d tool(s) for '%s'", len(tools), server_name)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def delete_cache(server_name: str) -> None:
    """配置被替换或删除后，移除对应服务的工具缓存。"""

    try:
        _cache_path(server_name).unlink(missing_ok=True)
    except OSError:
        logger.warning("mcp_cache: failed to remove cache for '%s'", server_name)
