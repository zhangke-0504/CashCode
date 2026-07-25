## ADDED Requirements

### Requirement: Read and write global MEMORY.md
`MemoryStore` SHALL 提供 `read_memory() -> str` 和 `write_memory(content: str) -> None` 方法，操作 `base_dir / "MEMORY.md"` 全局文件。`read_memory` 在文件不存在时返回空字符串。

#### Scenario: read_memory returns empty string when file absent
- **WHEN** `memory/MEMORY.md` 不存在
- **THEN** `read_memory()` 返回 `""`，不抛出异常

#### Scenario: write_memory creates or overwrites MEMORY.md
- **WHEN** 调用 `write_memory("用户叫张珂...")`
- **THEN** `memory/MEMORY.md` 被创建或覆写，内容为传入字符串

### Requirement: Track dream cursor across all chat_ids
`MemoryStore` SHALL 提供 `get_dream_cursors() -> dict[str, int]` 和 `set_dream_cursors(cursors: dict[str, int]) -> None` 方法，操作 `base_dir / ".dream_cursor"` JSON 文件。不存在时返回空字典。

#### Scenario: get_dream_cursors returns empty dict when file absent
- **WHEN** `memory/.dream_cursor` 不存在
- **THEN** `get_dream_cursors()` 返回 `{}`

#### Scenario: set_dream_cursors persists cursor map
- **WHEN** 调用 `set_dream_cursors({"chat_A": 6, "chat_B": 3})`
- **THEN** `memory/.dream_cursor` 内容为对应 JSON，下次 `get_dream_cursors()` 返回同样的字典

### Requirement: List all chat_id directories
`MemoryStore` SHALL 提供 `list_chat_ids() -> list[str]` 方法，返回 `base_dir` 下所有子目录的名称（排除以 `.` 开头的隐藏目录）。

#### Scenario: Returns all chat_id subdirectories
- **WHEN** `memory/` 下有 `chat_A/`、`chat_B/` 和 `.dream_cursor` 文件
- **THEN** `list_chat_ids()` 返回 `["chat_A", "chat_B"]`，不包含文件或隐藏目录
