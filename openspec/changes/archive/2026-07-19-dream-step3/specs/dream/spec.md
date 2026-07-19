## ADDED Requirements

### Requirement: Collect unprocessed history from all chat sessions
系统 SHALL 扫描 `memory/` 目录下所有 chat_id 子目录，读取各 chat_id 中 cursor 值大于 `.dream_cursor` 记录值的 history 条目，汇总为一个按 timestamp 排序的批次。

#### Scenario: New entries collected from multiple chat_ids
- **WHEN** `memory/chat_A/history.jsonl` 有 cursor 5-8 的新条目，`memory/chat_B/history.jsonl` 有 cursor 3-4 的新条目
- **THEN** Dream 收集到 5 条新条目（按 timestamp 排序），两个 chat_id 的 cursor 均被更新

#### Scenario: No new entries skips processing
- **WHEN** 所有 chat_id 的最新 cursor 均未超过 `.dream_cursor` 中的记录值
- **THEN** `SimpleDream.run()` 立即返回 False，不发起任何 LLM 调用

### Requirement: Two-phase LLM processing to update MEMORY.md
系统 SHALL 通过两次 LLM 调用更新全局 MEMORY.md：Phase 1 分析新历史条目产生变更报告，Phase 2 基于报告和当前 MEMORY.md 生成完整的新 MEMORY.md 内容并写入文件。

#### Scenario: Phase 1 produces analysis report
- **WHEN** Dream 收到一批新 history 条目
- **THEN** Phase 1 LLM 调用成功，返回包含"应新增/更新/删除哪些事实"的分析报告文本

#### Scenario: Phase 2 produces updated MEMORY.md
- **WHEN** Phase 1 分析报告已生成
- **THEN** Phase 2 LLM 调用成功，输出完整的新 MEMORY.md 文本，写入 `memory/MEMORY.md`

#### Scenario: Phase 1 failure aborts the run
- **WHEN** Phase 1 LLM 调用抛出异常
- **THEN** Dream 记录 warning 日志，不更新 MEMORY.md，不推进 dream cursor，返回 False

#### Scenario: Phase 2 failure preserves existing MEMORY.md
- **WHEN** Phase 2 LLM 调用抛出异常
- **THEN** 现有 MEMORY.md 保持不变，dream cursor 不推进，Dream 返回 False

### Requirement: Dream cursor tracks processing progress per chat_id
系统 SHALL 在每次成功完成 Dream 处理后，将本次批次中各 chat_id 的最新 cursor 值写入全局 `memory/.dream_cursor` 文件（JSON 格式），用于下次运行时跳过已处理条目。

#### Scenario: Cursor advances after successful run
- **WHEN** Dream 成功完成一次处理（Phase 1 + Phase 2 均成功）
- **THEN** `memory/.dream_cursor` 中各 chat_id 对应的 cursor 值更新为本批次最大值

#### Scenario: New chat_id automatically included
- **WHEN** 出现一个不在 `.dream_cursor` 中的新 chat_id
- **THEN** 该 chat_id 的 dream cursor 默认为 0，其所有历史条目均被视为未处理

### Requirement: Periodic background execution
系统 SHALL 在服务启动时创建一个 asyncio 后台任务，每隔 `DREAM_INTERVAL_SECONDS`（默认 300 秒，可通过环境变量配置）自动执行一次 `SimpleDream.run()`。

#### Scenario: Dream runs periodically while service is active
- **WHEN** 服务正常运行且距上次 Dream 运行已超过间隔时间
- **THEN** `SimpleDream.run()` 被自动调用，处理期间新积累的 history 条目

#### Scenario: Dream stops cleanly on service shutdown
- **WHEN** 服务收到关闭信号（lifespan 结束）
- **THEN** Dream 后台任务被 cancel，不影响正在进行的对话
