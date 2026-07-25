## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop._handle_turn` SHALL 在有工具可用时，委托给 `SimpleAgentRunner` 执行 Phase 1 工具循环（非流式），再用 Phase 2 将最终回复以流式方式发给用户。持久化调用 `store.append_tool_turn`（含工具的轮次）或 `store.append_turn`（无工具的普通轮次）。`_handle_turn` SHALL 在 `_sessions[chat_id]` 中维护包含工具链消息的完整历史，确保下一轮 LLM 能看到本轮的工具调用记录。

#### Scenario: Tool call emits WS events before final streaming reply
- **WHEN** LLM 在 Phase 1 调用一次工具
- **THEN** 用户先收到 `_tool_call` WS 事件（含 tool_name），工具执行后收到 `_tool_result` 事件，最后收到流式最终回复

#### Scenario: Full tool chain in history for next turn
- **WHEN** 一轮含工具调用完成后，用户发起下一轮对话
- **THEN** 发往 LLM 的 messages 包含上一轮的 tool_calls 和 tool_result 消息，LLM 能看到自己上次的行为

#### Scenario: No tools available falls back to direct streaming
- **WHEN** 工具列表为空或 LLM 未返回 tool_calls
- **THEN** `_handle_turn` 直接使用流式 LLM 调用（现有行为），不经过 Runner

#### Scenario: Tool turn persisted atomically
- **WHEN** 工具循环完成，最终回复生成
- **THEN** `store.append_tool_turn` 原子写入完整工具链到 history.jsonl；失败时不写入任何内容（与现有 append_turn 失败行为一致）
