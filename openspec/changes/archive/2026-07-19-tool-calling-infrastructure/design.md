## Context

当前 `SimpleAgentLoop` 是无工具的纯对话循环。工具调用基础设施需要解决三个核心问题：①如何在不破坏流式 UX 的前提下执行工具；②如何将完整工具链持久化到 history.jsonl；③如何通过 WS 让用户实时感知工具执行。参考 spore 的 AgentRunner，但大幅简化（去掉收敛策略、工具审批、mid-turn 注入等）。

## Goals / Non-Goals

**Goals:**
- LLM 可在对话中发起工具调用，结果注入 messages 后继续生成最终回复
- 工具调用阶段通过 `_tool_call`/`_tool_result` WS 事件实时通知前端
- tool_calls + tool_result + 最终回复作为一个原子单元写入 history.jsonl
- `load_history_smart` 支持从包含工具类消息的历史中恢复，保持上下文连贯
- `SaveMemoryTool`：首个工具实现，LLM 主动触发时即时写入 MEMORY.md

**Non-Goals:**
- 工具审批（用户授权） — spore 有，CashCode 暂不实现
- mid-turn 用户注入 — 复杂，后期可选
- 工具调用阶段的流式输出（先非流式工具循环，再流式最终回复）
- 文件系统工具（ReadFileTool、EditFileTool）— 需要 workspace 概念，本次不做
- Option B 完整历史中工具消息的 Consolidator 压缩优化 — 当前 Consolidator 遇到 tool_calls/tool 消息时，将其格式化为文本纳入压缩，不做特殊处理

## Decisions

### D1：两阶段执行 — 工具循环非流式 + 最终回复流式

```
Phase 1: SimpleAgentRunner（非流式 ReAct 循环）
  LLM(messages + tools) → tool_calls?
    Yes: emit _tool_call WS → execute → emit _tool_result WS → append → repeat
    No:  return final_text

Phase 2: SimpleAgentLoop（流式）
  final_text 以 stream_delta 形式发给用户
  （fake streaming: 按字切分 or 直接 _turn_done）
```

**理由**：工具调用 + streaming 同时处理需要 buffer delta chunks 并检测 tool_call 边界，极其复杂。两阶段分离简单且 UX 可接受：工具执行期间前端收到 `_tool_call` 事件，用户感知到"正在执行"；最终回复仍有流式输出感。

---

### D2：history.jsonl 新增两种 role 类型

```
role: "tool_calls"   ← assistant 调用工具的消息（含 tool_calls 数组）
role: "tool"         ← 工具返回结果的消息（含 tool_call_id）
```

一轮含工具调用的对话在 history.jsonl 中的记录：
```jsonl
{"cursor":N,   "role":"user",       "content":"记住我叫张珂"}
{"cursor":N+1, "role":"tool_calls", "content":"[save_memory]", "tool_calls":[...]}
{"cursor":N+2, "role":"tool",       "content":"已保存：...", "tool_call_id":"call_xxx"}
{"cursor":N+3, "role":"assistant",  "content":"好的，已经记住啦！"}
```

**理由**：完整工具链存入历史，LLM 下一轮能看到自己上次做了什么，保持行为连贯。`content` 字段保留文本摘要，方便 Consolidator 纳入压缩（不需要特殊处理）。

---

### D3：`append_tool_turn` — 原子写入整轮工具链

```python
def append_tool_turn(
    self,
    chat_id: str,
    user_content: str,
    tool_calls_msg: dict,        # assistant msg with tool_calls
    tool_results: list[dict],    # list of tool result msgs
    final_reply: str,
) -> None:
```

**理由**：工具调用链是一个逻辑单元，必须原子写入（要么全写，要么全不写），防止部分写入导致历史格式损坏。失败时不写入任何内容（类似现有 append_turn 的失败处理）。

---

### D4：`load_history_smart` 恢复工具类消息

```python
role: "tool_calls"  → {"role": "assistant", "content": msg["content"], "tool_calls": msg["tool_calls"]}
role: "tool"        → {"role": "tool", "tool_call_id": msg["tool_call_id"], "content": msg["content"]}
```

**理由**：DeepSeek 兼容 OpenAI 工具调用格式，直接恢复原始格式传入 API 即可。

---

### D5：`SaveMemoryTool` 简化版（参考 spore）

```python
async def execute(self, content: str, category: str = "memory") -> str:
    existing = self._store.read_memory()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"[{ts}] {content.strip()}"
    if entry in existing:
        return "该信息已存在，无需重复保存。"
    new_memory = existing.rstrip("\n") + "\n" + entry + "\n"
    self._store.write_memory(new_memory)
    return f"已保存到长期记忆：{content.strip()}"
```

去掉 spore 的 `scope`/`confidence`/project 概念，CashCode 当前单用户场景无需这些。

---

### D6：System prompt 告知 LLM 工具存在

```python
base_prompt = (
    "你是 CashCode，一个具备跨会话持久记忆能力的 AI 助手。...\n\n"
    "## 可用工具\n"
    "- save_memory：当用户明确要求记住某事，或你判断某信息对未来对话有价值时，"
    "立即调用此工具将其保存到长期记忆。不要对临时性闲聊内容使用此工具。"
)
```

## Risks / Trade-offs

- **[风险] Consolidator 遇到 tool_calls/tool 消息格式不兼容** → `_format_messages` 对 tool_calls role 特殊处理：输出 `[TOOL: save_memory]` 文本摘要，不崩溃
- **[风险] fake streaming（直接发全文）UX 比真实流式差** → 可接受；工具执行结束到最终回复之间已有 _tool_result 事件填充等待感
- **[Trade-off] append_tool_turn 原子写入失败时内存历史已更新** → 失败时记录 warning，不回滚内存（与现有 append_turn 失败行为一致）

## Migration Plan

history.jsonl 中的旧记录格式（user/assistant/summary/tool）完全兼容：`load_history_smart` 遇到 tool_calls/tool 类型时恢复为原始格式；遇到旧格式（无这些类型）时行为不变。
