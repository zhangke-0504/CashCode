## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop._handle_turn` SHALL 在每轮调用 LLM 前始终注入一条 `role: "system"` 消息到 messages 列表最前面，其内容始终包含 Agent 的基础身份与持久记忆能力说明；当 `MemoryStore.read_memory()` 返回非空时，将 MEMORY.md 内容作为"已记住的信息"追加到该 system 消息中。history（当前会话消息列表）紧随 system 消息之后。

#### Scenario: Base identity always injected regardless of memory state
- **WHEN** 处理任意一轮对话
- **THEN** 发往 LLM 的 messages 第一条始终为 `role: "system"` 消息，其内容声明 Agent 是具备跨会话持久记忆能力的助手（即使 MEMORY.md 为空）

#### Scenario: MEMORY.md appended to system prompt when non-empty
- **WHEN** `memory/MEMORY.md` 存在且内容非空
- **THEN** system 消息内容为基础身份说明 + `## 你已经记住的信息\n<MEMORY.md内容>`，其后为 history

#### Scenario: Only base identity injected when MEMORY.md is empty
- **WHEN** `memory/MEMORY.md` 不存在或内容为空
- **THEN** system 消息只包含基础身份说明（不含记忆段落），其后为 history

#### Scenario: Consolidator char estimate unaffected by system prompt
- **WHEN** Consolidator 调用 `_estimate_chars(history)` 估算上下文大小
- **THEN** 估算只统计 history 列表中的消息字符数，不包含 system prompt（system prompt 是固定开销，不触发压缩）

#### Scenario: In-memory cache used for active session
- **WHEN** 同一 chat_id 在服务运行期间连续发送多条消息
- **THEN** 系统使用内存缓存（`self._sessions`），无需每轮重复读文件

#### Scenario: History loaded from file on cold start
- **WHEN** 服务重启后该 chat_id 第一次发送消息
- **THEN** `MemoryStore.load_history(chat_id)` 被调用，返回含摘要和近期对话的完整历史
