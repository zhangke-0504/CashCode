## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop` 的会话历史 SHALL 通过 `MemoryStore` 持久化到文件，而非仅存于内存 dict。服务重启后，首次收到某 `chat_id` 的消息时，历史 SHALL 自动从文件恢复，LLM 调用行为与重启前一致。

#### Scenario: In-memory cache used for active session
- **WHEN** 同一 chat_id 在服务运行期间连续发送多条消息
- **THEN** 系统使用内存缓存（`self._sessions`），无需每轮重复读文件

#### Scenario: History loaded from file on cold start
- **WHEN** 服务重启后该 chat_id 第一次发送消息
- **THEN** `MemoryStore.load_history(chat_id)` 被调用，返回完整历史列表并填入内存缓存

#### Scenario: Turn written to file after completion
- **WHEN** 一轮 LLM 流式回复完成
- **THEN** `MemoryStore.append_turn(chat_id, user_content, assistant_content)` 被调用，两条记录写入 history.jsonl

#### Scenario: Failed turn does not persist
- **WHEN** LLM 调用抛出异常
- **THEN** 该轮的用户消息 SHALL NOT 被写入 history.jsonl（与现有内存回滚逻辑一致）
