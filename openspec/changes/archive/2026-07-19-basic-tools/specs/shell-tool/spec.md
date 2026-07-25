## ADDED Requirements

### Requirement: ExecTool executes shell commands in workspace
`ExecTool` SHALL 接受 `command: str`，在 WORKSPACE_DIR 内以 asyncio subprocess 执行，合并 stdout+stderr，截断到4096字符后返回；超时30秒自动终止并返回超时提示。

#### Scenario: Command executes and returns output
- **WHEN** LLM 调用 `exec(command="git status")`
- **THEN** 返回命令输出（stdout + stderr 合并，最多4096字符）

#### Scenario: Command times out
- **WHEN** 命令执行超过30秒
- **THEN** 进程被终止，返回 "命令执行超时（30秒）"

#### Scenario: Command fails with non-zero exit code
- **WHEN** 命令以非零退出码结束
- **THEN** 返回包含 stderr 内容的错误信息，不抛出异常
