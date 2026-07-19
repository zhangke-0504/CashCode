## ADDED Requirements

### Requirement: 统一工具注册与查找
ToolRegistry SHALL 以字典形式存储所有工具（内置 + MCP），提供注册、查找、执行的统一接口。

#### Scenario: 注册工具
- **WHEN** 调用 `registry.register(tool)`
- **THEN** 工具以 `tool.name` 为 key 存入内部字典，`get_definitions()` 缓存失效

#### Scenario: 查找已注册工具
- **WHEN** 调用 `registry.get("save_memory")`
- **THEN** 返回对应的 Tool 对象；若不存在则返回 None

#### Scenario: 执行工具
- **WHEN** 调用 `registry.execute("web_fetch", {"url": "https://..."})`
- **THEN** 找到对应工具，调用其 `execute(**params)`，返回结果字符串；工具不存在时返回错误字符串

### Requirement: 稳定排序的工具定义列表
`get_definitions()` SHALL 返回所有工具的 OpenAI schema 列表，内置工具（非 `mcp_` 前缀）排在前面并按名称排序，MCP 工具（`mcp_` 前缀）排在后面并按名称排序，结果缓存至下次 register/unregister。

#### Scenario: 工具定义排序
- **WHEN** 已注册 `mcp_weather_get_weather`、`save_memory`、`web_fetch`，调用 `get_definitions()`
- **THEN** 返回顺序为 `save_memory`、`web_fetch`（字母序）在前，`mcp_weather_get_weather` 在后

#### Scenario: 注册新工具后缓存失效
- **WHEN** 调用 `get_definitions()` 后再 `register(new_tool)`，再次调用 `get_definitions()`
- **THEN** 第二次调用重新计算并包含新工具

### Requirement: runner 兼容 ToolRegistry
`SimpleAgentRunner.run()` SHALL 接受 `ToolRegistry` 参数，从中获取工具定义和执行工具，替代原有的 `list[Tool]` 参数。

#### Scenario: runner 使用 registry 执行工具
- **WHEN** LLM 返回 tool_call `{name: "save_memory", arguments: {...}}`
- **THEN** runner 调用 `registry.execute("save_memory", {...})` 并将结果追加到 messages
