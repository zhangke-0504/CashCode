## 1. MemoryStore 扩展

- [x] 1.1 在 `store.py` 中实现 `read_soul(self) -> str`：读取 `base_dir / "SOUL.md"`，文件不存在时返回空字符串
- [x] 1.2 在 `store.py` 中实现 `write_soul(self, content: str) -> None`：写入 `base_dir / "SOUL.md"`（覆盖）

## 2. AgentLoop 改造

- [x] 2.1 在 `loop.py` 模块级定义 `_DEFAULT_SOUL` 常量（当前 `base_prompt` 字符串的内容）
- [x] 2.2 在 `_handle_turn` 中将 `base_prompt = "..."` 替换为 `soul = self._store.read_soul() or _DEFAULT_SOUL`，后续 system_content 拼接使用 `soul` 而非 `base_prompt`

## 3. 创建默认 SOUL.md

- [x] 3.1 创建 `server/memory/SOUL.md`，内容为当前 Agent 的默认身份和工具使用规则

## 4. 验证

- [ ] 4.1 编辑 `server/memory/SOUL.md`，将 Agent 改名为"小码"、调整说话风格，重启服务，确认 Agent 用新身份回复
- [ ] 4.2 删除 `server/memory/SOUL.md`，重启服务，确认 Agent 使用默认身份正常工作（兜底路径）
