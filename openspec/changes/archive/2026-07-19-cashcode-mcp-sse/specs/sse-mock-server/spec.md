## ADDED Requirements

### Requirement: SSE mock server 可独立启动
`mcp_servers/calculator/server.py` SHALL 是一个可独立运行的 FastMCP SSE server，执行 `python mcp_servers/calculator/server.py` 后监听 `http://127.0.0.1:8090/sse`，无需 CashCode 进程存在。

#### Scenario: 独立启动并暴露端点
- **WHEN** 执行 `python mcp_servers/calculator/server.py`
- **THEN** 进程启动，日志显示监听 `http://127.0.0.1:8090`，GET `http://127.0.0.1:8090/sse` 返回 SSE 流

### Requirement: calculator server 提供 calculate 和 convert_unit 工具
calculator server SHALL 通过 FastMCP 暴露 `calculate(expression: str)` 和 `convert_unit(value: float, from_unit: str, to_unit: str)` 两个工具。

#### Scenario: calculate 执行数学表达式
- **WHEN** 调用 `calculate(expression="2 + 3 * 4")`
- **THEN** 返回 `"14"` 或包含结果的字符串；非法表达式返回错误描述，不抛出未捕获异常

#### Scenario: convert_unit 换算常见单位
- **WHEN** 调用 `convert_unit(value=100, from_unit="km", to_unit="miles")`
- **THEN** 返回包含换算结果的字符串（约 `"62.14 miles"`）

### Requirement: mcp_config.json 包含 calculator SSE 条目
`mcp_config.json` SHALL 新增 calculator 条目，包含 `type: "sse"` 和 `url`，不含 `command`/`args`。

#### Scenario: 配置格式正确
- **WHEN** CashCode 读取 mcp_config.json
- **THEN** calculator 条目解析为 `{"type": "sse", "url": "http://127.0.0.1:8090/sse", "display_name": ..., "description": ...}`
