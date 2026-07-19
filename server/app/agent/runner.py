"""SimpleAgentRunner：非流式 ReAct 循环，处理工具调用阶段。

参考 spore ``core.agent.runner.AgentRunner``，去掉收敛策略、工具审批、mid-turn 注入等
复杂机制，保留最小可用的工具调用循环。

执行策略：
  - 所有轮次（含最终轮）均使用非流式 API
  - 工具调用前后通过回调发布 WS 事件（_tool_call / _tool_result）
  - 返回 (final_text, updated_messages)，loop.py 负责将 final_text 切块发给前端
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

from openai import AsyncOpenAI

from .tools.base import Tool

logger = logging.getLogger(__name__)

# 工具调用轮次上限，防止无限循环
_MAX_ITERATIONS = 5
_MAX_ITERATIONS_MSG = (
    "[系统提示] 已达到最大工具调用次数，请直接给出当前已知的最佳回复。"
)


class SimpleAgentRunner:
    """非流式 ReAct 循环。

    Phase 1 专用：处理 LLM 的工具调用请求，直到 LLM 不再发起工具调用为止。
    loop.py 收到返回的 final_text 后负责以分块方式流式发给用户（fake streaming）。

    回调约定：
      on_tool_call(chat_id, stream_id, tool_name, tool_args) → None（可 async）
      on_tool_result(chat_id, stream_id, tool_name, result)  → None（可 async）
    """

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

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def run(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool],
        *,
        chat_id: str = "",
        stream_id: int = 0,
    ) -> tuple[str, list[dict[str, Any]]]:
        """执行 ReAct 循环，返回 (final_text, updated_messages)。

        updated_messages 包含完整的工具调用链（tool_calls + tool_results + 最终回复），
        供 loop.py 同步到 in-memory history 并持久化到 history.jsonl。

        若没有工具或 LLM 直接返回文字，则 updated_messages == 原始 messages（无修改）。
        """
        if not tools:
            # 无工具：直接非流式调用，返回文字
            return await self._call_llm_text(messages), messages

        schemas = [t.to_openai_schema() for t in tools]
        tool_map = {t.name: t for t in tools}
        working = list(messages)

        for iteration in range(self.MAX_ITERATIONS):
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=working,
                tools=schemas,
                tool_choice="auto",
                stream=False,
            )

            msg = response.choices[0].message
            tool_calls = msg.tool_calls

            if not tool_calls:
                # 无工具调用：LLM 给出最终文字回复
                final_text = msg.content or ""
                logger.info(
                    "Runner: done after %d iteration(s) for chat_id=%s",
                    iteration + 1, chat_id,
                )
                return final_text, working

            logger.info(
                "Runner: iteration %d, %d tool call(s) for chat_id=%s",
                iteration + 1, len(tool_calls), chat_id,
            )

            # 追加 assistant 消息（含 tool_calls）
            assistant_dict = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in tool_calls],
            }
            working.append(assistant_dict)

            # 逐一执行工具
            for call in tool_calls:
                tool_name = call.function.name
                try:
                    raw_args = call.function.arguments
                    kwargs = json.loads(raw_args) if raw_args else {}
                except (json.JSONDecodeError, ValueError):
                    kwargs = {}

                # WS 通知：工具调用开始
                await self._notify_tool_call(chat_id, stream_id, tool_name, kwargs)

                # 执行工具
                tool = tool_map.get(tool_name)
                if tool is None:
                    result = f"未知工具：{tool_name}"
                    logger.warning("Runner: unknown tool '%s'", tool_name)
                else:
                    try:
                        result = await tool.execute(**kwargs)
                    except Exception:
                        result = f"工具 {tool_name} 执行失败"
                        logger.exception("Runner: tool '%s' raised", tool_name)

                # WS 通知：工具执行完成
                await self._notify_tool_result(chat_id, stream_id, tool_name, result)

                # 追加工具结果消息
                working.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

        # 超出最大迭代次数：强制结束
        logger.warning("Runner: max iterations reached for chat_id=%s", chat_id)
        working.append({"role": "user", "content": _MAX_ITERATIONS_MSG})
        final_text = await self._call_llm_text(working)
        return final_text, working

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _call_llm_text(self, messages: list[dict[str, Any]]) -> str:
        """非流式调用 LLM，只返回文字内容（无工具）。"""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def _notify_tool_call(
        self,
        chat_id: str,
        stream_id: int,
        tool_name: str,
        kwargs: dict[str, Any],
    ) -> None:
        if self._on_tool_call:
            result = self._on_tool_call(chat_id, stream_id, tool_name, kwargs)
            if hasattr(result, "__await__"):
                await result

    async def _notify_tool_result(
        self,
        chat_id: str,
        stream_id: int,
        tool_name: str,
        result: str,
    ) -> None:
        if self._on_tool_result:
            cb = self._on_tool_result(chat_id, stream_id, tool_name, result)
            if hasattr(cb, "__await__"):
                await cb
