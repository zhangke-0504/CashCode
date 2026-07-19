# Spec: mock-mcp-servers

## Purpose

提供本地可独立运行的 mock MCP stdio server，用于开发阶段验证 MCP 连接、工具包装和 agent 集成，无需真实外部 API。

## Requirements

### Requirement: 本地 weather MCP server
`mcp_servers/weather/server.py` SHALL 是一个可独立运行的 MCP stdio server，提供 `get_weather` 和 `get_forecast` 两个工具，返回 mock 数据（无需真实 API）。

#### Scenario: get_weather 返回 mock 天气
- **WHEN** 调用 `get_weather(city="北京")`
- **THEN** 返回包含城市名、天气状况、温度的字符串，如 `"北京：晴，25°C，湿度 40%"`

#### Scenario: get_forecast 返回多天预报
- **WHEN** 调用 `get_forecast(city="上海", days=3)`
- **THEN** 返回 3 天的 mock 预报数据字符串

#### Scenario: server 可独立启动
- **WHEN** 执行 `python mcp_servers/weather/server.py`
- **THEN** 进程启动并等待 stdio 输入（MCP 握手），无报错退出

### Requirement: 本地 notes MCP server
`mcp_servers/notes/server.py` SHALL 是一个可独立运行的 MCP stdio server，提供 `create_note` 和 `list_notes` 两个工具，将便签持久化到 `mcp_servers/notes/data/` 目录。

#### Scenario: create_note 创建便签文件
- **WHEN** 调用 `create_note(title="买菜清单", content="苹果、牛奶")`
- **THEN** 在 `mcp_servers/notes/data/` 目录创建对应文件，返回成功消息

#### Scenario: list_notes 列出所有便签
- **WHEN** 调用 `list_notes()`
- **THEN** 返回 `data/` 目录下所有便签的标题列表

#### Scenario: server 可独立启动
- **WHEN** 执行 `python mcp_servers/notes/server.py`
- **THEN** 进程启动并等待 stdio 输入，无报错退出

### Requirement: mcp_config.json 配置文件
`mcp_servers/mcp_config.json` SHALL 包含 weather 和 notes 两个 server 的 stdio 配置，agent 启动时读取此文件连接 server。

#### Scenario: 配置格式正确
- **WHEN** agent 读取 `mcp_config.json`
- **THEN** 能解析出 `{"weather": {"type": "stdio", "command": "python", "args": [...]}, "notes": {...}}` 结构
