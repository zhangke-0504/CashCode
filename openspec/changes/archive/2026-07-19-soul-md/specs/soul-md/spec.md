## ADDED Requirements

### Requirement: Agent identity defined by SOUL.md file
`memory/SOUL.md` SHALL 作为 Agent 的人格定义文件，包含：身份描述、说话风格、工具使用规则。用户可直接编辑此文件调整 Agent 风格，无需修改代码。文件不存在时 Agent 使用内置默认身份。

#### Scenario: SOUL.md present and used as identity
- **WHEN** `memory/SOUL.md` 存在且内容非空
- **THEN** system prompt 第一段为 SOUL.md 内容，而非硬编码字符串

#### Scenario: Default identity used when SOUL.md absent
- **WHEN** `memory/SOUL.md` 不存在
- **THEN** system prompt 使用 `_DEFAULT_SOUL` 默认字符串，行为与修改前完全一致
