## Context

`loop.py` 的 `_handle_turn` 里 `base_prompt` 是硬编码字符串。SOUL.md 的改动极小：加两个文件读写方法，一行替换 system prompt 构建逻辑，加一个默认文件。与已有的 `read_memory()`/`write_memory()` 完全对称。

## Goals / Non-Goals

**Goals:**
- `memory/SOUL.md` 不存在时行为与当前完全相同（字符串回落）
- `memory/SOUL.md` 存在时内容作为 system prompt 的第一段
- Dream 可通过已有的 `write_soul()` 更新 Agent 行为规则

**Non-Goals:**
- SOUL.md 的 git 版本控制
- Dream 自动更新 SOUL.md（Dream 的 prompt 可以选择性追加这一能力，不是本次范围）

## Decisions

### D1：`read_soul()` 路径与 `read_memory()` 对称

```
memory/MEMORY.md  ← read_memory() / write_memory()
memory/SOUL.md    ← read_soul()   / write_soul()
```

**理由**：统一放在 `base_dir`（`memory/`）下，与 spore 的 workspace 级文件对齐；方法签名与 `read_memory()` 完全一致，无需额外学习成本。

### D2：`_DEFAULT_SOUL` 模块级常量作为兜底

```python
# loop.py 模块级
_DEFAULT_SOUL = (
    "你是 CashCode，一个具备跨会话持久记忆能力的 AI 助手。..."
)

# _handle_turn 里
soul = self._store.read_soul() or _DEFAULT_SOUL
```

**理由**：不改变无 SOUL.md 时的行为，保持向后兼容；`_DEFAULT_SOUL` 作为文档也说明了 SOUL.md 应有的最小内容。

## Risks / Trade-offs

- **[Trade-off] SOUL.md 过长会占用上下文窗口** → 与 MEMORY.md 同理，用户自行控制长度；Consolidator 估算时包含在全量字符计算中（已修复）

## Migration Plan

无需迁移。新部署时 `memory/SOUL.md` 不存在即回落默认，首次使用无感知。
