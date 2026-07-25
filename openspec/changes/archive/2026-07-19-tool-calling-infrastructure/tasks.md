## 1. Tool 基础层

- [x] 1.1 创建 `server/app/agent/tools/__init__.py`（空文件）
- [x] 1.2 创建 `server/app/agent/tools/base.py`，实现 `Tool` 抽象基类：`name`、`description` 属性，`parameters() -> dict` 抽象方法，`to_openai_schema() -> dict` 默认实现，`async execute(**kwargs) -> str` 抽象方法
- [x] 1.3 创建 `server/app/agent/tools/memory.py`，实现 `SaveMemoryTool(Tool)`：`name="save_memory"`，参数 `content: str`；`execute` 读取 MEMORY.md → 去重检查 → 追加 `[timestamp] content` → 写回；返回确认或"已存在"提示

## 2. SimpleAgentRunner

- [x] 2.1 创建 `server/app/agent/runner.py`，定义 `SimpleAgentRunner` 类，类级常量 `MAX_ITERATIONS = 5`，构造参数：`client: AsyncOpenAI`、`model: str`、`on_tool_call: Callable` 和 `on_tool_result: Callable`（WS 通知回调）
- [x] 2.2 实现 `async run(messages, tools) -> tuple[str, list[dict]]`：循环非流式调用 LLM（`tools=schemas, tool_choice="auto"`）；无 tool_calls → 返回 `(final_text, updated_messages)`；有 tool_calls → 调用 `on_tool_call` → 执行工具 → 调用 `on_tool_result` → 追加 tool 消息 → 继续循环；超出 MAX_ITERATIONS 返回错误文本

## 3. MemoryStore 扩展

- [x] 3.1 在 `store.py` 中实现 `append_tool_turn(chat_id, user_content, tool_calls_msg, tool_results, final_reply)`：在一个 `open(..., "a")` 调用中依次写入 user、tool_calls、tool_result(s)、assistant 四类记录，cursor 连续自增；异常时不写入任何内容
- [x] 3.2 修改 `load_history_smart` 中的消息映射：`role: "tool_calls"` → `{"role": "assistant", "content": ..., "tool_calls": [...]}` ；`role: "tool"` → `{"role": "tool", "tool_call_id": ..., "content": ...}`
- [x] 3.3 修改 `_format_messages`（在 Consolidator 中）以兼容工具类消息：`role: "tool_calls"` 输出 `[TOOL_CALLS: tool_name]`，`role: "tool"` 输出 `[TOOL_RESULT: content]`，避免 Consolidator 崩溃

## 4. 集成 SimpleAgentLoop

- [x] 4.1 在 `loop.py` 中 import `SimpleAgentRunner`、`SaveMemoryTool`，`__init__` 中初始化：`self._tools = [SaveMemoryTool(self._store)]`；`self._runner = SimpleAgentRunner(self._client, self._model, on_tool_call=..., on_tool_result=...)`
- [x] 4.2 实现 WS 通知回调：`on_tool_call(chat_id, stream_id, tool_name)` → 发布 `{"_tool_call": True, "_tool_name": tool_name}` 事件；`on_tool_result(chat_id, stream_id, tool_name, result)` → 发布 `{"_tool_result": True, "_tool_name": tool_name, "_result": result}` 事件
- [x] 4.3 修改 `_handle_turn`：调用 `self._runner.run(messages_to_send, self._tools)` 获取 `(final_reply, updated_messages)`；若 updated_messages 含工具链，调用 `store.append_tool_turn`；否则调用现有 `store.append_turn`；将 updated_messages 中工具链相关部分同步到 `history`（in-memory）
- [x] 4.4 修改 system prompt：在 `base_prompt` 末尾追加工具使用说明："当用户明确要求记住某事时，立即调用 save_memory 工具"
- [x] 4.5 修改最终回复的输出：当使用 runner 时（非流式得到 final_reply），以 fake streaming 方式（整块发送一个 `_stream_delta` + `_stream_end`）或直接发布 `_turn_done`，不影响现有无工具流程

## 5. 验证

- [ ] 5.1 手动测试 SaveMemoryTool：告诉 Agent "帮我记住我叫张珂"，确认前端收到 `_tool_call` 和 `_tool_result` 事件，`memory/MEMORY.md` 出现新条目
- [ ] 5.2 验证跨轮次工具链：上一轮有工具调用，下一轮问"你上次记了什么" → LLM 能从 history 中看到 tool_calls 记录并准确回答
- [ ] 5.3 验证 history.jsonl 格式：工具调用后检查文件，应出现 `role: "tool_calls"` 和 `role: "tool"` 记录
- [ ] 5.4 验证无工具轮次不受影响：普通对话（LLM 未触发工具）仍走原有流式路径，无 `_tool_call` 事件
