## 1. MemoryStore 扩展

- [x] 1.1 在 `store.py` 中实现 `read_memory(self) -> str`：读取 `base_dir / "MEMORY.md"`，文件不存在时返回空字符串
- [x] 1.2 在 `store.py` 中实现 `write_memory(self, content: str) -> None`：写入 `base_dir / "MEMORY.md"`（覆盖）
- [x] 1.3 在 `store.py` 中实现 `get_dream_cursors(self) -> dict[str, int]`：读取 `base_dir / ".dream_cursor"` JSON 文件；不存在时返回 `{}`
- [x] 1.4 在 `store.py` 中实现 `set_dream_cursors(self, cursors: dict[str, int]) -> None`：将 cursor dict 写入 `base_dir / ".dream_cursor"`（JSON）
- [x] 1.5 在 `store.py` 中实现 `list_chat_ids(self) -> list[str]`：返回 `base_dir` 下所有非隐藏子目录名称

## 2. SimpleDream 模块

- [x] 2.1 创建 `server/app/memory/dream.py`，定义 `SimpleDream` 类，构造参数：`client: AsyncOpenAI`、`model: str`、`store: MemoryStore`；类级常量 `MAX_BATCH = 50`
- [x] 2.2 实现 `_collect_new_entries(self) -> list[dict]`：调用 `store.list_chat_ids()`，对每个 chat_id 调用 `store.read_unprocessed_history(chat_id, since_cursor=dream_cursors[chat_id])`，汇总并按 timestamp 排序
- [x] 2.3 实现 `_format_entries(self, entries: list[dict]) -> str`：格式化为 `[timestamp] ROLE: content` 多行文本供 LLM 分析
- [x] 2.4 实现 `async _phase1_analyze(self, entries_text: str, current_memory: str) -> str`：Phase 1 LLM 调用，system prompt 指示分析新增/更新/删除的事实，返回分析报告
- [x] 2.5 实现 `async _phase2_update(self, analysis: str, current_memory: str) -> str`：Phase 2 LLM 调用，system prompt 指示基于分析报告生成完整新 MEMORY.md，返回新内容
- [x] 2.6 实现 `async run(self) -> bool`：整合上述方法——收集新条目→若空返回 False→Phase 1→Phase 2→写入 MEMORY.md→更新 dream cursor；任一阶段异常时记录 warning 并返回 False

## 3. 集成 SimpleAgentLoop（system prompt 注入）

- [x] 3.1 在 `loop.py` 的 `_handle_turn` 中，构建 messages 前调用 `self._store.read_memory()`，若非空则在 messages 列表最前面插入 `{"role": "system", "content": f"你是一个AI助手，拥有持久记忆能力。\n\n## 长期记忆\n{memory}"}`

## 4. 集成 main.py（后台定时任务）

- [x] 4.1 在 `main.py` 的 lifespan 中初始化 `SimpleDream(client, model, store)`（复用 agent 的 client 和 model，或单独读取环境变量）
- [x] 4.2 在 lifespan 中添加 `dream_task = asyncio.create_task(dream_loop(dream))`；实现 `dream_loop` 协程：循环执行 `await dream.run()`，间隔 `int(os.getenv("DREAM_INTERVAL", "300"))` 秒
- [x] 4.3 在 lifespan 的 finally 块中取消并等待 `dream_task`

## 5. 验证

- [ ] 5.1 手动测试：与 Agent 对话并告知姓名/职业等信息，等待 Dream 运行（调低 `DREAM_INTERVAL=30` 便于测试），检查 `server/memory/MEMORY.md` 出现对应事实
- [ ] 5.2 验证跨会话记忆：重启服务，新开 chat_id，首条消息后确认 Agent 知道用户信息（来自 MEMORY.md 注入）
- [ ] 5.3 检查 `.dream_cursor` 文件：Dream 运行后内容为 JSON，各 chat_id 的 cursor 值正确推进
