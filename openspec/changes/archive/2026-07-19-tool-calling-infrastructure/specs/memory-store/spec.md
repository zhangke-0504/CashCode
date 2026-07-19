## ADDED Requirements

### Requirement: Persist full tool chain to history atomically
`MemoryStore` SHALL 提供 `append_tool_turn(chat_id, user_content, tool_calls_msg, tool_results, final_reply)` 方法，将一轮含工具调用的完整对话原子写入 history.jsonl：user → tool_calls → tool_result(s) → assistant，各占一行，cursor 连续自增。若写入过程抛异常则不写入任何内容（原子性）。

#### Scenario: Full tool chain written as sequential records
- **WHEN** 一轮工具调用完成，调用 `append_tool_turn`
- **THEN** history.jsonl 追加 4 条记录：user（cursor N）、tool_calls（cursor N+1）、tool（cursor N+2）、assistant（cursor N+3），均含 cursor、timestamp、role、content 字段

#### Scenario: tool_calls record includes tool_calls array
- **WHEN** append_tool_turn 写入 tool_calls 记录
- **THEN** 该记录含 `"role": "tool_calls"` 和 `"tool_calls": [...]` 字段（OpenAI format）

### Requirement: Load history smart restores tool message types
`MemoryStore.load_history_smart` SHALL 在恢复历史时，将 `role: "tool_calls"` 记录恢复为含 `tool_calls` 字段的 assistant 消息，将 `role: "tool"` 记录恢复为含 `tool_call_id` 的 tool 消息，以便 LLM API 可直接接收。

#### Scenario: tool_calls role restored as assistant message with tool_calls
- **WHEN** history.jsonl 含 `role: "tool_calls"` 记录
- **THEN** load_history_smart 返回 `{"role": "assistant", "content": ..., "tool_calls": [...]}` 格式消息

#### Scenario: tool role restored as tool message
- **WHEN** history.jsonl 含 `role: "tool"` 记录
- **THEN** load_history_smart 返回 `{"role": "tool", "tool_call_id": ..., "content": ...}` 格式消息
