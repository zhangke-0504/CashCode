## ADDED Requirements

### Requirement: Append summary record to history file
`MemoryStore` SHALL 提供 `append_summary(chat_id, summary)` 方法，将单条摘要记录以 `role: "summary"` 类型写入 `history.jsonl`，cursor 自增，格式为 `{"cursor": N, "timestamp": "...", "role": "summary", "content": "..."}`.

#### Scenario: Summary record written with correct format
- **WHEN** 调用 `append_summary(chat_id, "用户询问了Python基础...")`
- **THEN** history.jsonl 追加一行，包含自增 cursor、当前时间戳、`role: "summary"` 和摘要内容

## MODIFIED Requirements

### Requirement: Load history on session resume
`MemoryStore.load_history` SHALL 在读取 history.jsonl 时，将 `role: "summary"` 的记录映射为 `{"role": "assistant", "content": "[历史摘要] <content>"}` 纳入返回列表；未知 role 的记录 SHALL 被跳过，不引发异常。

#### Scenario: Summary record mapped to assistant message on load
- **WHEN** history.jsonl 包含一条 `role: "summary"` 记录
- **THEN** `load_history` 返回列表中对应项为 `{"role": "assistant", "content": "[历史摘要] ..."}`

#### Scenario: Unknown role records skipped silently
- **WHEN** history.jsonl 包含 `role: "unknown_future_type"` 的记录
- **THEN** 该记录被跳过，不出现在返回列表中，不抛出异常

#### Scenario: History restored after restart
- **WHEN** 服务重启后该 chat_id 第一次发送消息
- **THEN** `load_history` 返回包含摘要和近期对话的完整 messages 列表

#### Scenario: New chat_id starts with empty history
- **WHEN** 收到全新 chat_id 的首条消息，且无对应 history.jsonl 文件
- **THEN** 系统以空历史列表启动，正常处理
