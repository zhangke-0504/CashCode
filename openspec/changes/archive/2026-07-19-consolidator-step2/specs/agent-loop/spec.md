## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop` 的 `_handle_turn` SHALL 在每轮成功完成后，依次执行：持久化本轮对话（`store.append_turn`）→ 触发压缩检查（`consolidator.maybe_consolidate`）→ 发布 `_turn_done`。

#### Scenario: Consolidation runs after successful turn
- **WHEN** 一轮 LLM 流式回复完成
- **THEN** `consolidator.maybe_consolidate(chat_id, history)` 在 `append_turn` 之后、`_turn_done` 发布之前被调用

#### Scenario: Consolidation failure does not break turn
- **WHEN** `maybe_consolidate` 内部发生异常
- **THEN** 异常被捕获并记录日志，`_turn_done` 消息仍正常发布，对话不中断

#### Scenario: In-memory cache used for active session
- **WHEN** 同一 chat_id 在服务运行期间连续发送多条消息
- **THEN** 系统使用内存缓存（`self._sessions`），无需每轮重复读文件

#### Scenario: History loaded from file on cold start
- **WHEN** 服务重启后该 chat_id 第一次发送消息
- **THEN** `MemoryStore.load_history(chat_id)` 被调用，返回含摘要和近期对话的完整历史
