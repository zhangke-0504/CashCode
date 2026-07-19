# search-tools

## Purpose

File search tools that allow the LLM agent to find files by name pattern and search file content using regular expressions.

## Requirements

### Requirement: GlobTool finds files by name pattern
`GlobTool` SHALL 接受 `pattern: str`（如 `**/*.py`）和可选 `path: str`，在 WORKSPACE_DIR 内按模式匹配文件名，返回匹配的相对路径列表（最多100条）。

#### Scenario: Pattern matches files
- **WHEN** LLM 调用 `glob(pattern="**/*.py")`
- **THEN** 返回工作目录下所有 .py 文件的相对路径列表

#### Scenario: No matches returns empty message
- **WHEN** 模式无匹配
- **THEN** 返回 "未找到匹配 <pattern> 的文件"

### Requirement: GrepTool searches file content
`GrepTool` SHALL 接受 `pattern: str`（正则）、可选 `path: str` 和 `file_pattern: str`（文件名过滤），在工作目录内搜索匹配内容，返回 `文件名:行号: 内容` 格式的结果（最多50条）。

#### Scenario: Content match found
- **WHEN** LLM 调用 `grep(pattern="import torch", file_pattern="*.py")`
- **THEN** 返回所有匹配行，格式为 `src/model.py:3: import torch`

#### Scenario: No matches
- **WHEN** 无文件包含匹配内容
- **THEN** 返回 "未找到匹配 <pattern> 的内容"
