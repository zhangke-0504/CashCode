## 1. 依赖与环境准备

- [x] 1.1 在 `server/requirements.txt` 中添加 `mcp>=1.0` 依赖
- [x] 1.2 在 `server/` 目录下运行 `pip install mcp` 确认安装成功

## 2. 本地 Mock MCP Servers

- [x] 2.1 创建目录结构：`mcp_servers/weather/`、`mcp_servers/notes/`、`mcp_servers/notes/data/`
- [x] 2.2 实现 `mcp_servers/weather/server.py`：stdio MCP server，包含 `get_weather(city)` 和 `get_forecast(city, days)` 两个工具，返回 mock 数据
- [x] 2.3 实现 `mcp_servers/notes/server.py`：stdio MCP server，包含 `create_note(title, content)` 和 `list_notes()` 两个工具，数据持久化到 `mcp_servers/notes/data/`
- [x] 2.4 创建 `mcp_servers/mcp_config.json`：包含 weather 和 notes 两个 server 的 stdio 配置
- [x] 2.5 验证：`python mcp_servers/weather/server.py` 能启动无报错；`python mcp_servers/notes/server.py` 能启动无报错

## 3. ToolRegistry

- [x] 3.1 新建 `server/app/agent/tools/registry.py`，实现 `ToolRegistry` 类（`register`、`get`、`has`、`get_definitions`、`execute`、`tool_names`）
- [x] 3.2 在 `server/app/agent/tools/base.py` 中添加 `to_schema = to_openai_schema` 别名，供 `ToolRegistry.get_definitions()` 调用
- [x] 3.3 验证：在 Python shell 中手动创建 ToolRegistry，注册一个内置 Tool，调用 `get_definitions()` 返回正确 schema

## 4. MCP 连接层与工具包装

- [x] 4.1 新建 `server/app/agent/tools/mcp.py`，实现 `MCPConnectionHandle` dataclass（`session` 属性、`wait_ready()`、`aclose()`）
- [x] 4.2 在 `mcp.py` 中实现 `establish_mcp_sessions(mcp_servers: dict) -> dict[str, MCPConnectionHandle]`：每个 server 一个后台 owner task，支持 stdio 传输，30s 超时，失败时跳过并打印 warning
- [x] 4.3 在 `mcp.py` 中实现 `MCPToolWrapper(Tool)`：`name` 为 `mcp_{server_name}_{tool_def.name}`，`execute()` 调用 `session.call_tool()` 并提取 TextContent，超时/异常返回错误字符串不抛出
- [x] 4.4 在 `mcp.py` 中实现 `load_mcp_tools(handles, registry)`：对每个 handle 调用 `session.list_tools()`，为每个 tool_def 创建 `MCPToolWrapper` 并注册进 registry
- [x] 4.5 验证：写一个临时测试脚本，调用 `establish_mcp_sessions` 连接 weather server，调用 `get_weather`，打印返回结果

## 5. Runner 改造

- [x] 5.1 修改 `server/app/agent/runner.py`：`run()` 方法改为接受 `ToolRegistry` 参数，用 `registry.get_definitions()` 替代 `[t.to_openai_schema() for t in tools]`，用 `registry.execute(name, kwargs)` 替代 `tool_map[name].execute(**kwargs)`
- [x] 5.2 验证：runner 单独测试（不走 MCP），发一条不需要工具的消息，确认返回正常

## 6. Loop 改造与集成

- [x] 6.1 修改 `server/app/agent/loop.py`：将 `self._tools = [...]` 替换为 `self._registry = ToolRegistry()`，用 `registry.register(tool)` 逐一注册内置工具
- [x] 6.2 在 `loop.py` 中添加 `async def _setup_mcp()`：读取 `mcp_servers/mcp_config.json`（不存在则跳过），调用 `establish_mcp_sessions()`，调用 `load_mcp_tools()`
- [x] 6.3 在 `loop.py` 的 `run()` 方法里，主循环开始前调用 `await self._setup_mcp()`
- [x] 6.4 在 `loop.py` 的 `stop()` 方法里，对所有 `self._mcp_handles` 调用 `await handle.aclose()`
- [x] 6.5 将 `runner.run()` 的调用从传 `self._tools` 改为传 `self._registry`

## 7. 端到端验证

- [ ] 7.1 启动 agent（`python server/main.py`），确认日志显示 weather 和 notes server 连接成功，MCP 工具注册完毕
- [ ] 7.2 通过 WebSocket 发送"北京今天天气怎么样"，确认 agent 调用了 `mcp_weather_get_weather` 并返回 mock 天气数据
- [ ] 7.3 通过 WebSocket 发送"帮我记一个便签，标题是买菜清单，内容是苹果牛奶"，确认 agent 调用了 `mcp_notes_create_note` 并在 `mcp_servers/notes/data/` 生成文件
- [ ] 7.4 通过 WebSocket 发送"列出我所有的便签"，确认 agent 调用了 `mcp_notes_list_notes` 并返回列表
