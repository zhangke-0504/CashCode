## ADDED Requirements

### Requirement: MCPPrepareTool 是永远可见的内置工具
`MCPPrepareTool` SHALL 是非 deferred 的内置工具，永远出现在 `get_definitions()` 返回列表中。

#### Scenario: 激活集为空时 mcp_prepare 可见
- **WHEN** `DeferredAwareRegistry.get_definitions()` 被调用，激活集为空
- **THEN** 返回列表包含 `mcp_prepare`

### Requirement: mcp_prepare 按需建立连接并激活工具
`MCPPrepareTool.execute(server_name)` SHALL：（1）如果 server 已连接，跳过建连接；（2）如果未连接，调用 `lazy_connect(server_name, config)` 建立 stdio 连接；（3）调用 `list_tools()`，注册 `MCPToolWrapper`，写入 disk cache；（4）将所有注册工具加入 `ActivatedToolSet`；（5）返回已激活工具名列表。

#### Scenario: 首次 prepare 建立连接并激活
- **WHEN** `mcp_prepare(server_name="weather")`，weather server 未连接
- **THEN** stdio 连接建立，工具注册进 FullRegistry，disk cache 写入，工具加入激活集，返回激活工具列表

#### Scenario: 重复 prepare 跳过建连接
- **WHEN** `mcp_prepare(server_name="weather")`，weather server 已连接
- **THEN** 不重新建连接，直接将已注册工具加入激活集，返回激活工具列表

#### Scenario: server_name 不在配置中返回错误
- **WHEN** `mcp_prepare(server_name="nonexistent")`
- **THEN** 返回错误字符串，不抛异常

### Requirement: lazy_connect 复用 owner task 模式
`lazy_connect(server_name, config, handles)` SHALL 调用 `establish_mcp_sessions({server_name: config})`，将新 handle 合并进传入的 handles dict，返回连接是否成功（bool）。

#### Scenario: 成功建立连接
- **WHEN** 调用 `lazy_connect("weather", cfg, handles)`，weather 配置有效
- **THEN** `handles["weather"]` 被填充，`handles["weather"].session` 不为 None，返回 True
