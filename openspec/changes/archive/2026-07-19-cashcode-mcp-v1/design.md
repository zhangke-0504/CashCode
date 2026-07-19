## Context

CashCode server 当前的工具体系极为简单：`SimpleAgentLoop` 在 `__init__` 里把内置工具放进一个 `list[Tool]`，`SimpleAgentRunner.run()` 每次调用时临时构建 `tool_map = {t.name: t for t in tools}`。这种方式无法动态接入外部工具。

MCP（Model Context Protocol）是连接 LLM Agent 与外部工具的开放协议。MCP server 是独立进程，通过 stdio（子进程标准输入输出）或 HTTP/SSE 与 Agent 通信。Agent 要使用 MCP 工具，必须先建立持久连接，再将其工具适配为 Agent 可调用的接口。

参考来源：spore 项目（`server/core/agent/tools/mcp.py`、`server/core/agent/tools/registry.py`）。本设计是 spore 实现的简化版，去掉鉴权、审批、版本控制、公司 catalog 等复杂机制，保留最小可用的 MCP 接入能力。

## Goals / Non-Goals

**Goals:**
- 实现 `ToolRegistry`：统一管理内置工具与 MCP 工具
- 实现 MCP stdio 连接：用后台 task 持有连接，支持优雅关闭
- 实现 `MCPToolWrapper`：将 MCP 工具适配为 CashCode `Tool` 接口
- 提供本地 mock MCP server（weather / notes）用于开发测试
- 改造 `runner.py` 和 `loop.py` 接入新体系，保持现有内置工具行为不变

**Non-Goals:**
- MCP SSE / streamableHttp 传输（V1 只支持 stdio）
- tool_search + 延迟激活（DeferredAwareRegistry）留给 V2
- 公司 MCP catalog / 服务发现
- 工具审批、鉴权注入

## Decisions

### 决策1：ToolRegistry 替代 list[Tool]

**选择**：新建 `ToolRegistry` 类，`runner.py` 接受 `ToolRegistry` 而非 `list[Tool]`。

**原因**：MCP 工具在 agent 启动后动态注册，`list[Tool]` 是构造时固定的，无法在 `run()` 之外修改。`ToolRegistry` 作为共享对象，`loop.py` 向其注册工具，`runner.py` 从中取工具执行，解耦了工具管理和工具执行。

**备选方案**：每次 `runner.run()` 重新传入包含 MCP 工具的 list。缺点：MCP 工具注册时机与 runner 调用时机分离，代码耦合更高。

### 决策2：后台 owner task 持有连接生命周期

**选择**：每个 MCP server 一个后台 `asyncio.Task`，在 task 内部用 `AsyncExitStack` 持有 transport + session 的整个生命周期。

**原因**：MCP SDK 的 stdio transport 内部使用 AnyIO cancel scope，**cancel scope 必须在同一个 asyncio task 内开启和关闭**。不能在 task A 里建连接，在 task B 里关闭。后台 task 模式（来自 spore）是解决此约束的标准方案。

**备选方案**：直接 `async with stdio_client(...) as ...:` 包住整个 agent 生命周期。缺点：无法独立管理多个 server 的连接，也无法按需关闭单个 server。

### 决策3：MCPToolWrapper 名称约定

**选择**：wrapped 工具名 = `mcp_{server_name}_{tool_def.name}`，如 `mcp_weather_get_weather`。

**原因**：与 spore 保持一致，方便未来迁移。`mcp_` 前缀也让 `ToolRegistry.get_definitions()` 能区分内置工具和 MCP 工具（内置在前，MCP 在后），稳定排序减少 prompt cache 抖动。

### 决策4：V1 所有 MCP 工具直接对模型可见

**选择**：MCP 工具注册进 `ToolRegistry` 后直接出现在 `get_definitions()` 返回值里，LLM 可以直接调用。

**原因**：V1 以"跑通基本流程"为目标，延迟激活（deferred）需要额外的 `DeferredAwareRegistry` + `ActivatedToolSet` + `ToolSearchTool`，留给 V2。本地 mock server 工具数量少（4个），直接暴露不会撑爆 context。

## Risks / Trade-offs

- **[风险] MCP server 启动失败** → 只跳过该 server，打印 warning，不影响 agent 主流程启动。
- **[风险] MCP server 进程崩溃后连接断开** → V1 不实现重连，工具调用会返回错误字符串；V2 再加 recover_session。
- **[风险] stdio 子进程在 Windows 上路径问题** → mock server 配置使用 `python` 命令 + 相对路径，需确保运行环境有对应 Python 可执行文件。
- **[trade-off] 所有工具对模型可见** → 工具多时会消耗 token，但 V1 本地 mock 只有 4 个工具，可接受。

## Migration Plan

1. 新增文件（不影响现有逻辑）：`registry.py`、`mcp.py`、`mcp_servers/`
2. 修改 `base.py`：添加 `to_schema = to_openai_schema`（向后兼容）
3. 修改 `runner.py`：同时兼容 `list[Tool]` 和 `ToolRegistry`（过渡期），待稳定后移除 list 路径
4. 修改 `loop.py`：用 `ToolRegistry` 替换 `self._tools` list，加入 MCP 初始化
5. 验证：启动 agent，发送"查询天气"消息，确认 MCP 工具被调用
