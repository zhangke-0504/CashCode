## Context

CashCode V1/V2 的 `establish_mcp_sessions()` 使用 `owner task` 模式（每个 server 一个 asyncio.Task 持有 AsyncExitStack），目前只有 stdio 分支。加入 SSE 分支只需在 owner task 内增加一个 `elif transport_type == "sse"` 路径，其余握手、list_tools、lazy_connect 流程完全复用。

本地 SSE mock server 使用 `mcp.server.fastmcp.FastMCP`（mcp SDK 的高层封装），通过 `mcp.run(transport="sse")` 暴露 HTTP/SSE 端点，需独立启动，不由 CashCode 自动 spawn。

## Goals / Non-Goals

**Goals:**
- `establish_mcp_sessions()` 支持 `type: "sse"` 配置，通过 `sse_client(url)` 建立连接
- 提供本地 SSE mock server（calculator），验证端到端 SSE 连接流程
- 用户能通过 `mcp_prepare("calculator")` 触发 SSE 连接并激活工具

**Non-Goals:**
- streamableHttp transport（下一步，和 SSE 同构）
- 自动启动/守护 SSE server 进程
- SSE 身份认证（LoginAuth）

## Decisions

### 决策1：SSE server 需独立手动启动

**选择**：文档说明用户需在独立终端启动 `python mcp_servers/calculator/server.py`，CashCode 不自动 spawn。

**原因**：SSE 代表的是"远程 HTTP 服务"模式。自动 spawn 与这一语义矛盾，也无法在生产中使用（公网 MCP 服务显然不由 Agent 进程 spawn）。这个约束本身就是 SSE 和 stdio 架构差异的核心教学点。

### 决策2：使用 FastMCP 而非低层 Server API

**选择**：SSE mock server 使用 `mcp.server.fastmcp.FastMCP` + `@mcp.tool()` 装饰器。

**原因**：FastMCP 隐藏了 list_tools/call_tool 的样板代码，代码量减半，与 stdio server 形成鲜明对比，更清晰地展示"SSE server 侧很简单，复杂性在 client 侧（owner task 模式）"。

### 决策3：owner task 模式完全复用

**选择**：SSE 分支只替换传输建立那一步（`sse_client(url)` 替代 `stdio_client(params)`），owner task 的 ready/close_requested/AsyncExitStack 机制不变。

**原因**：这是架构上最重要的一点：**两种传输的区别仅在于"怎么建立通道"，建好之后的 MCP 会话完全相同**。保持代码结构一致强化这一认知。

## Risks / Trade-offs

- **[风险] SSE server 未启动时 mcp_prepare 报错** → 设计上是正确行为（连接失败），owner task 的 `errors_out` 捕获异常，handle 不进入 accepted，`lazy_connect` 返回 False，MCPPrepareTool 返回友好错误字符串。
- **[trade-off] 需要两个终端** → 教学价值高于便利性，这正好展示了两种传输的本质区别。
