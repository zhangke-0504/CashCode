## ADDED Requirements

### Requirement: ToolSearchTool 是永远可见的内置工具
`ToolSearchTool` SHALL 是非 deferred 的内置工具，永远出现在 `get_definitions()` 返回列表中，不受激活集影响。

#### Scenario: 未激活任何工具时 tool_search 可见
- **WHEN** 激活集为空，`DeferredAwareRegistry.get_definitions()` 被调用
- **THEN** 返回列表包含 `tool_search`

### Requirement: tool_search 执行 BM25 搜索并激活命中工具
`ToolSearchTool.execute(query)` SHALL 刷新 `ToolSearchIndex`（通过 `CacheFeeder` 合并 disk cache + live registry），用 BM25 搜索 query，对 `callable=true` 的命中工具调用 `activated_set.activate()`，返回结构化结果文本。

#### Scenario: 搜索并激活工具
- **WHEN** 调用 `tool_search(query="天气 城市")`，`mcp_weather_get_weather` 在 disk cache 或 live registry 中存在且 callable
- **THEN** `mcp_weather_get_weather` 被加入激活集，返回文本包含 "✅ 已激活" 提示

#### Scenario: 搜索到 cache-only 工具时提示 mcp_prepare
- **WHEN** 调用 `tool_search(query="天气")`，工具仅在 disk cache（callable=false，未连接）
- **THEN** 返回文本包含 `requiresPreparation` 和 `mcp_prepare` 引导提示

#### Scenario: 无结果时返回友好提示
- **WHEN** 调用 `tool_search(query="根本不存在的功能")`
- **THEN** 返回"未找到相关工具"提示，不抛异常

### Requirement: ToolSearchIndex 使用 BM25 + CJK bigram
`ToolSearchIndex` SHALL 实现标准 BM25（k1=1.5, b=0.75），分词支持 ASCII + camelCase 拆分 + CJK bigram，索引基于文档 fingerprint 缓存（内容未变不重建）。

#### Scenario: 中文查询命中中文描述
- **WHEN** 工具描述含"获取城市天气"，查询为"天气查询"
- **THEN** 该工具出现在搜索结果中（score > 0）

#### Scenario: camelCase 工具名可被搜索
- **WHEN** 工具名为 `getWeatherForecast`，查询为 "weather forecast"
- **THEN** 该工具出现在搜索结果中

### Requirement: CacheFeeder 合并 disk cache 与 live registry
`CacheFeeder.iter_documents()` SHALL 遍历所有已配置 server，先读 disk cache，再查 live `ToolRegistry`，live 结果优先（覆盖同名 cache 条目），返回 `IndexDocument` 列表。

#### Scenario: live 工具标记 callable=true
- **WHEN** server 已连接，工具在 live registry 中
- **THEN** 对应 IndexDocument `callable=true`、`source="live"`

#### Scenario: 仅 cache 工具标记 callable=false
- **WHEN** server 未连接，工具只在 disk cache
- **THEN** 对应 IndexDocument `callable=false`、`source="cache"`、`requires_preparation=true`
