## Context

`consolidator-last-consolidated` 引入了增量压缩和 `last_consolidated` 指针，但代码审查发现三个确定性 bug（to_keep 丢失、摘要非累计、阈值盲区）。本次改为**累计压缩**模式：每次 Consolidator 压缩 `history[:keep_from]` 的全部内容（含已有摘要前缀），生成的摘要是完整历史快照；同时将 `keep_from_cursor` 写入 summary 记录，使 Smart Load 能正确恢复 to_keep 消息。

## Goals / Non-Goals

**Goals:**
- 重启后 to_keep 消息不丢失（通过 `keep_from_cursor` 元数据）
- 每条 summary 是完整历史快照（累计压缩）
- 阈值计算包含完整 history（包括摘要前缀）
- 并发安全（per-chat-id asyncio.Lock）
- 原子持久化（只在 `append_summary` 成功后更新指针）

**Non-Goals:**
- 多轮 Consolidator（保持单轮）
- 精确 token 估算（继续用字符数近似）
- 旧 history.jsonl 文件的迁移（向后兼容，缺少 `keep_from_cursor` 的旧 summary 按兜底逻辑处理）

## Decisions

### D1：累计压缩 — `to_compress = history[:keep_from]`（含已有摘要前缀）

```python
# 修改前（增量）：
to_compress = history[last_consolidated:keep_from]  # 只压缩新内容

# 修改后（累计）：
to_compress = history[:keep_from]  # 压缩所有内容，包括旧摘要前缀
to_keep = history[keep_from:]
```

**理由**：每次 summary 成为完整快照，重启后只需最后一条 summary 即可恢复完整上下文。旧摘要前缀被重新 summarize 进新摘要，不会随重启丢失。

---

### D2：`keep_from_cursor` 写入 summary 记录

```python
# append_summary 写入格式：
{
  "cursor": N,
  "timestamp": "...",
  "role": "summary",
  "content": "...",
  "keep_from_cursor": <to_keep 中第一条消息的 cursor 值>
}
```

**理由**：to_keep 消息在 history.jsonl 中的 cursor 值小于 summary 的 cursor（因为 append_turn 先于 append_summary 执行），无法仅凭文件位置或 cursor 大小区分"to_keep"和"to_compress"的原始消息。`keep_from_cursor` 作为元数据精确标记了保留边界。

---

### D3：`load_history_smart` 基于 `keep_from_cursor` 加载

```python
def load_history_smart(chat_id):
    raw = _read_raw_entries(chat_id)
    
    # 找最后一条 summary 及其 keep_from_cursor
    last_summary_entry = None
    for e in raw:
        if e.get("role") == "summary":
            last_summary_entry = e
    
    if last_summary_entry is None:
        return convert_all(raw), 0
    
    keep_from_cursor = last_summary_entry.get("keep_from_cursor")
    summary_cursor = last_summary_entry["cursor"]
    
    messages = [convert_summary(last_summary_entry)]  # 摘要作为 prefix
    
    for e in raw:
        c = e.get("cursor", 0)
        role = e.get("role")
        if role == "summary":
            continue  # 跳过所有 summary（包括最后一条，已单独加载）
        if keep_from_cursor is not None and c >= keep_from_cursor:
            messages.append(convert(e))  # to_keep 消息（含 cursor < summary_cursor 的部分）
        elif keep_from_cursor is None and c > summary_cursor:
            messages.append(convert(e))  # 兜底：无元数据时只加载 summary 之后的
    
    return messages, 1
```

**理由**：`keep_from_cursor` 精确标记保留边界，无论消息在文件中的位置如何都能正确加载。兜底路径兼容无 `keep_from_cursor` 的旧 summary 记录。

---

### D4：阈值计算改为全量 `history`，`last_consolidated` 简化为 0/1

```python
# 修改后：
total_chars = self._estimate_chars(history)  # 包含摘要前缀
if total_chars < self.CHAR_THRESHOLD:
    return 0  # 无摘要前缀；或 1（有前缀但不触发）

# last_consolidated 只表示"是否有摘要前缀"：
# 0 = 无摘要，所有消息可压缩
# 1 = 有一条摘要前缀（累计模式下最多1条）
```

**理由**：累计压缩后，内存中最多只有1条 summary 前缀（每次压缩替换前一条），`last_consolidated` 的语义简化为"有无前缀"。全量 `_estimate_chars` 避免阈值盲区。

---

### D5：per-chat-id asyncio.Lock + 原子持久化

```python
self._locks: dict[str, asyncio.Lock] = {}

async def maybe_consolidate(self, chat_id, history):
    lock = self._locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        ...
        try:
            self._store.append_summary(chat_id, summary, keep_from_cursor=kfc)
        except Exception:
            logger.warning(...)
            return 0  # 不推进 last_consolidated
        return 1  # 只有持久化成功才返回 1
```

**理由**：对齐 spore 的 session-level 锁设计；原子持久化确保运行时状态和磁盘状态一致。

## Risks / Trade-offs

- **[Trade-off] 累计压缩调用 LLM 时输入更长**：to_compress 包含旧摘要前缀，摘要 prompt 更长 → 每次压缩代价略高。对于长期运行的会话这是可接受的，摘要质量也更好（LLM 能看到完整历史）。
- **[风险] keep_from_cursor 指向的条目可能不存在**：极端情况下（文件截断、手动编辑）cursor 找不到对应条目 → 兜底：找不到时加载全量原始消息，避免空历史。
- **[兼容性] 旧 summary 记录无 keep_from_cursor**：Smart Load 对旧记录使用 `cursor > summary_cursor` 的兜底路径，行为与旧版一致（仍有 Bug 1，但不影响已有功能）。

## Migration Plan

无需迁移。新格式向后兼容；旧 history.jsonl 继续可读，只是 Smart Load 对旧 summary 使用兜底逻辑（不含 to_keep 消息）。首次压缩后生成新格式 summary，后续重启即修复。
