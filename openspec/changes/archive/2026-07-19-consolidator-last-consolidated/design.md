## Context

`SimpleConsolidator` 压缩触发后用 `history.clear() + extend` 替换内存列表，同时往 history.jsonl append 一条 `role: "summary"` 记录。重启时 `load_history()` 全量加载，导致已压缩的原始消息和摘要共存于内存，Consolidator 下次触发时重复压缩。spore 用 `session.last_consolidated`（int 指针）解决：只处理指针之后的消息。CashCode 因为 history.jsonl 是 append-only 且含有 summary 标记，可以从 summary 记录的位置推导出等价指针，无需额外持久化文件。

## Goals / Non-Goals

**Goals:**
- 重启后 Consolidator 只处理最后一次压缩以来的新消息
- `last_consolidated` 在运行时由 Smart Load 自动推导，不需要额外存储
- 压缩后 `last_consolidated` 单调递增，已压缩的 summary 前缀永不被重压

**Non-Goals:**
- 多轮 Consolidator（spore 最多5轮）—— 保持单轮
- 精确 token 估算 —— 继续用字符数近似
- 持久化 `last_consolidated` 到文件 —— 重启时从 history.jsonl 重新推导即可

## Decisions

### D1：Smart Load —— 从最后一条 summary 开始加载

```python
def load_history_smart(chat_id) -> tuple[list[dict], int]:
    all_entries = _read_raw_entries(chat_id)  # 全量读，不转换 role

    # 找最后一条 summary 的位置
    last_summary_pos = -1
    for i, e in enumerate(all_entries):
        if e.get("role") == "summary":
            last_summary_pos = i

    if last_summary_pos == -1:
        # 无 summary：全量加载，last_consolidated=0
        start = 0
        last_consolidated = 0
    else:
        # 从 summary 开始加载；summary 本身算作"已压缩"
        start = last_summary_pos
        last_consolidated = 1

    messages = convert_entries_to_messages(all_entries[start:])
    return messages, last_consolidated
```

**理由**：history.jsonl 里的 `role: "summary"` 就是天然的"压缩边界"标记，不需要额外文件；从最后一条 summary 开始加载，等价于 spore 的"从 last_consolidated 之后开始"。

---

### D2：`maybe_consolidate` 增加 `last_consolidated` 参数，返回新值

```python
async def maybe_consolidate(
    self,
    chat_id: str,
    history: list[dict],
    last_consolidated: int = 0,
) -> int:
    unconsolidated = history[last_consolidated:]
    total_chars = self._estimate_chars(unconsolidated)
    if total_chars < self.CHAR_THRESHOLD:
        return last_consolidated  # 无变化

    keep_from = self._find_keep_boundary(unconsolidated)
    to_compress = unconsolidated[:keep_from]
    to_keep = unconsolidated[keep_from:]

    if not to_compress:
        return last_consolidated

    summary = await self._summarize(to_compress)

    # 重建：[已压缩前缀] + [新 summary] + [保留]
    prefix = history[:last_consolidated]
    history.clear()
    history.extend(prefix)
    history.append({"role": "assistant", "content": f"[历史摘要] {summary}"})
    history.extend(to_keep)

    self._store.append_summary(chat_id, summary)
    return last_consolidated + 1  # 新 summary 也进入"已压缩"区
```

**理由**：与 spore 的 `session.last_consolidated = end_idx` 对齐；返回新值让 loop.py 更新状态。

---

### D3：loop.py 用 dict 追踪每个 chat_id 的 `last_consolidated`

```python
self._last_consolidated: dict[str, int] = {}

# 懒加载时：
if chat_id not in self._sessions:
    messages, lc = self._store.load_history_smart(chat_id)
    self._sessions[chat_id] = messages
    self._last_consolidated[chat_id] = lc

# 每轮结束后：
lc = await self._consolidator.maybe_consolidate(
    chat_id, history,
    last_consolidated=self._last_consolidated.get(chat_id, 0),
)
self._last_consolidated[chat_id] = lc
```

**理由**：in-memory dict，无需持久化；重启时通过 Smart Load 重新推导初始值，逻辑自洽。

## Risks / Trade-offs

- **[风险] 多条 summary 时只从最后一条开始加载** → 正确行为：每次压缩都应该从上次压缩边界开始，多条 summary 是多次历史压缩的累积，只需最新的边界
- **[Trade-off] 历史原始消息在重启后不可见** → Smart Load 不加载最后一条 summary 之前的原始消息，这与用户体验预期一致（压缩的目的就是丢弃细节）
- **[Trade-off] `load_history()` 旧签名保留** → 避免破坏 Dream 等现有调用方；Dream 仍用全量加载分析历史条目（Dream 读的是 raw history，不是 in-memory messages），两者互不干扰

## Migration Plan

无需迁移。已有 history.jsonl 文件保持不变；Smart Load 会自动从中找到最后一条 summary 作为边界，已有 `last_consolidated=0` 的会话等同于全量加载（无 summary 记录）。
