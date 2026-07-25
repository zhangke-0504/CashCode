## Why

V1 将所有 MCP 工具直接暴露给 LLM，当 MCP server 数量增多时会造成 context 溢出、模型困惑、prompt cache 抖动。需要引入延迟激活机制，让 LLM 按需通过搜索发现并激活工具，同时将连接从启动时改为按需建立，复现 spore 的完整 MCP 体系。

## What Changes

- 新增 `SessionMetadata` 持久层：`memory/<chat_id>/metadata.json`，为跨轮次状态（如激活集）提供磁盘存储
- 新增 `ActivatedToolSet`：LRU 激活集（容量50），绑定至当前 async task，跨轮次持久化到 session metadata
- 新增 `DeferredAwareRegistry`：包装 `ToolRegistry`，MCP 工具默认对 LLM 不可见，只有 activate 后才出现在工具列表
- 新增 `ToolSearchTool`：内置工具，BM25 搜索 MCP 工具并激活命中结果；附带 `ToolSearchIndex`（含 CJK bigram 分词）和 `CacheFeeder`（合并 disk cache + live registry）
- 新增 `mcp_cache.py`：工具 schema 磁盘缓存，以 transport fingerprint 做失效检测，为 lazy connection 提供离线搜索能力
- 新增 `MCPPrepareTool`：内置工具，按需建立单个 MCP server 的 stdio/SSE 连接，列举工具、注册 wrapper、写 cache、激活
- **BREAKING** 修改 `loop.py` 启动行为：不再在启动时连接所有 MCP server，改为读配置但不建连接；从 cache 加载工具 schema（callable=false）供搜索
- **BREAKING** 修改 `loop.py` 每轮处理：绑定 `ActivatedToolSet`，传 `DeferredAwareRegistry` 给 runner，轮次结束时写回 metadata

## Capabilities

### New Capabilities

- `session-metadata`: 跨轮次状态存储 —— `MemoryStore` 新增 metadata.json 读写，`ActivatedToolSet` 持久化至此
- `activated-tool-set`: 工具激活集 —— LRU dict，ContextVar 绑定，activate/touch/deactivate/跨轮次持久化
- `deferred-tool-registry`: 延迟工具注册表 —— DeferredAwareRegistry 包装 ToolRegistry，MCP 工具默认 deferred，激活后对 LLM 可见
- `mcp-tool-cache`: 工具 schema 磁盘缓存 —— transport fingerprint 验证，支持离线搜索
- `tool-search`: BM25 工具搜索 —— ToolSearchTool + ToolSearchIndex + CacheFeeder，中文 bigram + camelCase 分词，命中即激活
- `mcp-prepare`: 懒连接与激活 —— MCPPrepareTool 按需连接单个 server，list_tools + 注册 + 写 cache + 激活

### Modified Capabilities

- `mcp-connection`: 连接时机从启动时改为按需（mcp_prepare 触发），启动时仅读配置；关闭时仍优雅关闭所有已建连接
- `tool-registry`: 工具注册表不再直接暴露所有工具给 LLM，MCP 工具默认 deferred，通过 DeferredAwareRegistry 控制可见性

## Impact

- 新增文件：`server/app/agent/tools/mcp_cache.py`
- 新增文件：`server/app/agent/tools/tool_search.py`（含 ActivatedToolSet, DeferredAwareRegistry, ToolSearchIndex, ToolSearchTool, MCPPrepareTool, CacheFeeder）
- 修改文件：`server/app/memory/store.py`（+metadata 读写方法）
- 修改文件：`server/app/agent/tools/mcp.py`（+lazy_connect 单 server 按需连接）
- 修改文件：`server/app/agent/loop.py`（启动逻辑 + 每轮 ActivatedToolSet 绑定）
- 新增目录：`mcp_cache/`（工具 schema 缓存文件）
