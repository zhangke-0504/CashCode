# Spec: MemoryStore

## Purpose

`MemoryStore` 负责将对话历史以 JSONL 格式持久化到本地文件系统，并提供加载、追加和增量读取接口，支持服务重启后的会话恢复。

## Requirements

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

### Requirement: Append summary record to history file
`MemoryStore.append_summary` SHALL 接受可选参数 `keep_from_cursor: int | None = None`，当提供时将其写入 summary 记录的 `keep_from_cursor` 字段；该字段标记 to_keep 消息的起始 cursor 值，供 Smart Load 正确恢复 to_keep 消息。

#### Scenario: Summary record written with correct format
- **WHEN** 调用 `append_summary(chat_id, "用户询问了Python基础...")`
- **THEN** history.jsonl 追加一行，包含自增 cursor、当前时间戳、`role: "summary"` 和摘要内容

#### Scenario: Summary record written with keep_from_cursor metadata
- **WHEN** 调用 `append_summary(chat_id, "摘要内容", keep_from_cursor=11)`
- **THEN** history.jsonl 新增一行，包含 `"keep_from_cursor": 11` 字段

#### Scenario: Summary record without keep_from_cursor remains valid
- **WHEN** 调用 `append_summary(chat_id, "摘要内容")`（不传 keep_from_cursor）
- **THEN** history.jsonl 新增一行，不含 `keep_from_cursor` 字段，向后兼容

### Requirement: Load history on session resume
`MemoryStore.load_history` SHALL 在读取 history.jsonl 时，将 `role: "summary"` 的记录映射为 `{"role": "assistant", "content": "[历史摘要] <content>"}` 纳入返回列表；未知 role 的记录 SHALL 被跳过，不引发异常。

#### Scenario: Summary record mapped to assistant message on load
- **WHEN** history.jsonl 包含一条 `role: "summary"` 记录
- **THEN** `load_history` 返回列表中对应项为 `{"role": "assistant", "content": "[历史摘要] ..."}`

#### Scenario: Unknown role records skipped silently
- **WHEN** history.jsonl 包含 `role: "unknown_future_type"` 的记录
- **THEN** 该记录被跳过，不出现在返回列表中，不抛出异常

#### Scenario: History restored after restart
- **WHEN** 服务重启后收到已有 chat_id 的新消息
- **THEN** LLM 收到包含历史对话的完整 messages 列表，而非仅当前消息

#### Scenario: New chat_id starts with empty history
- **WHEN** 收到全新 chat_id 的首条消息，且无对应 history.jsonl 文件
- **THEN** 系统以空历史列表启动，正常处理

### Requirement: Smart load history starting from last consolidation boundary
`MemoryStore.load_history_smart` SHALL 优先使用最后一条 summary 记录的 `keep_from_cursor` 字段定位 to_keep 消息边界：加载该 summary 作为前缀，再加载所有 cursor >= `keep_from_cursor` 且非 summary 的条目作为 to_keep 消息；当 summary 无 `keep_from_cursor` 字段时，退回到加载 cursor > summary_cursor 的条目（兜底）。无 summary 时全量加载。

#### Scenario: Smart load uses keep_from_cursor to recover to_keep messages
- **WHEN** history.jsonl 含 cursor 9-10（被压缩）、cursor 11-12（to_keep）、cursor 13（summary，keep_from_cursor=11）
- **THEN** `load_history_smart()` 返回：[summary(cursor13), user(cursor11), assistant(cursor12)]，`last_consolidated=1`

#### Scenario: Fallback when no keep_from_cursor in summary
- **WHEN** history.jsonl 含 summary 记录但无 `keep_from_cursor` 字段
- **THEN** 加载 summary + cursor > summary_cursor 的条目，行为与修复前一致

#### Scenario: Full load when no summary exists
- **WHEN** history.jsonl 无任何 summary 记录
- **THEN** 返回全量消息列表，`last_consolidated=0`

### Requirement: Read unprocessed entries since cursor
系统 SHALL 提供 `read_unprocessed_history(since_cursor)` 接口，返回 cursor 值大于给定值的所有历史条目，供后续 Consolidator/Dream 增量处理。

#### Scenario: Returns only new entries
- **WHEN** 调用 `read_unprocessed_history(since_cursor=5)`，history.jsonl 包含 cursor 1-8
- **THEN** 仅返回 cursor 6、7、8 的条目

### Requirement: Read and write global MEMORY.md
`MemoryStore` SHALL 提供 `read_memory() -> str` 和 `write_memory(content: str) -> None` 方法，操作 `base_dir / "MEMORY.md"` 全局文件。`read_memory` 在文件不存在时返回空字符串。

#### Scenario: read_memory returns empty string when file absent
- **WHEN** `memory/MEMORY.md` 不存在
- **THEN** `read_memory()` 返回 `""`，不抛出异常

#### Scenario: write_memory creates or overwrites MEMORY.md
- **WHEN** 调用 `write_memory("用户叫张珂...")`
- **THEN** `memory/MEMORY.md` 被创建或覆写，内容为传入字符串

### Requirement: Read and write soul file
`MemoryStore` SHALL 提供 `read_soul() -> str` 和 `write_soul(content: str) -> None` 方法，操作 `base_dir / "SOUL.md"`；`read_soul` 在文件不存在时返回空字符串。

#### Scenario: read_soul returns empty string when file absent
- **WHEN** `memory/SOUL.md` 不存在
- **THEN** `read_soul()` 返回 `""`，不抛出异常

#### Scenario: write_soul creates or overwrites SOUL.md
- **WHEN** 调用 `write_soul("你是小码...")`
- **THEN** `memory/SOUL.md` 被创建或覆写，内容为传入字符串

### Requirement: Track dream cursor across all chat_ids
`MemoryStore` SHALL 提供 `get_dream_cursors() -> dict[str, int]` 和 `set_dream_cursors(cursors: dict[str, int]) -> None` 方法，操作 `base_dir / ".dream_cursor"` JSON 文件。不存在时返回空字典。

#### Scenario: get_dream_cursors returns empty dict when file absent
- **WHEN** `memory/.dream_cursor` 不存在
- **THEN** `get_dream_cursors()` 返回 `{}`

#### Scenario: set_dream_cursors persists cursor map
- **WHEN** 调用 `set_dream_cursors({"chat_A": 6, "chat_B": 3})`
- **THEN** `memory/.dream_cursor` 内容为对应 JSON，下次 `get_dream_cursors()` 返回同样的字典

### Requirement: List all chat_id directories
`MemoryStore` SHALL 提供 `list_chat_ids() -> list[str]` 方法，返回 `base_dir` 下所有子目录的名称（排除以 `.` 开头的隐藏目录）。

#### Scenario: Returns all chat_id subdirectories
- **WHEN** `memory/` 下有 `chat_A/`、`chat_B/` 和 `.dream_cursor` 文件
- **THEN** `list_chat_ids()` 返回 `["chat_A", "chat_B"]`，不包含文件或隐藏目录

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
