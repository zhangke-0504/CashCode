## MODIFIED Requirements

### Requirement: establish_mcp_sessions 支持多种传输类型
The system SHALL determine transport type from config: `type: "stdio"` or command present → stdio; `type: "sse"` or url ending in `/sse` → SSE; `type: "streamableHttp"` or url present → streamableHttp. Previously only stdio was supported.

#### Scenario: SSE 配置正确路由到 sse_client
- **WHEN** config 含 `{"type": "sse", "url": "http://127.0.0.1:8090/sse"}`
- **THEN** owner task 使用 `sse_client(url)` 而非 `stdio_client(params)`，握手流程相同

#### Scenario: stdio 配置行为不变
- **WHEN** config 含 `{"type": "stdio", "command": "python", "args": [...]}`
- **THEN** 行为与修改前完全一致，不受 SSE 分支影响
