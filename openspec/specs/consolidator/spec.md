# Spec: SimpleConsolidator

## Purpose

`SimpleConsolidator` 负责检测对话历史是否超过字符阈值，并在超过时通过 LLM 对旧消息进行摘要压缩，将压缩结果写入内存历史和持久化文件，以保持上下文窗口在可控范围内。

## Requirements

### Requirement: Detect oversized context and trigger consolidation
`SimpleConsolidator.maybe_consolidate` SHALL 使用**累计压缩**模式：`to_compress = history[:keep_from]`（包含任何已有摘要前缀），`to_keep = history[keep_from:]`；字符估算基于**全量 history**（不再排除摘要前缀）；`keep_from_cursor` 为 to_keep 第一条消息的 cursor 值（若能从 history 条目中获取），写入 `append_summary` 调用。方法签名移除 `last_consolidated` 参数，返回值仅表示是否有摘要前缀（0 或 1）。

#### Scenario: No consolidation when under threshold
- **WHEN** `sum(len(m["content"]) for m in history) < 40000`
- **THEN** `maybe_consolidate` 立即返回，不修改 history，不调用 LLM

#### Scenario: Consolidation triggered when over threshold
- **WHEN** 内存历史总字符数 >= 40,000
- **THEN** 系统触发压缩，调用 LLM 生成摘要，并替换内存历史中的旧消息

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

### Requirement: Preserve recent messages by character ratio
压缩时，系统 SHALL 从后往前累计字符数，保留总字符量约 50% 的最近消息（`KEEP_RATIO = 0.5`），其余旧消息作为压缩对象。

#### Scenario: Keep boundary aligns to user message
- **WHEN** 按字符比例计算的保留边界落在 `assistant` 消息上
- **THEN** 边界向后移动，直到对齐下一条 `user` 消息，确保保留的消息序列以 user 开头

#### Scenario: Nothing to compress when all messages are recent
- **WHEN** 按 50% 比例计算后，to_compress 列表为空
- **THEN** `maybe_consolidate` 不调用 LLM，直接返回

### Requirement: Summarize old messages via LLM
系统 SHALL 将待压缩的旧消息格式化后发送给 LLM，获取一段简洁的摘要文本。

#### Scenario: LLM summarization succeeds
- **WHEN** LLM 成功返回摘要内容
- **THEN** 内存 history 被替换为：`[{"role":"assistant","content":"[历史摘要] <summary>"}] + to_keep`

#### Scenario: LLM summarization fails
- **WHEN** LLM 调用抛出异常
- **THEN** 系统记录 warning 日志，跳过本次压缩，内存 history 保持不变，对话继续正常进行

### Requirement: Archive summary to history.jsonl
`SimpleConsolidator` SHALL 为每个 chat_id 维护一个 `asyncio.Lock`，确保同一 chat_id 的并发 `maybe_consolidate` 调用串行执行，防止重复压缩或指针竞争。

#### Scenario: Summary appended after successful consolidation
- **WHEN** LLM 摘要生成成功
- **THEN** history.jsonl 中新增一条 `{"cursor": N, "timestamp": "...", "role": "summary", "content": "..."}` 记录

#### Scenario: Concurrent calls serialized per chat_id
- **WHEN** 同一 chat_id 的两个 `maybe_consolidate` 调用并发触发
- **THEN** 第二个调用等待第一个完成后才执行；不会基于相同旧状态重复压缩
