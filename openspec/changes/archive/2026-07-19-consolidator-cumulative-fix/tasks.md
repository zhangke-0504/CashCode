## 1. MemoryStore：扩展 append_summary + 修复 load_history_smart

- [x] 1.1 修改 `append_summary(chat_id, summary, keep_from_cursor=None)` 签名：当 `keep_from_cursor` 不为 None 时，将其写入 summary 记录的 JSON 对象中（`"keep_from_cursor": <int>`）
- [x] 1.2 重写 `load_history_smart`：找到最后一条 summary 记录，读取其 `keep_from_cursor` 字段；若存在则加载 `cursor >= keep_from_cursor` 且非 summary 的所有条目作为 to_keep；若无 `keep_from_cursor` 字段则退回 `cursor > summary_cursor` 兜底路径；无 summary 则全量加载

## 2. Consolidator：改为累计压缩 + 并发锁 + 原子持久化

- [x] 2.1 在 `SimpleConsolidator.__init__` 中新增 `self._locks: dict[str, asyncio.Lock] = {}`
- [x] 2.2 修改 `maybe_consolidate` 方法体：字符估算改为 `self._estimate_chars(history)`（全量，不再排除前缀）
- [x] 2.3 修改压缩边界：`to_compress = history[:keep_from]`（含摘要前缀），`to_keep = history[keep_from:]`
- [x] 2.4 计算 `keep_from_cursor`：通过 `store.get_keep_from_cursor(chat_id, len(to_keep))` 从 history.jsonl 查询（内存消息无 cursor 字段，改为读文件推导）
- [x] 2.5 修改压缩后 history 重建：`history.clear(); history.append(summary_msg); history.extend(to_keep)`（无 prefix，累计模式每次只保留一条摘要）
- [x] 2.6 修改 `append_summary` 调用：传入 `keep_from_cursor=keep_from_cursor`
- [x] 2.7 修改返回值：`append_summary` 成功则返回 1，抛异常则返回 0（只有持久化成功才更新指针）
- [x] 2.8 在 `maybe_consolidate` 入口和出口用 `async with self._locks.setdefault(chat_id, asyncio.Lock()):` 包裹全部逻辑

## 3. AgentLoop：适配简化后的 last_consolidated 语义

- [x] 3.1 确认 `_last_consolidated` 的值只会是 0 或 1（不再累计），删除或注释旧注释中关于"随 prefix 数量增长"的描述
- [x] 3.2 确认 `maybe_consolidate` 调用方式无需改变（仍传 `last_consolidated`，接收返回值更新字典）

## 4. 验证

- [ ] 4.1 重启数据完整性：触发压缩后重启，验证重启后 to_keep 消息（如《行路难》）出现在内存历史中
- [ ] 4.2 累计摘要：触发两次压缩，第二次摘要应包含第一次摘要的内容（可通过日志或直接检查 summary 内容验证）
- [ ] 4.3 阈值正确性：有摘要前缀时，Consolidator 的 `total_chars` 日志应包含摘要字符数，不再只显示新消息字符数
- [ ] 4.4 keep_from_cursor 字段：压缩后检查 history.jsonl 最后一条 summary 记录包含 `keep_from_cursor` 字段，且值等于 to_keep 第一条消息的 cursor
