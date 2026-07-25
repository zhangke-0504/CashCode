## ADDED Requirements

### Requirement: 将 MCP 工具适配为 CashCode Tool 接口
`MCPToolWrapper` SHALL 实现 `Tool` 抽象基类，将 MCP server 的单个工具封装为 CashCode 可调用的 Tool 对象。

#### Scenario: 工具名称命名规范
- **WHEN** 创建 `MCPToolWrapper(session, server_name="weather", tool_def.name="get_weather")`
- **THEN** `wrapper.name` 返回 `"mcp_weather_get_weather"`

#### Scenario: 工具 schema 透传
- **WHEN** MCP server 返回 `tool_def.inputSchema = {"type": "object", "properties": {"city": {...}}, "required": ["city"]}`
- **THEN** `wrapper.parameters()` 返回该 schema（经过 nullable 标准化处理）

### Requirement: execute() 转发至 MCP session
`MCPToolWrapper.execute()` SHALL 通过 `session.call_tool(original_name, arguments=kwargs)` 调用外部进程，提取 `TextContent` 文本并返回字符串；调用超时（默认 30s）时返回超时错误字符串而非抛出异常。

#### Scenario: 成功执行 MCP 工具
- **WHEN** 调用 `wrapper.execute(city="北京")`，MCP server 返回 `TextContent(text="北京：晴，25°C")`
- **THEN** `execute()` 返回字符串 `"北京：晴，25°C"`

#### Scenario: 工具调用超时
- **WHEN** MCP server 30 秒内未响应
- **THEN** `execute()` 返回描述超时的错误字符串，不抛出异常

#### Scenario: 工具调用异常
- **WHEN** `session.call_tool()` 抛出异常
- **THEN** `execute()` 捕获异常，返回描述错误的字符串，不向上传播

### Requirement: ToolRegistry 中的 MCP 工具对模型可见
连接后 `session.list_tools()` 返回的每个工具 SHALL 被包装为 `MCPToolWrapper` 并注册进 `ToolRegistry`，出现在 `get_definitions()` 返回值的 MCP 工具段（`mcp_` 前缀，按名排序）。

#### Scenario: list_tools 后工具可被 LLM 调用
- **WHEN** `load_mcp_tools(handles, registry)` 执行完毕
- **THEN** `registry.get("mcp_weather_get_weather")` 返回有效的 `MCPToolWrapper` 对象
