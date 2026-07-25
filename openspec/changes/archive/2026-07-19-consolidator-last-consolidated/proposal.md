## Why

当前 `SimpleConsolidator` 在压缩旧消息后，重启服务时 `load_history()` 会从 history.jsonl 加载**全量**历史，导致已经被压缩过的原始消息和摘要记录同时进入内存。下次 Consolidator 触发时会把摘要本身再压一遍，产生"摘要套摘要"的信息损失。参考 spore 的 `session.last_consolidated` 指针机制，引入 Smart Load 解决这一问题。

## What Changes

- 修改 `server/app/memory/store.py`：新增 `load_history_smart(chat_id)` 方法，从 history.jsonl 中最后一条 `role: "summary"` 记录开始加载，并返回 `(messages, last_consolidated)` 元组；无 summary 时全量加载，`last_consolidated=0`
- 修改 `server/app/memory/consolidator.py`：`maybe_consolidate` 增加 `last_consolidated` 参数，只对 `history[last_consolidated:]` 估算字符/找边界/压缩，返回更新后的 `last_consolidated` 值
- 修改 `server/app/agent/loop.py`：新增 `self._last_consolidated: dict[str, int]` 字典，在懒加载时使用 `load_history_smart()`，每轮更新 `_last_consolidated[chat_id]`

## Capabilities

### New Capabilities

- `consolidator-last-consolidated`: Smart Load + last_consolidated 指针机制，防止已压缩内容被重复压缩

### Modified Capabilities

- `memory-store`: 新增 `load_history_smart` 方法
- `consolidator`: `maybe_consolidate` 签名变更，增加 `last_consolidated` 参数，返回更新后的值
- `agent-loop`: 集成 `last_consolidated` 状态追踪

## Impact

- **修改文件**: `server/app/memory/store.py`、`server/app/memory/consolidator.py`、`server/app/agent/loop.py`
- **无破坏性变更**: `load_history()` 保留原签名，新增 `load_history_smart()` 作为增量接口
- **行为变化**: 重启后 Consolidator 只压缩最后一次压缩以来的新消息，不再重压旧摘要
