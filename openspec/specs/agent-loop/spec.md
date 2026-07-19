# Spec: SimpleAgentLoop

## Purpose

`SimpleAgentLoop` 负责处理单轮及多轮对话，通过 `MemoryStore` 将会话历史持久化，确保服务重启后会话状态可恢复。

## Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop._handle_turn` SHALL 在有工具可用时，委托给 `SimpleAgentRunner` 执行 Phase 1 工具循环（非流式），再用 Phase 2 将最终回复以流式方式发给用户。持久化调用 `store.append_tool_turn`（含工具的轮次）或 `store.append_turn`（无工具的普通轮次）。`_handle_turn` SHALL 在 `_sessions[chat_id]` 中维护包含工具链消息的完整历史，确保下一轮 LLM 能看到本轮的工具调用记录。

`SimpleAgentLoop._handle_turn` SHALL 在每轮调用 LLM 前始终注入一条 `role: "system"` 消息到 messages 列表最前面，其内容始终包含 Agent 的基础身份与持久记忆能力说明；当 `MemoryStore.read_memory()` 返回非空时，将 MEMORY.md 内容作为"已记住的信息"追加到该 system 消息中。history（当前会话消息列表）紧随 system 消息之后。

一轮对话成功完成后，`_handle_turn` SHALL 按 `append_turn` → `maybe_consolidate` → 发布 `_turn_done` 的顺序持久化并整理历史；LLM 调用失败时 SHALL 不持久化该轮，且从内存历史中回退刚追加的用户消息。

`SimpleAgentLoop._handle_turn` SHALL 在构建 system prompt 时，先调用 `self._store.read_soul()` 读取 SOUL.md 内容；若非空则使用其内容作为 Agent 身份段，否则使用 `_DEFAULT_SOUL` 内置字符串兜底。MEMORY.md 追加逻辑保持不变。

`SimpleAgentLoop` SHALL 维护 `_last_consolidated: dict[str, int]` 字典追踪每个 chat_id 的压缩边界，值仅为 0（无摘要前缀）或 1（有摘要前缀）。首次遇到某 chat_id 时 SHALL 调用 `MemoryStore.load_history_smart(chat_id)` 获取 `(messages, last_consolidated)`，并分别存入 `_sessions` 和 `_last_consolidated`。`_handle_turn` SHALL 向 `maybe_consolidate` 传入 `last_consolidated` 当前值，并将返回值直接更新到字典；`maybe_consolidate` 内部 `append_summary` 失败时返回 0，使 `_last_consolidated[chat_id]` 保持 0。

#### Scenario: Base identity always injected regardless of memory state
- **WHEN** 处理任意一轮对话
- **THEN** 发往 LLM 的 messages 第一条始终为 `role: "system"` 消息，其内容声明 Agent 是具备跨会话持久记忆能力的助手（即使 MEMORY.md 为空）

#### Scenario: MEMORY.md appended to system prompt when non-empty
- **WHEN** `memory/MEMORY.md` 存在且内容非空
- **THEN** system 消息内容为基础身份说明 + `## 你已经记住的信息\n<MEMORY.md内容>`，其后为 history

#### Scenario: Only base identity injected when MEMORY.md is empty
- **WHEN** `memory/MEMORY.md` 不存在或内容为空
- **THEN** system 消息只包含基础身份说明（不含记忆段落），其后为 history

#### Scenario: SOUL.md content used as system prompt base
- **WHEN** `memory/SOUL.md` 存在且内容非空
- **THEN** system prompt 基础段为 SOUL.md 内容，MEMORY.md（若有）追加在其后

#### Scenario: Default soul used when SOUL.md absent
- **WHEN** `memory/SOUL.md` 不存在或为空
- **THEN** 使用模块级 `_DEFAULT_SOUL` 常量，行为与当前完全一致

#### Scenario: Consolidator char estimate unaffected by system prompt
- **WHEN** Consolidator 调用 `_estimate_chars(history)` 估算上下文大小
- **THEN** 估算只统计 history 列表中的消息字符数，不包含 system prompt（system prompt 是固定开销，不触发压缩）

#### Scenario: In-memory cache used for active session
- **WHEN** 同一 chat_id 在服务运行期间连续发送多条消息
- **THEN** 系统使用内存缓存（`self._sessions`），无需每轮重复读文件

#### Scenario: Smart load used on first encounter of chat_id
- **WHEN** 服务重启后某 chat_id 第一次收到消息
- **THEN** 调用 `load_history_smart(chat_id)`，内存中的消息列表仅包含从最后一条 summary 开始的历史，`_last_consolidated[chat_id]` 被初始化为对应值

#### Scenario: Turn written to file after completion
- **WHEN** 一轮对话成功完成（LLM 正常返回完整回复）
- **THEN** `MemoryStore.append_turn(chat_id, user_content, full_reply)` 在发布 `_turn_done` 之前被调用，将本轮 user + assistant 落盘

#### Scenario: Failed turn does not persist
- **WHEN** LLM 调用抛出异常
- **THEN** `append_turn` 不被调用，刚追加的用户消息从内存历史中弹出，文件不被写入

#### Scenario: Consolidation runs after successful turn
- **WHEN** 一轮对话成功完成且 `append_turn` 已写入
- **THEN** `Consolidator.maybe_consolidate(chat_id, history)` 在发布 `_turn_done` 之前被调用

#### Scenario: last_consolidated updated after each successful consolidation
- **WHEN** `maybe_consolidate` 触发压缩并返回新值
- **THEN** `_last_consolidated[chat_id]` 更新为返回值，下次 Consolidator 检查时使用新边界

#### Scenario: last_consolidated unchanged when consolidation skipped
- **WHEN** `maybe_consolidate` 因字符数未超阈值返回原值
- **THEN** `_last_consolidated[chat_id]` 保持不变

#### Scenario: last_consolidated simplified to 0 or 1
- **WHEN** 内存中有一条 summary 前缀（累计模式下最多一条）
- **THEN** `_last_consolidated[chat_id] = 1`，不会积累到更大的值

#### Scenario: last_consolidated stays 0 when persistence fails
- **WHEN** `maybe_consolidate` 内部 `append_summary` 失败
- **THEN** 返回 0，`_last_consolidated[chat_id]` 不更新，下次仍从 0 开始尝试压缩

#### Scenario: Consolidation failure does not break turn
- **WHEN** `maybe_consolidate` 内部抛出异常
- **THEN** 异常被捕获、记录 warning，`_turn_done` 仍正常发布，主对话流程不中断

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
