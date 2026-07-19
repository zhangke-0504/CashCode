## Why

Agent 的"身份"（是谁、说话风格、工具使用规则）目前硬编码在 `loop.py` 的 `base_prompt` 字符串里，修改性格需要改代码。引入 SOUL.md 文件，将 Agent 人格与代码分离：用户编辑 `memory/SOUL.md` 即可调整 Agent 风格，无需重新部署。

## What Changes

- 修改 `server/app/memory/store.py`：新增 `read_soul()` 和 `write_soul()` 方法（参考已有的 `read_memory()` / `write_memory()`）
- 修改 `server/app/agent/loop.py`：`_handle_turn` 中将硬编码 `base_prompt` 替换为 `self._store.read_soul()`，无文件时回落默认值
- 新增 `server/memory/SOUL.md`：默认 Agent 人格文件，内含当前 `base_prompt` 内容和工具使用规则

## Capabilities

### New Capabilities

- `soul-md`: 文件驱动的 Agent 人格，用户可直接编辑 `memory/SOUL.md` 定制 Agent 风格，无需改代码

### Modified Capabilities

- `memory-store`: 新增 `read_soul`/`write_soul` 方法
- `agent-loop`: system prompt 从 SOUL.md 读取，提供默认值兜底

## Impact

- **新增文件**: `server/memory/SOUL.md`
- **修改文件**: `server/app/memory/store.py`、`server/app/agent/loop.py`
- **无破坏性变更**: SOUL.md 不存在时自动回落默认字符串，行为与当前完全一致
