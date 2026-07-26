# -*- coding: utf-8 -*-
"""ToolRegistry：统一管理 CashCode 所有工具（内置 + MCP）。

参考 spore ``core.agent.tools.registry.ToolRegistry``，去掉
cast_params / validate_params 验证体系，保留最小可用接口：
  register / get / has / get_definitions / execute / tool_names
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ...logging_config import log_event, safe_exception_info
from .base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """所有工具的统一注册表。

    内部维护一个 ``{name: Tool}`` 字典。
    ``get_definitions()`` 返回的 schema 列表：内置工具（非 mcp_ 前缀）按名排序在前，
    MCP 工具（mcp_ 前缀）按名排序在后，并缓存直到下次 register/unregister。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._cached_definitions: list[dict[str, Any]] | None = None
        self._membership_revision: int = 0

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """注册工具，已存在同名工具时覆盖。"""
        self._tools[tool.name] = tool
        self._cached_definitions = None  # 缓存失效
        self._membership_revision += 1

    def unregister(self, name: str) -> None:
        """注销工具（不存在时静默忽略）。"""
        if self._tools.pop(name, None) is not None:
            self._cached_definitions = None
            self._membership_revision += 1

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, name: str) -> Tool | None:
        """按名称查找工具，不存在返回 None。"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        """返回所有已注册工具名称列表。"""
        return list(self._tools.keys())

    @property
    def membership_revision(self) -> int:
        """单调递增版本号，供 DeferredAwareRegistry 缓存失效用。"""
        return self._membership_revision

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # ------------------------------------------------------------------
    # schema（供 LLM 使用）
    # ------------------------------------------------------------------

    @staticmethod
    def _schema_name(schema: dict[str, Any]) -> str:
        """从 OpenAI schema 中提取工具名称。"""
        fn = schema.get("function")
        if isinstance(fn, dict):
            name = fn.get("name")
            if isinstance(name, str):
                return name
        name = schema.get("name")
        return name if isinstance(name, str) else ""

    def get_definitions(self) -> list[dict[str, Any]]:
        """返回所有工具的 OpenAI schema 列表（有缓存）。

        排序规则：内置工具（非 mcp_ 前缀）按名字母序在前，
        MCP 工具（mcp_ 前缀）按名字母序在后。
        稳定顺序可减少 LLM prompt cache 抖动。
        """
        if self._cached_definitions is not None:
            return self._cached_definitions

        definitions = [tool.to_schema() for tool in self._tools.values()]
        builtins: list[dict[str, Any]] = []
        mcp_tools: list[dict[str, Any]] = []
        for schema in definitions:
            if self._schema_name(schema).startswith("mcp_"):
                mcp_tools.append(schema)
            else:
                builtins.append(schema)
        builtins.sort(key=self._schema_name)
        mcp_tools.sort(key=self._schema_name)
        self._cached_definitions = builtins + mcp_tools
        return self._cached_definitions

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def execute(self, name: str, params: dict[str, Any]) -> Any:
        """查找并执行工具，返回结果字符串。工具不存在或执行出错时返回错误字符串。"""
        _HINT = "\n\n[Analyze the error above and try a different approach.]"
        tool = self._tools.get(name)
        if tool is None:
            log_event(
                logger,
                logging.WARNING,
                "tool.execution.rejected",
                tool=name,
                reason="not_found",
            )
            available = ", ".join(self.tool_names) or "(无)"
            return f"Error: Tool '{name}' not found. Available: {available}{_HINT}"
        started = time.monotonic()
        log_event(
            logger,
            logging.DEBUG,
            "tool.execution.started",
            tool=name,
        )
        try:
            result = await tool.execute(**params)
            log_event(
                logger,
                logging.INFO,
                "tool.execution.completed",
                tool=name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                result_length=self._result_length(result),
            )
            return result
        except Exception as exc:
            logger.error(
                "event=tool.execution.failed tool=%s duration_ms=%.2f error_type=%s",
                name,
                (time.monotonic() - started) * 1000,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return f"Error executing {name}: {exc}{_HINT}"

    @staticmethod
    def _result_length(result: Any) -> int | None:
        if isinstance(result, (str, bytes, list, tuple, dict, set)):
            return len(result)
        return None
