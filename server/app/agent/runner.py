"""非流式 ReAct Runner，返回完整且按用途投影的 Turn 轨迹。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from openai import AsyncOpenAI

from .tools.registry import ToolRegistry
from .tools.result import ToolExecutionResult

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 5
_MAX_ITERATIONS_MSG = (
    "[System] The maximum tool-call iterations were reached. "
    "Return the best answer available from the current evidence."
)


@dataclass(slots=True)
class TurnTrace:
    final_text: str
    model_messages: list[dict[str, Any]] = field(default_factory=list)
    durable_messages: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    success: bool = True
    error: str | None = None


class SimpleAgentRunner:
    """循环执行模型和工具，直到模型返回最终文本。"""

    MAX_ITERATIONS: int = _MAX_ITERATIONS

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        on_tool_call: Callable[..., Any] | None = None,
        on_tool_result: Callable[..., Any] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._on_tool_call = on_tool_call
        self._on_tool_result = on_tool_result

    async def run(
        self,
        messages: list[dict[str, Any]],
        registry: ToolRegistry,
        *,
        chat_id: str = "",
        stream_id: int = 0,
    ) -> TurnTrace:
        working = list(messages)
        model_delta: list[dict[str, Any]] = []
        durable_delta: list[dict[str, Any]] = []
        tools_used: list[str] = []
        had_tool_error = False

        for iteration in range(self.MAX_ITERATIONS):
            # tool_search、skill_load 或 mcp_prepare 执行后，可见工具可能发生变化。
            schemas = registry.get_definitions()
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": working,
                "stream": False,
            }
            if schemas:
                kwargs.update(tools=schemas, tool_choice="auto")
            response = await self._client.chat.completions.create(**kwargs)

            msg = response.choices[0].message
            tool_calls = msg.tool_calls
            if not tool_calls:
                final_text = msg.content or ""
                return TurnTrace(
                    final_text=final_text,
                    model_messages=model_delta,
                    durable_messages=durable_delta,
                    tools_used=tools_used,
                    iterations=iteration + 1,
                    success=not had_tool_error,
                    error="one or more tool calls failed" if had_tool_error else None,
                )

            assistant_message = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in tool_calls],
            }
            working.append(assistant_message)
            model_delta.append(assistant_message)
            durable_delta.append(dict(assistant_message))

            for call in tool_calls:
                tool_name = call.function.name
                tools_used.append(tool_name)
                try:
                    raw_args = call.function.arguments
                    params = json.loads(raw_args) if raw_args else {}
                    if not isinstance(params, dict):
                        params = {}
                except (json.JSONDecodeError, ValueError):
                    params = {}

                await self._notify_tool_call(chat_id, stream_id, tool_name, params)
                raw_result = await registry.execute(tool_name, params)
                result = ToolExecutionResult.coerce(raw_result)
                stripped_result = result.model_content.lstrip()
                had_tool_error = had_tool_error or stripped_result.startswith("Error")
                if stripped_result.startswith("{"):
                    try:
                        had_tool_error = had_tool_error or bool(json.loads(stripped_result).get("error"))
                    except (json.JSONDecodeError, AttributeError):
                        pass
                await self._notify_tool_result(
                    chat_id, stream_id, tool_name, result.public
                )

                model_message = {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": tool_name,
                    "content": result.model_content,
                }
                durable_message = {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": tool_name,
                    "content": result.persisted,
                }
                working.append(model_message)
                model_delta.append(model_message)
                durable_delta.append(durable_message)

        logger.warning("Runner: max iterations reached for chat_id=%s", chat_id)
        working.append({"role": "user", "content": _MAX_ITERATIONS_MSG})
        final_text = await self._call_llm_text(working)
        return TurnTrace(
            final_text=final_text,
            model_messages=model_delta,
            durable_messages=durable_delta,
            tools_used=tools_used,
            iterations=self.MAX_ITERATIONS,
            success=False,
            error="maximum tool-call iterations reached",
        )

    async def _call_llm_text(self, messages: list[dict[str, Any]]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, stream=False
        )
        return response.choices[0].message.content or ""

    async def _notify_tool_call(
        self,
        chat_id: str,
        stream_id: int,
        tool_name: str,
        params: dict[str, Any],
    ) -> None:
        if self._on_tool_call:
            value = self._on_tool_call(chat_id, stream_id, tool_name, params)
            if hasattr(value, "__await__"):
                await value

    async def _notify_tool_result(
        self,
        chat_id: str,
        stream_id: int,
        tool_name: str,
        result: str,
    ) -> None:
        if self._on_tool_result:
            value = self._on_tool_result(chat_id, stream_id, tool_name, result)
            if hasattr(value, "__await__"):
                await value
