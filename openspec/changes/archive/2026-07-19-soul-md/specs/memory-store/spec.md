## ADDED Requirements

### Requirement: Read and write soul file
`MemoryStore` SHALL 提供 `read_soul() -> str` 和 `write_soul(content: str) -> None` 方法，操作 `base_dir / "SOUL.md"`；`read_soul` 在文件不存在时返回空字符串。

#### Scenario: read_soul returns empty string when file absent
- **WHEN** `memory/SOUL.md` 不存在
- **THEN** `read_soul()` 返回 `""`，不抛出异常

#### Scenario: write_soul creates or overwrites SOUL.md
- **WHEN** 调用 `write_soul("你是小码...")`
- **THEN** `memory/SOUL.md` 被创建或覆写，内容为传入字符串
