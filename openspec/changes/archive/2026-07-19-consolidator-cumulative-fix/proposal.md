## Why

`consolidator-last-consolidated` 引入了 `last_consolidated` 指针机制，但代码审查发现设计存在三个确定性 bug，会在重启后导致数据丢失：

1. **to_keep 消息丢失**：Consolidator 先通过 `append_turn` 写入 to_keep 消息（低 cursor），再写入 summary（高 cursor）。`load_history_smart` 从 summary 的**文件位置**开始加载，to_keep 消息在前方被跳过。
2. **摘要非累计**：每次压缩只总结"本次新增内容"，不含此前的摘要前缀。重启后只加载最后一条 summary，更早摘要中的信息（用户身份、早期会话内容）永久丢失。
3. **阈值盲区**：`_estimate_chars(history[last_consolidated:])` 不计入摘要前缀，但 LLM 实际收到完整 history（含所有摘要），导致真实 prompt 大小无法被检测，上下文窗口可能溢出。

## What Changes

- 修改 `server/app/memory/consolidator.py`：`maybe_consolidate` 改为**累计压缩**（始终从 `history[0]` 到 `history[:keep_from]`），并在 summary 记录中写入 `keep_from_cursor` 元数据；添加 per-chat-id asyncio.Lock 防并发
- 修改 `server/app/memory/store.py`：`append_summary` 接受可选 `keep_from_cursor` 参数；`load_history_smart` 改为基于 `keep_from_cursor` 元数据加载 to_keep 消息
- 修改 `server/app/agent/loop.py`：`_last_consolidated` 简化为 0/1（有无摘要前缀），修复阈值计算为全量估算 `history`；`maybe_consolidate` 返回值只在 `append_summary` **成功后**更新指针（修复原子性）
- 删除 `server/app/memory/consolidator.py` 中的 `last_consolidated` 参数（改为内部逻辑推断）

## Capabilities

### Modified Capabilities

- `consolidator`: 累计压缩、keep_from_cursor 元数据、并发锁、原子持久化
- `memory-store`: `append_summary` 接受 `keep_from_cursor`；`load_history_smart` 基于元数据加载
- `agent-loop`: 简化 `_last_consolidated`，修复阈值计算

## Impact

- **修改文件**: `server/app/memory/consolidator.py`、`server/app/memory/store.py`、`server/app/agent/loop.py`
- **history.jsonl 格式**: summary 记录新增可选字段 `keep_from_cursor`，向后兼容（无该字段的旧记录按旧逻辑处理）
- **行为变化**: 重启后 to_keep 消息不再丢失；每条摘要是完整的历史快照；阈值计算包含所有消息
