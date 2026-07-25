## ADDED Requirements

### Requirement: Detect oversized context and trigger consolidation
系统 SHALL 在每轮对话成功完成后，检查该 chat_id 的内存历史总字符数。当总字符数超过 `CHAR_THRESHOLD`（40,000）时，SHALL 触发一次压缩流程。

#### Scenario: No consolidation when under threshold
- **WHEN** `sum(len(m["content"]) for m in history) < 40000`
- **THEN** `maybe_consolidate` 立即返回，不修改 history，不调用 LLM

#### Scenario: Consolidation triggered when over threshold
- **WHEN** 内存历史总字符数 >= 40,000
- **THEN** 系统触发压缩，调用 LLM 生成摘要，并替换内存历史中的旧消息

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
压缩成功后，系统 SHALL 调用 `store.append_summary(chat_id, summary)` 将摘要写入 history.jsonl，供未来 Dream 处理。

#### Scenario: Summary appended after successful consolidation
- **WHEN** LLM 摘要生成成功
- **THEN** history.jsonl 中新增一条 `{"cursor": N, "timestamp": "...", "role": "summary", "content": "..."}` 记录
