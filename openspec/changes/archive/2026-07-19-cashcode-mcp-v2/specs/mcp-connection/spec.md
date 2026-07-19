## MODIFIED Requirements

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
