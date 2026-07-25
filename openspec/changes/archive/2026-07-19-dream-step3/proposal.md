## Why

Step 1+2 实现了对话历史的持久化和上下文压缩，但记忆仍局限于单个 chat_id。不同会话之间完全隔离——用户在一个对话中说的"我叫张珂，是前端工程师"，在新开的对话里 Agent 完全不知道。需要引入 Dream：定时从所有会话历史中提炼长期记忆，写入全局 MEMORY.md，并在每轮对话的 system prompt 中注入，使 Agent 具备跨会话的持久记忆能力。

## What Changes

- 新增 `server/app/memory/dream.py`：`SimpleDream` 类，两阶段 LLM 处理（分析 → 更新 MEMORY.md）
- 修改 `server/app/memory/store.py`：新增 `read_memory()`、`write_memory()`、dream cursor 读写方法（全局级，不再是 per-chat-id）
- 修改 `server/app/agent/loop.py`：每轮对话前将 MEMORY.md 内容注入 system prompt
- 修改 `server/main.py`：在 lifespan 中启动 Dream 后台定时任务（asyncio periodic task）

## Capabilities

### New Capabilities

- `dream`: 定时两阶段 LLM 处理器，读取跨 chat_id 的未处理 history 条目，提炼事实写入全局 MEMORY.md

### Modified Capabilities

- `memory-store`: 新增全局级 MEMORY.md 读写和 dream cursor 跟踪方法
- `agent-loop`: 每轮对话前从 MEMORY.md 读取长期记忆并注入 system prompt

## Impact

- **新文件**: `server/app/memory/dream.py`
- **修改文件**: `server/app/memory/store.py`、`server/app/agent/loop.py`、`server/main.py`
- **新增存储**: `server/memory/MEMORY.md`（全局）、`server/memory/.dream_cursor`（JSON，记录各 chat_id 的处理进度）
- **API 调用增加**: Dream 每次运行时额外进行 2 次非流式 LLM 调用（Phase 1 分析 + Phase 2 生成）
- **无破坏性变更**: MEMORY.md 不存在时 system prompt 正常工作（空记忆场景）
