## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop` 的 `_last_consolidated` 字典值简化为 0（无摘要前缀）或 1（有摘要前缀），随 `load_history_smart` 返回值初始化，随 `maybe_consolidate` 返回值更新。`_handle_turn` 向 `maybe_consolidate` 传入 `last_consolidated`（无需再计算，返回值直接更新字典）；`maybe_consolidate` 返回值仅在 `append_summary` 成功后为 1，失败时为 0（修复原子性）。

#### Scenario: last_consolidated simplified to 0 or 1
- **WHEN** 内存中有一条 summary 前缀（累计模式下最多一条）
- **THEN** `_last_consolidated[chat_id] = 1`，不会积累到更大的值

#### Scenario: last_consolidated stays 0 when persistence fails
- **WHEN** `maybe_consolidate` 内部 `append_summary` 失败
- **THEN** 返回 0，`_last_consolidated[chat_id]` 不更新，下次仍从 0 开始尝试压缩
