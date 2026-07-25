## Why

CashCode 目前只支持 stdio 传输，只能连接本地命令行进程。现实中绝大多数公网 MCP server（Anthropic 官方 MCP、第三方服务）都通过 SSE（Server-Sent Events）HTTP 协议暴露。补全 SSE 传输后，CashCode 具备接入任意 HTTP MCP 服务的能力，同时通过本地 SSE mock server 直观展示 SSE 与 stdio 的架构差异（独立运行的 HTTP 服务 vs 自动 spawn 的子进程）。

## What Changes

- 新增 `mcp_servers/calculator/server.py`：使用 FastMCP 构建的 SSE MCP server，提供 `calculate` 和 `convert_unit` 两个工具，监听 `http://127.0.0.1:8090/sse`
- 修改 `mcp_servers/mcp_config.json`：新增 calculator 的 SSE 配置条目（`type: "sse"`, `url`）
- 修改 `server/app/agent/tools/mcp.py`：在 `establish_mcp_sessions()` 的 owner task 中加入 SSE 分支，调用 `sse_client(url)` 建立传输

## Capabilities

### New Capabilities

- `sse-transport`: SSE 传输支持 —— `establish_mcp_sessions()` 识别 `type: "sse"` 配置，通过 `sse_client(url)` 建立 HTTP 连接，owner task 模式不变
- `sse-mock-server`: 本地 SSE mock MCP server —— FastMCP 实现，需独立启动，提供 calculate 和 convert_unit 工具

### Modified Capabilities

- `mcp-connection`: 连接层新增 SSE transport 分支；SSE server 需独立运行（不自动 spawn），mcp_prepare 时若 server 未启动则返回连接错误

## Impact

- 新增文件：`mcp_servers/calculator/server.py`
- 修改文件：`mcp_servers/mcp_config.json`
- 修改文件：`server/app/agent/tools/mcp.py`（`establish_mcp_sessions()` 加 ~20 行）
- 新增依赖：`httpx-sse`（通常随 `mcp` 包自动安装）
