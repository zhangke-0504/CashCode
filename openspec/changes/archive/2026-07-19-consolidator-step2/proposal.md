## Why

Step 1 实现了对话历史的文件持久化，但 `self._sessions` 中的消息列表会随对话轮次无限增长，最终超过 LLM 的上下文窗口限制，导致 API 报错或响应质量下降。需要引入 Consolidator，在上下文过长时自动压缩旧消息。

## What Changes

- 新增 `server/app/memory/consolidator.py`：`SimpleConsolidator` 类，负责检测上下文长度、触发 LLM 摘要、替换内存历史
- 修改 `server/app/memory/store.py`：新增 `append_summary(chat_id, summary)` 方法，写入 `role: "summary"` 类型记录
- 修改 `server/app/memory/store.py`：修改 `load_history` 使其将 `role: "summary"` 记录映射为合法的 LLM messages 格式
- 修改 `server/app/agent/loop.py`：在每轮 `_handle_turn` 成功后调用 `consolidator.maybe_consolidate`

## Capabilities

### New Capabilities

- `consolidator`: 字符数触发的轻量上下文压缩，保留最近50%字符量的消息，其余通过 LLM 摘要后存入 history.jsonl

### Modified Capabilities

- `memory-store`: 新增 `append_summary` 方法和 `load_history` 对 summary 记录的处理逻辑
- `agent-loop`: `_handle_turn` 每轮成功后触发 Consolidator 检查

## Impact

- **新文件**: `server/app/memory/consolidator.py`
- **修改文件**: `server/app/memory/store.py`、`server/app/agent/loop.py`
- **运行时依赖**: 无新增第三方依赖；Consolidator 复用现有 `AsyncOpenAI` 客户端
- **API 调用增加**: 触发压缩时额外发起一次非流式 LLM 调用（summarization）
- **history.jsonl 格式扩展**: 新增 `role: "summary"` 记录类型，向后兼容（`load_history` 跳过无法识别的 role）
