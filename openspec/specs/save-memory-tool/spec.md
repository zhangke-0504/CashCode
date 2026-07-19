# Spec: SaveMemoryTool

## Purpose

TBD — `SaveMemoryTool` 是一个 LLM 可调用的工具，用于将有长期价值的信息持久化到全局 `memory/MEMORY.md`，并在后续对话中自动注入 system prompt，实现跨会话记忆。

## Requirements

### Requirement: SaveMemoryTool saves facts to MEMORY.md immediately
`SaveMemoryTool` SHALL 接受 `content: str` 参数，将其以 `[timestamp] content` 格式追加到全局 `memory/MEMORY.md`；若内容已存在则跳过（去重）；执行成功返回确认文字，失败返回错误说明。触发条件：用户明确要求记住某事，或 LLM 判断该信息对未来对话有长期价值。

#### Scenario: New fact appended to MEMORY.md
- **WHEN** LLM 调用 `save_memory(content="用户叫张珂，是 Python 工程师")`
- **THEN** `memory/MEMORY.md` 末尾追加 `[2026-07-19 14:30] 用户叫张珂，是 Python 工程师`，返回 `"已保存到长期记忆：..."`

#### Scenario: Duplicate content skipped
- **WHEN** LLM 调用 `save_memory` 且该内容已存在于 MEMORY.md
- **THEN** 不重复写入，返回 `"该信息已存在，无需重复保存。"`

#### Scenario: Memory injected into next turn's system prompt
- **WHEN** SaveMemoryTool 写入成功后，用户发起新一轮对话
- **THEN** 该条新事实出现在 system prompt 的 `## 你已经记住的信息` 段落中（因为 `loop.py` 每轮读取 MEMORY.md）
