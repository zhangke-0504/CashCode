## MODIFIED Requirements

### Requirement: Append summary record to history file
`MemoryStore.append_summary` SHALL 接受可选参数 `keep_from_cursor: int | None = None`，当提供时将其写入 summary 记录的 `keep_from_cursor` 字段；该字段标记 to_keep 消息的起始 cursor 值，供 Smart Load 正确恢复 to_keep 消息。

#### Scenario: Summary record written with keep_from_cursor metadata
- **WHEN** 调用 `append_summary(chat_id, "摘要内容", keep_from_cursor=11)`
- **THEN** history.jsonl 新增一行，包含 `"keep_from_cursor": 11` 字段

#### Scenario: Summary record without keep_from_cursor remains valid
- **WHEN** 调用 `append_summary(chat_id, "摘要内容")`（不传 keep_from_cursor）
- **THEN** history.jsonl 新增一行，不含 `keep_from_cursor` 字段，向后兼容

## MODIFIED Requirements

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
