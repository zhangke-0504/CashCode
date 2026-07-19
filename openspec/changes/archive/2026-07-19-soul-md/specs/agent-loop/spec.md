## MODIFIED Requirements

### Requirement: Session history persisted across restarts
`SimpleAgentLoop._handle_turn` SHALL 在构建 system prompt 时，先调用 `self._store.read_soul()` 读取 SOUL.md 内容；若非空则使用其内容作为 Agent 身份段，否则使用 `_DEFAULT_SOUL` 内置字符串兜底。MEMORY.md 追加逻辑保持不变。

#### Scenario: SOUL.md content used as system prompt base
- **WHEN** `memory/SOUL.md` 存在且内容非空
- **THEN** system prompt 基础段为 SOUL.md 内容，MEMORY.md（若有）追加在其后

#### Scenario: Default soul used when SOUL.md absent
- **WHEN** `memory/SOUL.md` 不存在或为空
- **THEN** 使用模块级 `_DEFAULT_SOUL` 常量，行为与当前完全一致
