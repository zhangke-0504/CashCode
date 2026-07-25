## ADDED Requirements

### Requirement: Append conversation turn to history file
每轮对话结束后，系统 SHALL 将用户消息和助手回复分别以 JSONL 格式 append 到 `memory/<chat_id>/history.jsonl`，每行格式为 `{"cursor": <int>, "timestamp": "<YYYY-MM-DD HH:MM>", "role": "<user|assistant>", "content": "<text>"}`.

#### Scenario: Append user and assistant messages after turn
- **WHEN** 一轮对话完成（LLM 回复流式结束）
- **THEN** `history.jsonl` 中新增两行：role=user 和 role=assistant，cursor 各自自增

#### Scenario: Directory auto-created on first write
- **WHEN** 某 `chat_id` 首次写入历史
- **THEN** 系统自动创建 `memory/<chat_id>/` 目录，无需手动预建

### Requirement: Cursor auto-increment tracking
系统 SHALL 为每条历史记录分配单调递增的整数 cursor，并将最新 cursor 值持久化到 `memory/<chat_id>/.cursor` 文件，用于后续增量读取。

#### Scenario: Cursor increments on each append
- **WHEN** 连续 append 两条记录
- **THEN** 第二条记录的 cursor 值等于第一条加一

#### Scenario: Cursor survives restart
- **WHEN** 服务重启后继续对某 chat_id append 记录
- **THEN** 新记录的 cursor 值大于重启前最后一条记录的 cursor

### Requirement: Load history on session resume
系统 SHALL 在首次处理某 `chat_id` 的消息时，从 `history.jsonl` 读取全量历史并重建 OpenAI messages 格式（`[{"role": ..., "content": ...}]`）的列表，用于后续 LLM 调用。

#### Scenario: History restored after restart
- **WHEN** 服务重启后收到已有 chat_id 的新消息
- **THEN** LLM 收到包含历史对话的完整 messages 列表，而非仅当前消息

#### Scenario: New chat_id starts with empty history
- **WHEN** 收到全新 chat_id 的首条消息，且无对应 history.jsonl 文件
- **THEN** 系统以空历史列表启动，正常处理

### Requirement: Read unprocessed entries since cursor
系统 SHALL 提供 `read_unprocessed_history(since_cursor)` 接口，返回 cursor 值大于给定值的所有历史条目，供后续 Consolidator/Dream 增量处理。

#### Scenario: Returns only new entries
- **WHEN** 调用 `read_unprocessed_history(since_cursor=5)`，history.jsonl 包含 cursor 1-8
- **THEN** 仅返回 cursor 6、7、8 的条目
