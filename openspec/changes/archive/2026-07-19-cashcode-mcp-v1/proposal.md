## Why

CashCode 目前只支持硬编码的内置工具（`SaveMemoryTool`、`WebFetchTool` 等），工具列表在 `loop.py` 里固定写死，无法动态扩展。MCP（Model Context Protocol）是 Anthropic 定义的开放工具协议，支持将外部程序的能力以标准方式暴露给 Agent。引入 MCP 支持后，任何符合协议的外部服务都可以作为工具接入，不需要修改 Agent 核心代码。

## What Changes

- 新增 `ToolRegistry`：统一管理所有工具（内置 + MCP），替代 `runner.py` 里临时构建的 `tool_map` 字典
- 新增 `MCPToolWrapper`：将外部 MCP server 暴露的工具适配成 CashCode `Tool` 接口，Agent 无需感知工具是内置还是 MCP 来源
- 新增 `establish_mcp_sessions()`：连接外部 MCP 进程（stdio 传输），用后台 task 持有连接生命周期，返回 `MCPConnectionHandle`
- 新增 `mcp_servers/` 目录：包含本地 mock MCP server，用于在无公司网络环境下测试（weather 服务：2 个工具；notes 服务：2 个工具）
- 修改 `runner.py`：接受 `ToolRegistry` 替代 `list[Tool]`
- 修改 `loop.py`：启动时读取 `mcp_config.json`，建立 MCP 连接，将 MCP 工具注册进 `ToolRegistry`

## Capabilities

### New Capabilities

- `tool-registry`: 统一工具注册与查找 —— 存储所有工具（内置 + MCP），提供 register / get / get_definitions / execute 接口
- `mcp-connection`: MCP server 连接管理 —— 建立 stdio 连接，后台 task 持有生命周期，优雅关闭
- `mcp-tool-wrapping`: MCP 工具适配 —— 将 MCP 协议工具包装为 CashCode Tool，execute() 时通过 session.call_tool() 转发
- `mock-mcp-servers`: 本地 mock MCP server —— 提供可独立运行的测试 server（weather / notes），无需依赖公司内网

### Modified Capabilities

## Impact

- 新增文件：`server/app/agent/tools/registry.py`
- 新增文件：`server/app/agent/tools/mcp.py`
- 新增文件：`mcp_servers/mcp_config.json`
- 新增文件：`mcp_servers/weather/server.py`
- 新增文件：`mcp_servers/notes/server.py`
- 修改文件：`server/app/agent/tools/base.py`（添加 `to_schema` 别名）
- 修改文件：`server/app/agent/runner.py`（`list[Tool]` → `ToolRegistry`）
- 修改文件：`server/app/agent/loop.py`（添加 MCP 启动/关闭逻辑）
- 修改文件：`server/requirements.txt`（添加 `mcp>=1.0` 依赖）
