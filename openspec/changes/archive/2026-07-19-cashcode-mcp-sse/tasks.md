## 1. SSE Mock Server（calculator）

- [x] 1.1 创建目录 `mcp_servers/calculator/`
- [x] 1.2 实现 `mcp_servers/calculator/server.py`：使用 `FastMCP`，提供 `calculate(expression: str)` 工具（安全计算数学表达式，异常返回错误字符串）和 `convert_unit(value, from_unit, to_unit)` 工具（支持常见单位：km/miles、kg/lb、°C/°F），启动端口 8090
- [x] 1.3 在 `mcp_servers/mcp_config.json` 中新增 calculator 条目：`{"type": "sse", "url": "http://127.0.0.1:8090/sse", "display_name": "计算器服务", "description": "数学计算和单位换算"}`
- [ ] 1.4 验证：独立运行 `python mcp_servers/calculator/server.py`，浏览器或 curl 访问 `http://127.0.0.1:8090/sse` 有响应

## 2. SSE Transport（establish_mcp_sessions）

- [x] 2.1 修改 `server/app/agent/tools/mcp.py` 的 `establish_mcp_sessions()` owner task：在现有 stdio 分支之后添加 SSE 分支（`from mcp.client.sse import sse_client`，调用 `sse_client(cfg["url"])`）
- [x] 2.2 确保传输类型自动推断逻辑：无 `type` 字段时，有 `command` → stdio；有 `url` 且末尾为 `/sse` → sse；有 `url` 其他 → streamableHttp（兼容占位，暂不实现）
- [ ] 2.3 验证：启动 calculator server 后，运行 `test_sse.py` 直接调用 `establish_mcp_sessions` 连接 calculator，打印 list_tools 结果

## 3. 端到端验证

- [ ] 3.1 启动 calculator server（终端1：`python mcp_servers/calculator/server.py`），启动 agent（终端2：`python server/main.py`）
- [ ] 3.2 发送 `"用 calculate 工具算一下 (123 + 456) * 2"`，确认流程：`tool_search` → 找到 calculator 服务级存根 → 引导 `mcp_prepare` → `mcp_prepare("calculator")` → SSE 连接建立 → 工具激活 → `mcp_calculator_calculate` 被调用 → 返回 `1158`
- [ ] 3.3 发送 `"100公里是多少英里"`，确认 `mcp_calculator_convert_unit` 被调用并返回正确结果
- [ ] 3.4 关闭 calculator server，发送计算请求，确认 `mcp_prepare` 返回友好错误（"连接失败"）而非崩溃
- [ ] 1.2 实现 `mcp_servers/calculator/server.py`：使用 `FastMCP`，提供 `calculate(expression: str)` 工具（安全计算数学表达式，异常返回错误字符串）和 `convert_unit(value, from_unit, to_unit)` 工具（支持常见单位：km/miles、kg/lb、°C/°F），启动端口 8090
- [ ] 1.3 在 `mcp_servers/mcp_config.json` 中新增 calculator 条目：`{"type": "sse", "url": "http://127.0.0.1:8090/sse", "display_name": "计算器服务", "description": "数学计算和单位换算"}`
- [ ] 1.4 验证：独立运行 `python mcp_servers/calculator/server.py`，浏览器或 curl 访问 `http://127.0.0.1:8090/sse` 有响应

## 2. SSE Transport（establish_mcp_sessions）

- [ ] 2.1 修改 `server/app/agent/tools/mcp.py` 的 `establish_mcp_sessions()` owner task：在现有 stdio 分支之后添加 SSE 分支（`from mcp.client.sse import sse_client`，调用 `sse_client(cfg["url"])`）
- [ ] 2.2 确保传输类型自动推断逻辑：无 `type` 字段时，有 `command` → stdio；有 `url` 且末尾为 `/sse` → sse；有 `url` 其他 → streamableHttp（兼容占位，暂不实现）
- [ ] 2.3 验证：启动 calculator server 后，运行 `test_sse.py` 直接调用 `establish_mcp_sessions` 连接 calculator，打印 list_tools 结果

## 3. 端到端验证

- [ ] 3.1 启动 calculator server（终端1：`python mcp_servers/calculator/server.py`），启动 agent（终端2：`python server/main.py`）
- [ ] 3.2 发送 `"用 calculate 工具算一下 (123 + 456) * 2"`，确认流程：`tool_search` → 找到 calculator 服务级存根 → 引导 `mcp_prepare` → `mcp_prepare("calculator")` → SSE 连接建立 → 工具激活 → `mcp_calculator_calculate` 被调用 → 返回 `1158`
- [ ] 3.3 发送 `"100公里是多少英里"`，确认 `mcp_calculator_convert_unit` 被调用并返回正确结果
- [ ] 3.4 关闭 calculator server，发送计算请求，确认 `mcp_prepare` 返回友好错误（"连接失败"）而非崩溃
