# Spec: deferred-tool-registry

## Purpose

在 ToolRegistry 之上提供 deferred（按需可见）语义：MCP 工具默认对 LLM 隐藏，仅当工具出现在当前 ActivatedToolSet 中时才暴露给 LLM，同时对未激活工具的调用返回引导错误。

## Requirements

### Requirement: DeferredAwareRegistry 默认隐藏 MCP 工具
`DeferredAwareRegistry` SHALL 包装 `ToolRegistry`，`get_definitions()` 默认只返回非 deferred 工具（builtin），MCP 工具（`mcp_` 前缀）只有在当前 `ActivatedToolSet` 中才出现在返回列表里。

#### Scenario: 未激活的 MCP 工具不可见
- **WHEN** `get_definitions()` 被调用，`mcp_weather_get_weather` 未在激活集中
- **THEN** 返回列表中不包含 `mcp_weather_get_weather`

#### Scenario: 激活后立即可见
- **WHEN** `activated_set.activate("mcp_weather_get_weather")` 后再次调用 `get_definitions()`
- **THEN** 返回列表包含 `mcp_weather_get_weather`

### Requirement: get_definitions() 缓存随激活集版本失效
`get_definitions()` SHALL 以 `(full_registry.membership_revision, activated_set.visibility_revision)` 为缓存 key，任一变化时重新计算，不变时直接返回缓存。

#### Scenario: activate 触发缓存失效
- **WHEN** 调用 `get_definitions()` 后执行 `activated_set.activate("mcp_tool")`，再次调用 `get_definitions()`
- **THEN** 第二次调用重新计算并包含新激活工具（缓存 key 中的 `visibility_revision` 已变）

### Requirement: 未激活的 deferred 工具调用返回引导错误
`prepare_call()` SHALL 对 deferred 且未激活的 MCP 工具返回错误字符串，提示先调用 `tool_search`，而非直接执行。

#### Scenario: 调用未激活工具返回引导
- **WHEN** LLM 尝试调用 `mcp_weather_get_weather`，该工具未在激活集中
- **THEN** `execute()` 返回 `"工具 'mcp_weather_get_weather' 尚未激活，请先调用 tool_search 搜索相关工具"`
