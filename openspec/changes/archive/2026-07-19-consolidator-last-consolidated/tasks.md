## 1. MemoryStore：新增 load_history_smart

- [x] 1.1 在 `store.py` 中新增辅助方法 `_read_raw_entries(self, chat_id: str) -> list[dict]`：读取 history.jsonl 全量原始条目（不做 role 映射，直接返回 JSON 对象列表）；文件不存在返回空列表
- [x] 1.2 在 `store.py` 中实现 `load_history_smart(self, chat_id: str) -> tuple[list[dict[str, Any]], int]`：调用 `_read_raw_entries`，找到最后一条 `role: "summary"` 条目的位置；若存在则从该位置开始加载消息（`last_consolidated=1`），否则全量加载（`last_consolidated=0`）；role 映射规则与现有 `load_history()` 一致

## 2. Consolidator：增加 last_consolidated 参数

- [x] 2.1 修改 `maybe_consolidate` 签名：增加 `last_consolidated: int = 0` 参数，返回类型改为 `int`（原来是 `None`）
- [x] 2.2 修改字符估算逻辑：将 `self._estimate_chars(history)` 改为 `self._estimate_chars(history[last_consolidated:])`，阈值检查基于未压缩部分
- [x] 2.3 修改 `_find_keep_boundary` 调用：传入 `history[last_consolidated:]` 而非全量 `history`
- [x] 2.4 修改压缩后的 history 重建逻辑：`prefix = history[:last_consolidated]`；重建为 `prefix + [summary] + to_keep`；返回 `last_consolidated + 1`
- [x] 2.5 修改异常处理路径：所有 `return`（提前返回和异常跳过）均返回传入的 `last_consolidated` 原值

## 3. AgentLoop：集成 last_consolidated 追踪

- [x] 3.1 在 `loop.py` 的 `__init__` 中新增 `self._last_consolidated: dict[str, int] = {}`
- [x] 3.2 修改懒加载逻辑：将 `self._store.load_history(chat_id)` 改为调用 `load_history_smart(chat_id)`，解包 `(messages, lc)`，分别赋值给 `self._sessions[chat_id]` 和 `self._last_consolidated[chat_id]`
- [x] 3.3 修改 `maybe_consolidate` 调用：传入 `last_consolidated=self._last_consolidated.get(chat_id, 0)`，将返回值更新到 `self._last_consolidated[chat_id]`

## 4. 验证

- [ ] 4.1 手动测试重启场景：发消息触发 Consolidator（降低阈值），检查 history.jsonl 出现 summary；重启服务再发消息，观察日志确认 Consolidator **不**再触发（新消息字符数未超阈值），确认 `last_consolidated=1`
- [ ] 4.2 验证多次压缩不累积：连续触发两次 Consolidator，重启后检查日志中 `compress=N msgs` 只包含最后一次压缩以来的新消息，不含旧摘要
