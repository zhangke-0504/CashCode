## Context

Step 1+2 建立了 per-chat-id 的历史持久化和 Consolidator 压缩。Dream 是记忆系统的第三层，在所有 chat_id 之上维护一个全局 MEMORY.md，并通过 system prompt 注入使 Agent 在每轮对话中自动携带长期记忆。参考 spore 的两阶段设计，但去掉 AgentRunner/文件工具等复杂依赖，改用两次普通 LLM 调用。

## Goals / Non-Goals

**Goals:**
- 定时扫描所有 chat_id 的未处理 history 条目，提炼事实写入全局 MEMORY.md
- 每轮对话前将 MEMORY.md 注入 system prompt，实现跨会话长期记忆
- dream cursor 跟踪各 chat_id 的处理进度，避免重复处理

**Non-Goals:**
- SOUL.md、USER.md（spore 有，CashCode 暂不实现）
- git auto-commit（spore 有，CashCode 暂不实现）
- per-line age annotation（需要 git blame，复杂度高）
- AgentRunner Phase 2（文件工具式手术编辑，改用直接 LLM 输出替代）
- 多用户隔离（当前为单用户场景）

## Decisions

### D1：MEMORY.md 和 dream cursor 放在全局级

```
memory/
├── MEMORY.md              ← 全局长期记忆（跨所有 chat_id）
├── .dream_cursor          ← JSON: {"<chat_id>": <last_cursor>, ...}
└── <chat_id>/
    ├── history.jsonl
    └── .cursor
```

**理由**：与 spore 的 workspace 级设计对齐；单用户场景下全局 MEMORY.md 是正确的作用域；JSON dream cursor 文件统一管理各 chat_id 的处理进度，比分散在各子目录更易于原子更新。

---

### D2：两阶段处理，Phase 2 用直接 LLM 输出替代 AgentRunner

```
Phase 1（分析）：
  输入：所有新history 条目 + 当前 MEMORY.md
  输出：分析报告（"有哪些值得新增/更新/删除的事实"）
  → 普通 LLM 调用

Phase 2（更新）：
  输入：Phase 1 分析报告 + 当前 MEMORY.md（完整）
  输出：完整的新 MEMORY.md 文本
  → 直接写入文件
```

**理由**：spore 的 Phase 2 用 AgentRunner + 文件工具，允许 LLM 做手术式编辑，但引入了大量复杂度（工具调用循环、错误处理等）。两次 LLM 调用的方案在内容量不大时（MEMORY.md < 2KB）效果等价，且实现简单。Phase 1 分析报告是 Phase 2 的关键：让 Phase 2 的 LLM 知道"要做什么"，而不是盲目地从头重写。

---

### D3：Dream cursor 使用 per-chat-id JSON 文件

dream cursor 格式：
```json
{"e567ca47-60aa-4ac7-9dfc-a12a3d45281e": 7, "713a9301-fb67-40cb-943f-4e4eab879420": 3}
```

Dream 运行时：
1. 扫描 `memory/` 下所有子目录（即所有 chat_id）
2. 对每个 chat_id：读取 `history.jsonl` 中 cursor > dream_cursor[chat_id] 的条目
3. 汇总所有新条目，按 timestamp 排序后送给 LLM

**理由**：per-chat-id cursor 避免重复处理；JSON 格式允许原子更新（单次写入）；扫描目录比维护 chat_id 注册表更简单。

---

### D4：system prompt 注入方式

```python
# loop.py _handle_turn 中，构建 messages 前：
messages = []
memory = self._store.read_memory()
if memory:
    messages.append({
        "role": "system",
        "content": f"你是一个AI助手，拥有持久记忆能力。\n\n## 长期记忆\n{memory}"
    })
messages.extend(history)
```

**理由**：DeepSeek-chat 支持 system role；MEMORY.md 为空时不注入（新部署无感知）；system prompt 只读取文件，不影响 Consolidator 的字符估算（history 里不含 system 消息）。

**注意**：Consolidator 的 `_estimate_chars` 只统计 history，不含 system prompt，这是正确的——system prompt 是固定开销，不应触发压缩。

---

### D5：Dream 触发间隔

```python
DREAM_INTERVAL_SECONDS = 300  # 5分钟，可通过 .env 配置
```

asyncio periodic task 在 `main.py` 的 lifespan 启动：
```python
dream_task = asyncio.create_task(dream_loop(dream, interval=300))
```

**理由**：5分钟足够及时，又不会频繁触发 LLM 调用；通过 `.env` 暴露配置，测试时可设为 30 秒。

## Risks / Trade-offs

- **[风险] Phase 2 整体替换可能丢失 MEMORY.md 中的已有内容** → Phase 1 明确分析"保留/修改/删除"，Phase 2 prompt 强调"保留已有内容，只做必要修改"；MEMORY.md 不大时风险低
- **[风险] Dream 运行时 LLM 调用失败** → 静默跳过本次 Dream（不更新 cursor），下次运行重试；不影响对话
- **[风险] 多个 chat 同时进行时 Dream 写 MEMORY.md 与 loop 读 MEMORY.md 存在竞态** → Python asyncio 单线程，读写不会真正并发；最坏情况是本轮读到旧版 MEMORY.md，可接受
- **[Trade-off] system prompt 每轮重新读取文件** → MEMORY.md 体积小（< 2KB），文件读取 < 1ms，可接受；未来可加内存缓存

## Migration Plan

无需迁移。`MEMORY.md` 不存在时 system prompt 正常工作（不注入记忆段），Dream 首次运行时自动创建。

## Open Questions

- Dream 的 system prompt（Phase 1/2 的 LLM 指令）用中文还是英文？建议中文，与用户场景一致。
- `DREAM_INTERVAL_SECONDS` 是否需要写入 `.env`？建议写入，方便测试时快速调整。
