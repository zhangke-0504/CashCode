## MODIFIED Requirements

### Requirement: Detect oversized context and trigger consolidation
`SimpleConsolidator.maybe_consolidate` SHALL 使用**累计压缩**模式：`to_compress = history[:keep_from]`（包含任何已有摘要前缀），`to_keep = history[keep_from:]`；字符估算基于**全量 history**（不再排除摘要前缀）；`keep_from_cursor` 为 to_keep 第一条消息的 cursor 值（若能从 history 条目中获取），写入 `append_summary` 调用。方法签名移除 `last_consolidated` 参数，返回值仅表示是否有摘要前缀（0 或 1）。

#### Scenario: Cumulative compression includes existing summary prefix
- **WHEN** history 为 `[summary_old, user_A, assistant_A, user_B, assistant_B]`，keep_from=3
- **THEN** `to_compress = [summary_old, user_A, assistant_A]`（含旧摘要），LLM 摘要包含所有历史；新摘要替换旧摘要

#### Scenario: Full history used for threshold check
- **WHEN** history 有 1 条旧摘要前缀 + 2 条新消息，总字符 >= CHAR_THRESHOLD
- **THEN** 触发压缩，不会因旧摘要不计入而漏检

#### Scenario: keep_from_cursor written to summary record
- **WHEN** 压缩成功，to_keep 第一条消息有 cursor 字段（如 cursor=11）
- **THEN** `append_summary` 以 `keep_from_cursor=11` 调用，summary 记录含该元数据

#### Scenario: Pointer only advances on successful persistence
- **WHEN** `append_summary` 抛出异常
- **THEN** `maybe_consolidate` 返回 0（无摘要前缀状态），不返回 1，运行时状态与磁盘一致

### Requirement: Archive summary to history.jsonl
`SimpleConsolidator` SHALL 为每个 chat_id 维护一个 `asyncio.Lock`，确保同一 chat_id 的并发 `maybe_consolidate` 调用串行执行，防止重复压缩或指针竞争。

#### Scenario: Concurrent calls serialized per chat_id
- **WHEN** 同一 chat_id 的两个 `maybe_consolidate` 调用并发触发
- **THEN** 第二个调用等待第一个完成后才执行；不会基于相同旧状态重复压缩
