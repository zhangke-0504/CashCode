## ADDED Requirements

### Requirement: 建立 MCP stdio 连接
`establish_mcp_sessions()` SHALL 读取 server 配置列表，为每个 server 启动一个后台 asyncio task，在 task 内建立 stdio 连接并完成握手，返回 `{server_name: MCPConnectionHandle}` 字典（只包含连接成功的 server）。

#### Scenario: 成功连接 stdio MCP server
- **WHEN** 配置包含 `{"weather": {"type": "stdio", "command": "python", "args": ["mcp_servers/weather/server.py"]}}`
- **THEN** 启动 weather 进程，完成 MCP 握手，handle.session 不为 None，handle 进入 accepted 字典

#### Scenario: 连接失败时跳过
- **WHEN** MCP server 进程启动失败或握手超时（30s）
- **THEN** 该 server 不出现在返回字典中，打印 warning 日志，不抛出异常，其他 server 不受影响

### Requirement: 后台 task 持有连接生命周期
每个 MCP server 的 AsyncExitStack（transport + session）SHALL 在同一个 asyncio task 内开启和关闭，task 在收到关闭信号前一直运行。

#### Scenario: session 在 task 生命周期内可用
- **WHEN** `establish_mcp_sessions()` 返回后
- **THEN** `handle.session` 返回有效的 `ClientSession` 对象，可以调用 `call_tool()`

#### Scenario: 优雅关闭
- **WHEN** 调用 `await handle.aclose()`
- **THEN** 后台 task 收到信号，关闭 AsyncExitStack（断开连接、终止子进程），task 结束

### Requirement: loop 启动时初始化 MCP 连接
`SimpleAgentLoop` SHALL 在主循环启动前读取 `mcp_servers/mcp_config.json`（文件不存在时跳过），调用 `establish_mcp_sessions()`，并对每个连接成功的 server 调用 `session.list_tools()` 将工具注册进 `ToolRegistry`。

#### Scenario: 正常启动时加载 MCP 工具
- **WHEN** `mcp_config.json` 存在且包含有效 server 配置
- **THEN** MCP 工具被注册进 registry，loop 主循环正常启动

#### Scenario: 无配置文件时正常启动
- **WHEN** `mcp_servers/mcp_config.json` 不存在
- **THEN** 跳过 MCP 初始化，loop 正常启动，内置工具可用
