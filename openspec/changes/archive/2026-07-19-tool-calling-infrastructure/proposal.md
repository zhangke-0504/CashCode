## Why

当前 `SimpleAgentLoop` 是一个纯文字对话循环，LLM 无法主动执行操作（如保存记忆、搜索网页）。需要引入工具调用基础设施，使 LLM 能在对话中调用工具，同时满足三个要求：①用户通过 WS 事件实时感知工具调用过程；②完整工具链（tool_calls + tool_result）存入历史，确保跨轮次上下文连贯；③ history.jsonl 格式扩展以支持工具类消息，为未来添加更多工具提供标准路径。

## What Changes

- 新增 `server/app/agent/tools/base.py`：`Tool` 抽象基类，定义工具接口和 OpenAI schema 生成
- 新增 `server/app/agent/tools/memory.py`：`SaveMemoryTool`，LLM 主动追加事实到 MEMORY.md
- 新增 `server/app/agent/runner.py`：`SimpleAgentRunner`，非流式 ReAct 循环（工具调用阶段），每轮通过WS 发布 `_tool_call`/`_tool_result` 事件
- 修改 `server/app/memory/store.py`：新增 `append_tool_turn` 方法，将 tool_calls + tool_results + 最终回复写入 history.jsonl；`load_history_smart` 支持 tool_calls/tool 类型消息
- 修改 `server/app/agent/loop.py`：集成 `SimpleAgentRunner`，Phase 1 工具循环 + Phase 2 流式最终回复；system prompt 告知 LLM 可用工具

## Capabilities

### New Capabilities

- `tool-calling`: 基础 ReAct 循环，LLM 可调用工具，结果 WS 实时通知用户，完整链路存入历史
- `save-memory-tool`: LLM 主动将重要事实即时写入 MEMORY.md，无需等待 Dream 定时处理

### Modified Capabilities

- `memory-store`: 新增 `append_tool_turn` 方法，支持写入 tool_calls/tool/assistant 组合消息；`load_history_smart` 恢复工具类消息
- `agent-loop`: 集成工具调用阶段，支持 `_tool_call`/`_tool_result` WS 事件类型

## Impact

- **新增文件**: `server/app/agent/tools/__init__.py`、`server/app/agent/tools/base.py`、`server/app/agent/tools/memory.py`、`server/app/agent/runner.py`
- **修改文件**: `server/app/memory/store.py`、`server/app/agent/loop.py`
- **history.jsonl 格式扩展**: 新增 `role: "tool_calls"`（assistant 工具调用）和 `role: "tool"`（工具结果）两种记录类型，向后兼容
- **WS 协议扩展**: 新增 `_tool_call` 和 `_tool_result` metadata 类型，前端可选择性展示
- **API 调用模式变化**: 工具调用阶段使用非流式 API，最终回复仍流式；总调用次数可能增加（每次工具循环 +1 次）
