## ADDED Requirements

### Requirement: Smart load history starting from last consolidation boundary
`MemoryStore` SHALL 提供 `load_history_smart(chat_id) -> tuple[list[dict], int]` 方法：扫描 history.jsonl 中所有条目，找到最后一条 `role: "summary"` 记录的位置；若存在则从该位置开始加载（返回 `last_consolidated=1`），否则全量加载（返回 `last_consolidated=0`）。`role: "summary"` 映射为带 `[历史摘要]` 前缀的 assistant 消息，其他 role 映射规则与现有 `load_history()` 一致。

#### Scenario: Smart load starts from last summary when one exists
- **WHEN** history.jsonl 包含 cursor 1-4（原始对话）和 cursor 7（summary）和 cursor 8-9（新对话）
- **THEN** `load_history_smart()` 返回从 cursor 7 开始的 3 条消息，且 `last_consolidated=1`

#### Scenario: Smart load returns full history when no summary exists
- **WHEN** history.jsonl 只包含原始 user/assistant 条目，无 summary 记录
- **THEN** `load_history_smart()` 返回全量消息列表，且 `last_consolidated=0`

#### Scenario: Multiple summaries use the last one as boundary
- **WHEN** history.jsonl 包含 cursor 7（first summary）和 cursor 14（second summary）和新对话
- **THEN** `load_history_smart()` 从 cursor 14 开始加载，`last_consolidated=1`
