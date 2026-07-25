## 1. MemoryStore 扩展

- [x] 1.1 在 `store.py` 中实现 `append_summary(self, chat_id: str, summary: str) -> None`：写入 `role: "summary"` 记录，格式与 `append_turn` 一致，cursor 自增
- [x] 1.2 修改 `load_history` 中的 role 映射逻辑：`role: "summary"` → `{"role": "assistant", "content": "[历史摘要] <content>"}`；未知 role 跳过（不抛出异常）

## 2. SimpleConsolidator 模块

- [x] 2.1 创建 `server/app/memory/consolidator.py`，定义 `SimpleConsolidator` 类，构造参数：`client: AsyncOpenAI`、`model: str`、`store: MemoryStore`；类级常量 `CHAR_THRESHOLD = 40_000`、`KEEP_RATIO = 0.5`
- [x] 2.2 实现 `_estimate_chars(self, history: list[dict]) -> int`：返回所有消息 content 的字符总数
- [x] 2.3 实现 `_find_keep_boundary(self, history: list[dict]) -> int`：从后往前累计字符，找到保留约 50% 字符量的边界索引；边界向后对齐至 `role: "user"` 消息
- [x] 2.4 实现 `_format_messages(self, messages: list[dict]) -> str`：将消息列表格式化为可读文本供 LLM 摘要（参考 spore 的 `_format_messages`：`[timestamp] ROLE: content`）
- [x] 2.5 实现 `async _summarize(self, messages: list[dict]) -> str`：非流式调用 LLM，system prompt 指示生成简洁摘要，返回摘要文本；失败时抛出异常
- [x] 2.6 实现 `async maybe_consolidate(self, chat_id: str, history: list[dict]) -> None`：整合上述方法——估算字符→未超阈值则返回→找边界→压缩消息→调用 `_summarize`→替换 history→`store.append_summary`；异常时记录 warning 并返回，不传播

## 3. 集成 SimpleAgentLoop

- [x] 3.1 在 `loop.py` 中 import `SimpleConsolidator`，`__init__` 中初始化：`self._consolidator = SimpleConsolidator(self._client, self._model, self._store)`
- [x] 3.2 在 `_handle_turn` 的 `store.append_turn(...)` 之后，`publish _turn_done` 之前，添加：`await self._consolidator.maybe_consolidate(chat_id, history)`，并用 `try/except` 包裹确保异常不中断主流程

## 4. 验证

- [ ] 4.1 手动测试：发送大量消息直到超过阈值，观察服务日志出现 `Consolidating` 相关日志，history 条数被压缩
- [ ] 4.2 验证对话连续性：压缩后继续对话，LLM 仍能基于摘要回答上下文相关问题
- [ ] 4.3 检查 history.jsonl：压缩后文件中出现 `role: "summary"` 记录
- [ ] 4.4 验证重启恢复：重启服务后发送消息，`load_history` 正确加载含摘要的历史，对话上下文不断裂
