# Spec: Tool Calling

## Purpose

TBD — 提供工具调用的标准抽象接口（`Tool` 基类）与 ReAct 循环执行器（`SimpleAgentRunner`），使 Agent 能以结构化方式调用外部工具并将结果反馈给 LLM。

## Requirements

### Requirement: Tool base class defines standard interface
系统 SHALL 提供 `Tool` 抽象基类，定义工具的标准接口：`name`（工具名）、`description`（LLM 可读的调用说明）、`parameters() -> dict`（OpenAI JSON Schema 格式的参数定义）、`to_openai_schema() -> dict`（生成完整 OpenAI tool schema）、`async execute(**kwargs) -> str`（工具执行，返回结果字符串）。

#### Scenario: Tool schema generated correctly
- **WHEN** 调用 `tool.to_openai_schema()`
- **THEN** 返回 `{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}` 格式的字典，可直接传入 OpenAI API 的 `tools` 参数

### Requirement: SimpleAgentRunner executes ReAct loop
系统 SHALL 提供 `SimpleAgentRunner`，实现非流式 ReAct 循环：传入 messages + tools 列表，循环调用 LLM（非流式）；若响应含 `tool_calls` 则逐一执行工具并将结果追加到 messages；若无 `tool_calls` 则返回最终文字回复。循环上限 `MAX_ITERATIONS=5`，超出时返回错误提示文本。每次工具调用前后 SHALL 通过回调发布 `_tool_call` / `_tool_result` WS 事件。

#### Scenario: Tool called and result fed back to LLM
- **WHEN** LLM 返回含 `tool_calls` 的响应
- **THEN** Runner 执行对应工具，将工具结果追加为 `role: "tool"` 消息，再次调用 LLM

#### Scenario: Loop terminates when no tool calls
- **WHEN** LLM 响应不含 `tool_calls`
- **THEN** Runner 返回 `(final_text, updated_messages)`，不再调用 LLM

#### Scenario: Loop terminates at max iterations
- **WHEN** 连续 5 次 LLM 调用均含 tool_calls
- **THEN** Runner 返回错误提示文本，不无限循环

#### Scenario: WS events emitted per tool call
- **WHEN** 每次工具被调用前
- **THEN** 发布 `_tool_call` 事件（含 tool_name）；工具执行完成后发布 `_tool_result` 事件（含 tool_name 和结果摘要）
