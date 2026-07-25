## Context

`SimpleAgentLoop` 当前以 `dict[str, list[dict]]` 形式在内存中维护对话历史，重启即丢。spore 的 `MemoryStore` 提供了完整的三层记忆系统（文件持久化 + Consolidator + Dream），CashCode Step 1 只复现其最底层：纯文件 I/O 层。

## Goals / Non-Goals

**Goals:**
- 对话历史持久化到 `history.jsonl`，重启后可恢复
- cursor 游标机制，支持后续 Consolidator/Dream 增量处理
- 与现有 `SimpleAgentLoop` 无缝集成，不改变 WS 通信协议

**Non-Goals:**
- Token 估算和上下文压缩（Step 2 Consolidator）
- MEMORY.md / SOUL.md 长期记忆文件（Step 3 Dream）
- Git 版本控制历史文件
- 多用户隔离或鉴权

## Decisions

### D1：存储路径按 chat_id 分目录

```
server/memory/
├── <chat_id>/
│   ├── history.jsonl   ← 对话历史，每行一条 JSON
│   └── .cursor         ← 最新 cursor 值
└── <chat_id>/
    └── ...
```

**理由**：与 spore 的 workspace-per-session 模式对齐，且为后续 per-chat MEMORY.md 预留扩展点。扁平单文件方案（所有会话混在一起）难以按 chat_id 查询和清理。

**备选**：全局单文件按 chat_id 字段过滤 —— 放弃，查询代价高，且 Dream 处理单元是 workspace 维度。

---

### D2：history.jsonl 格式与 spore 保持一致

每行记录：
```json
{"cursor": 1, "timestamp": "2026-07-18 10:00", "role": "user", "content": "..."}
{"cursor": 2, "timestamp": "2026-07-18 10:00", "role": "assistant", "content": "..."}
```

**理由**：加入 `role` 字段（spore 在 `_format_messages` 中也有 role），方便直接重建 OpenAI messages 格式。cursor 自增整数，`.cursor` 文件存最新值避免每次全量读取。

---

### D3：MemoryStore 作为纯同步 I/O 类

文件操作均为同步（`pathlib.Path.read_text` / `open(..., "a")`），不引入 `asyncio` 文件锁。

**理由**：每个 `chat_id` 有独立目录，不存在并发写冲突。Python 的 GIL 保证单进程下同一文件的 append 操作是安全的。引入 `aiofiles` 会增加复杂度，收益极低。

---

### D4：loop.py 集成方式 —— 懒初始化

`SimpleAgentLoop` 保留 `self._sessions` dict 作为运行时缓存，初始化时不预加载所有历史，而是在 `_handle_turn` 首次遇到某 `chat_id` 时从文件加载。

**理由**：chat 数量可能很多，全量预加载浪费内存。懒加载与现有 `setdefault` 模式吻合。

## Risks / Trade-offs

- **[风险] 进程崩溃时最后一条消息可能未写入** → jsonl append 是原子的（单行写入），最多丢失崩溃瞬间那条，可接受
- **[风险] history.jsonl 无限增长** → Step 2 Consolidator 会解决；Step 1 暂不限制，仅记录 cursor 供后续使用
- **[Trade-off] 同步 I/O 阻塞事件循环** → history append 发生在每轮 LLM 响应完成后，文件写入 < 1ms，实际影响可忽略

## Migration Plan

无需迁移。Step 1 是纯新增：
1. 部署后新对话自动持久化
2. 已有进程内存中的历史在重启后首次请求时从文件恢复（如文件不存在则视为新会话）

## Open Questions

- `memory/` 目录的根路径是否需要可配置（.env 中的 `MEMORY_DIR`）？当前方案硬编码为 `server/memory/`。
