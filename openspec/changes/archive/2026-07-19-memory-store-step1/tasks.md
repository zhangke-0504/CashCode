## 1. MemoryStore 模块

- [x] 1.1 创建 `server/app/memory/__init__.py`（空文件，标记为包）
- [x] 1.2 创建 `server/app/memory/store.py`，实现 `MemoryStore` 类，包含：
  - `__init__(self, base_dir: Path)`：初始化 base_dir，不预建目录
  - `_chat_dir(self, chat_id: str) -> Path`：返回 `base_dir / chat_id`，按需创建
  - `_cursor_file(self, chat_id: str) -> Path`：返回 `.cursor` 文件路径
  - `_history_file(self, chat_id: str) -> Path`：返回 `history.jsonl` 文件路径
- [x] 1.3 实现 `MemoryStore._next_cursor(self, chat_id: str) -> int`：读取 `.cursor` 文件，返回 cursor+1；文件不存在则返回 1
- [x] 1.4 实现 `MemoryStore.append_turn(self, chat_id: str, user_content: str, assistant_content: str) -> None`：将 user 和 assistant 两条记录 append 到 `history.jsonl`，同步更新 `.cursor` 文件
- [x] 1.5 实现 `MemoryStore.load_history(self, chat_id: str) -> list[dict]`：读取 `history.jsonl`，返回 OpenAI messages 格式的列表 `[{"role": ..., "content": ...}]`；文件不存在返回空列表
- [x] 1.6 实现 `MemoryStore.read_unprocessed_history(self, chat_id: str, since_cursor: int) -> list[dict]`：返回 cursor > since_cursor 的所有条目（供 Step 2 Consolidator 使用）

## 2. 集成 SimpleAgentLoop

- [x] 2.1 在 `loop.py` 中 import `MemoryStore` 并在 `__init__` 初始化：`self._store = MemoryStore(Path("memory"))`
- [x] 2.2 修改 `_handle_turn`：首次遇到 `chat_id` 时调用 `load_history(chat_id)` 恢复历史，而非从空列表开始
- [x] 2.3 修改 `_handle_turn`：在成功完成一轮（`_turn_done` 发布之前）调用 `append_turn(chat_id, user_content, full_reply)`
- [x] 2.4 确认失败路径不写入文件：LLM 异常时 `append_turn` 不被调用（验证现有 `history.pop()` 逻辑位置正确）

## 3. 验证

- [ ] 3.1 手动测试：启动服务，发送几条消息，检查 `server/memory/<chat_id>/history.jsonl` 文件内容正确
- [ ] 3.2 手动测试重启恢复：重启服务后发送消息，确认 LLM 回复能引用上一次会话内容（说明历史已正确恢复）
- [ ] 3.3 验证 cursor 连续性：检查 `.cursor` 文件值与 `history.jsonl` 最后一条记录的 cursor 一致
