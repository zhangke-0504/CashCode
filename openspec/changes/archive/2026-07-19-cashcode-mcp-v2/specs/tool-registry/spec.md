## MODIFIED Requirements

### Requirement: ToolRegistry 中 MCP 工具默认对 LLM 不可见
The system SHALL use `DeferredAwareRegistry` (wrapping `ToolRegistry`) when passing tools to `SimpleAgentRunner`. MCP tools (`mcp_` prefix) SHALL be deferred by default and only appear in `get_definitions()` output when present in the current `ActivatedToolSet`.

#### Scenario: runner 收到 DeferredAwareRegistry
- **WHEN** `SimpleAgentRunner.run(messages, registry)` 被调用
- **THEN** `registry` 为 `DeferredAwareRegistry` 实例，`get_definitions()` 默认不含任何 `mcp_` 工具

#### Scenario: builtin 工具不受 deferred 影响
- **WHEN** `DeferredAwareRegistry.get_definitions()` 被调用，激活集为空
- **THEN** `save_memory`、`web_fetch`、`tool_search`、`mcp_prepare` 等 builtin 工具均可见
