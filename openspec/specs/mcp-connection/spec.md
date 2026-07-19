# Spec: mcp-connection

## Purpose

管理 CashCode agent 与外部 MCP server 的连接生命周期：启动、握手、保活、优雅关闭，并在 agent loop 启动时自动初始化。支持多种传输类型：stdio、SSE 和 streamableHttp。

## Requirements

### Requirement: establish_mcp_sessions 支持多种传输类型
`establish_mcp_sessions()` SHALL 读取 server 配置列表，为每个 server 启动一个后台 asyncio task，在 task 内根据配置确定传输类型并建立连接，完成握手，返回 `{server_name: MCPConnectionHandle}` 字典（只包含连接成功的 server）。传输类型判断规则：`type: "stdio"` 或 command 字段存在 → stdio；`type: "sse"` 或 url 以 `/sse` 结尾 → SSE；`type: "streamableHttp"` 或 url 字段存在 → streamableHttp。

#### Scenario: 成功连接 stdio MCP server
- **WHEN** 配置包含 `{"weather": {"type": "stdio", "command": "python", "args": ["mcp_servers/weather/server.py"]}}`
- **THEN** 启动 weather 进程，完成 MCP 握手，handle.session 不为 None，handle 进入 accepted 字典

#### Scenario: 连接失败时跳过
- **WHEN** MCP server 进程启动失败或握手超时（30s）
- **THEN** 该 server 不出现在返回字典中，打印 warning 日志，不抛出异常，其他 server 不受影响

#### Scenario: SSE 配置正确路由到 sse_client
- **WHEN** config 含 `{"type": "sse", "url": "http://127.0.0.1:8090/sse"}`
- **THEN** owner task 使用 `sse_client(url)` 而非 `stdio_client(params)`，握手流程相同

#### Scenario: stdio 配置行为不变
- **WHEN** config 含 `{"type": "stdio", "command": "python", "args": [...]}`
- **THEN** 行为与修改前完全一致，不受 SSE 分支影响

### Requirement: 后台 task 持有连接生命周期
每个 MCP server 的 AsyncExitStack（transport + session）SHALL 在同一个 asyncio task 内开启和关闭，task 在收到关闭信号前一直运行。

#### Scenario: session 在 task 生命周期内可用
- **WHEN** `establish_mcp_sessions()` 返回后
- **THEN** `handle.session` 返回有效的 `ClientSession` 对象，可以调用 `call_tool()`

#### Scenario: 优雅关闭
- **WHEN** 调用 `await handle.aclose()`
- **THEN** 后台 task 收到信号，关闭 AsyncExitStack（断开连接、终止子进程），task 结束

### Requirement: MCP server 连接改为按需触发
The system SHALL NOT establish MCP server connections at startup. Connections SHALL only be established when `MCPPrepareTool.execute(server_name)` is explicitly called. At startup, the system reads `mcp_config.json` and stores configuration without connecting.

#### Scenario: 启动时不建立任何 MCP 连接
- **WHEN** `SimpleAgentLoop` 启动（`run()` 被调用）
- **THEN** 不调用 `establish_mcp_sessions()`，`self._mcp_handles` 为空，无 MCP 子进程被启动

#### Scenario: mcp_prepare 触发按需连接
- **WHEN** `MCPPrepareTool.execute("weather")` 被调用，weather server 未连接
- **THEN** 建立 stdio 连接，owner task 启动，session 握手完成，`self._mcp_handles["weather"]` 填充

### Requirement: 已建立的连接在关闭时优雅关闭
The system SHALL close all active MCP connections (those in `self._mcp_handles`) when `stop()` is called, regardless of when they were established (startup or lazy connect).

#### Scenario: stop() 关闭所有懒加载连接
- **WHEN** 运行期间通过 `mcp_prepare` 建立了 weather 和 notes 连接，随后调用 `agent.stop()`
- **THEN** 对 `self._mcp_handles` 中所有 handle 调用 `aclose()`，stdio 子进程终止
