# filesystem-tools

## Purpose

File system tools that allow the LLM agent to read, write, edit, and list files within the workspace directory.

## Requirements

### Requirement: ReadFileTool reads files from workspace
`ReadFileTool` SHALL 接受 `path: str` 参数（相对于 WORKSPACE_DIR），返回文件内容；路径穿越到工作目录外时返回权限错误，文件不存在时返回错误说明。

#### Scenario: File within workspace read successfully
- **WHEN** LLM 调用 `read_file(path="README.md")`，文件存在
- **THEN** 返回文件内容字符串

#### Scenario: Path traversal blocked
- **WHEN** LLM 调用 `read_file(path="../../etc/passwd")`
- **THEN** 返回 "路径超出工作目录，拒绝访问"，不读取任何内容

### Requirement: WriteFileTool creates or overwrites files
`WriteFileTool` SHALL 接受 `path: str` 和 `content: str`，在 WORKSPACE_DIR 内创建或覆盖文件（自动创建父目录）；路径穿越返回权限错误。

#### Scenario: File written successfully
- **WHEN** LLM 调用 `write_file(path="output/result.txt", content="...")`
- **THEN** 文件被创建或覆盖，返回 "已写入 output/result.txt"

### Requirement: EditFileTool performs precise string replacement
`EditFileTool` SHALL 接受 `path: str`、`old_string: str`、`new_string: str`，在文件中替换第一处 `old_string`；`old_string` 不存在时返回错误，不修改文件。

#### Scenario: Exact string replaced
- **WHEN** LLM 调用 `edit_file(path="config.py", old_string="DEBUG=False", new_string="DEBUG=True")`
- **THEN** 文件中第一处匹配被替换，返回成功消息

#### Scenario: Old string not found
- **WHEN** `old_string` 在文件中不存在
- **THEN** 文件不被修改，返回 "未找到要替换的内容"

### Requirement: ListDirTool lists directory contents
`ListDirTool` SHALL 接受可选 `path: str`（默认 WORKSPACE_DIR 根目录），返回目录下文件和子目录的列表（含类型标记）。

#### Scenario: Directory listed
- **WHEN** LLM 调用 `list_dir(path="src")`
- **THEN** 返回格式化列表，每项含名称和类型（file/dir）
