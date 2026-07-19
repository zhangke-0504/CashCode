## Context

Step 1 完成了 `MemoryStore`（history.jsonl 持久化）和 `SimpleAgentLoop` 集成。当前 `self._sessions[chat_id]` 是完整的原始消息列表，无上限。DeepSeek-chat 支持 64K context，中文场景下字符数与 token 数近似 1:1，40K 字符约占 62.5% context，是合理的触发阈值。

## Goals / Non-Goals

**Goals:**
- 上下文字符总量超过阈值时，自动将旧消息压缩为摘要
- 压缩后内存历史保留最近约 50% 字符量的消息（与 spore Consolidator 目标一致）
- 摘要同时 append 到 history.jsonl（`role: "summary"`），供未来 Dream 使用
- `load_history` 支持 summary 记录，重启后能正确恢复压缩后的历史

**Non-Goals:**
- 精确 token 估算（不引入 tiktoken，用字符数近似）
- 并发锁（同一 chat_id 不会有并发写，单进程已安全）
- mid-turn 压缩（spore 有 AutoCompact，CashCode 不实现）
- 错误重试（摘要失败时跳过本次压缩，不影响对话）

## Decisions

### D1：触发时机 — 每轮成功后检查，不阻断主流程

```
_handle_turn 成功后：
  store.append_turn(...)
  await consolidator.maybe_consolidate(chat_id, history)  ← 新增
  publish _turn_done
```

**理由**：压缩发生在回复已发给用户之后，不影响本轮延迟。失败时静默跳过（记日志），不影响对话。

---

### D2：触发阈值 — 字符数近似，40K 触发，保留后 50%

```python
CHAR_THRESHOLD = 40_000
KEEP_RATIO     = 0.5

total_chars = sum(len(m["content"]) for m in history)
if total_chars < CHAR_THRESHOLD:
    return  # 不压缩

# 从后往前累计，找保留边界
keep_chars = 0
keep_from  = len(history)
for i in range(len(history) - 1, -1, -1):
    keep_chars += len(history[i]["content"])
    if keep_chars >= total_chars * KEEP_RATIO:
        keep_from = i
        break

# 确保 keep_from 落在 user 消息上（配对完整）
while keep_from < len(history) and history[keep_from]["role"] != "user":
    keep_from += 1
```

**理由**：比固定条数更自适应；50% 目标与 spore 对齐；从 user 消息边界切分确保 messages 配对完整。

---

### D3：摘要格式 — 注入为 `role: "assistant"` 带前缀

压缩后内存 history 变为：
```
[{"role": "assistant", "content": "[历史摘要] 用户询问了Python基础..."}]
[最近保留的消息...]
```

**理由**：LLM 不接受自定义 role，`assistant` 是唯一合法的"系统注入"角色（system prompt 已被 DeepSeek 占用）。加 `[历史摘要]` 前缀让 LLM 明白这是压缩内容，不是真实的助手回复。

---

### D4：history.jsonl 写入 — 新增 `append_summary`，`role: "summary"`

```json
{"cursor": N, "timestamp": "...", "role": "summary", "content": "摘要文本"}
```

`load_history` 遇到 `role: "summary"` 时映射为 `{"role": "assistant", "content": "[历史摘要] ..."}`，与内存中的格式保持一致。

**理由**：语义清晰，history.jsonl 中三种记录（user/assistant/summary）可区分；向后兼容（未知 role 跳过）。

---

### D5：Consolidator 不持有独立 LLM 客户端 — 由 loop 注入

```python
consolidator = SimpleConsolidator(
    client=self._client,  # 复用 loop 的 AsyncOpenAI 实例
    model=self._model,
    store=self._store,
)
```

**理由**：避免重复初始化客户端，保持单一连接池；与 spore Consolidator 接收 `provider` 注入的模式一致。

## Risks / Trade-offs

- **[风险] 摘要 LLM 调用增加延迟** → 压缩在 `_turn_done` 发布之后异步执行，用户已收到回复，无感知
- **[风险] 摘要质量差导致上下文语义丢失** → 不可完全避免，这是所有 summarization 方案的固有代价；加 `[历史摘要]` 前缀让 LLM 有一定预期
- **[风险] 压缩边界切到 summary 记录上** → `keep_from` 对齐 user 边界的逻辑需考虑 `role: "assistant"` 摘要注入的情况；实现时需特殊处理
- **[Trade-off] load_history 重建后摘要以 assistant 身份出现** → LLM 会看到"助手"说了一段"历史摘要"，语义略奇怪，但不影响实际对话质量

## Migration Plan

无需迁移。Consolidator 是纯增量功能，已有的 history.jsonl 文件不受影响，旧格式记录（无 summary）可正常加载。

## Open Questions

- 摘要 prompt 用中文还是英文指令？（建议中文，与用户语境一致）
- 是否需要通过 `.env` 暴露 `CHAR_THRESHOLD` 和 `KEEP_RATIO` 配置项？（可选，默认值足够）
