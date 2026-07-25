## Why

当前 `SimpleAgentLoop` 的对话历史完全存储在进程内存中（`self._sessions` dict），服务重启后所有会话上下文丢失，无法支持持续对话。需要引入文件持久化层，使对话历史在重启后可恢复。

## What Changes

- 新增 `server/app/memory/store.py`：`MemoryStore` 类，负责 `history.jsonl` 的读写和 cursor 管理
- 修改 `SimpleAgentLoop.__init__`：初始化时从文件恢复各 `chat_id` 的对话历史
- 修改 `SimpleAgentLoop._handle_turn`：每轮结束后将用户消息和助手回复 append 到 `history.jsonl`
- 对话历史按 `chat_id` 分目录存储：`memory/<chat_id>/history.jsonl`

## Capabilities

### New Capabilities

- `memory-store`: 文件持久化的对话历史存储，支持 append、读取、cursor 游标和 load_history 恢复

### Modified Capabilities

- `agent-loop`: `SimpleAgentLoop` 集成 `MemoryStore`，会话初始化和每轮消息写入行为变更

## Impact

- **新文件**: `server/app/memory/__init__.py`, `server/app/memory/store.py`
- **修改文件**: `server/app/agent/loop.py`
- **运行时依赖**: 无新增第三方依赖，仅使用标准库 `json`, `pathlib`, `datetime`
- **存储路径**: `server/memory/<chat_id>/history.jsonl`（相对于服务工作目录）
- **向前兼容**: 新 chat_id 首次连接时自动创建目录，不影响现有逻辑
