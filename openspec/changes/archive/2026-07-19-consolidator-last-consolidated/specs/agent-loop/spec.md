## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop` SHALL 维护 `_last_consolidated: dict[str, int]` 字典追踪每个 chat_id 的压缩边界。首次遇到某 chat_id 时 SHALL 调用 `MemoryStore.load_history_smart(chat_id)` 获取 `(messages, last_consolidated)`，并分别存入 `_sessions` 和 `_last_consolidated`。每轮对话成功后 SHALL 将 `_last_consolidated[chat_id]` 更新为 `maybe_consolidate` 的返回值。

#### Scenario: Smart load used on first encounter of chat_id
- **WHEN** 服务重启后某 chat_id 第一次收到消息
- **THEN** 调用 `load_history_smart(chat_id)`，内存中的消息列表仅包含从最后一条 summary 开始的历史，`_last_consolidated[chat_id]` 被初始化为对应值

#### Scenario: last_consolidated updated after each successful consolidation
- **WHEN** `maybe_consolidate` 触发压缩并返回新值
- **THEN** `_last_consolidated[chat_id]` 更新为返回值，下次 Consolidator 检查时使用新边界

#### Scenario: last_consolidated unchanged when consolidation skipped
- **WHEN** `maybe_consolidate` 因字符数未超阈值返回原值
- **THEN** `_last_consolidated[chat_id]` 保持不变
