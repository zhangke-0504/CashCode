## Context

CashCode V1 实现了基础 MCP 体系（ToolRegistry + MCPToolWrapper + establish_mcp_sessions），启动时连接所有 MCP server 并将工具直接暴露给 LLM。当 MCP server 数量增加时，这种"全量可见"方式会导致 LLM 工具列表过长。

V2 目标是复现 spore 的完整延迟激活体系：工具默认不可见，LLM 通过 `tool_search` 按需发现并激活，server 连接改为懒加载（`mcp_prepare` 触发）。参考代码：`spore/server/core/agent/tools/tool_search.py`、`mcp_tool_activation.py`、`mcp_skill_activation_ctx.py`。

## Goals / Non-Goals

**Goals:**
- LLM 默认只看到 builtin 工具（tool_search、mcp_prepare 等），MCP 工具全部 deferred
- 工具激活跨轮次持久化：本会话首次激活后，后续轮次无需重新搜索
- MCP server 连接改为懒加载：只有调用 mcp_prepare 时才建立连接
- disk cache 使 tool_search 在 server 未连接时仍能找到工具元数据

**Non-Goals:**
- SSE / streamableHttp 传输（V2 仍只支持 stdio）
- Company catalog / 服务目录（公司内网专用）
- 工具审批、鉴权注入
- MCPResourceWrapper / MCPPromptWrapper

## Decisions

### 决策1：ActivatedToolSet 存在 session metadata，不新建 Session 类

**选择**：扩展 `MemoryStore`（+2个方法），在 `memory/<chat_id>/metadata.json` 存储激活集，`loop.py` 用 `dict` 缓存各 chat_id 的 metadata。

**原因**：CashCode 没有 spore 的 Session 对象。最小改动是在现有 MemoryStore 目录结构里加 metadata.json，不破坏任何现有接口。

**备选**：新建 Session dataclass。代价是需要修改 loop.py 所有引用 `self._sessions` 的地方，改动面更大。

### 决策2：ActivatedToolSet 直接持有 metadata 子dict的引用

**选择**：`ActivatedToolSet.__init__(raw: dict)` 接受 `metadata["activated_tools"]` 的直接引用，`activate()` 同时写 `self._data` 和 `self._raw`（即 metadata 原始 dict），`save()` 时只需把 metadata 整体写入 metadata.json。

**原因**：与 spore 完全一致的设计。写入即反映到 metadata dict，无需额外同步。

### 决策3：DeferredAwareRegistry 用 (full_revision, activation_revision) 作缓存 key

**选择**：`get_definitions()` 内部缓存 key = `(full_registry.membership_revision, activated_set.visibility_revision)`；任意工具被 activate 时 `visibility_revision += 1`，缓存自动失效，同一轮对话内下次 LLM 调用即可看到新激活的工具。

**原因**：这是同轮激活立即生效的关键机制，无需额外事件或回调。

### 决策4：BM25 直接搬运 spore 实现，不引入外部库

**选择**：从 spore `tool_search.py` 复制 `tokenize / _is_cjk / _camel_split / ToolSearchIndex` 约100行。

**原因**：已含 CJK bigram、camelCase 分词、热门 bias，参数已调优，零新依赖。`rank_bm25` 等库无 CJK 支持，还需额外适配。

### 决策5：mcp_cache 仅用 transport fingerprint，去掉所有版本管理

**选择**：cache key = `sha256(command+args+env+url)[:16]`，cache 内容只含 `{transport_fingerprint, cached_at, tools, resources, prompts}`，无 catalogVersion / schemaComplete 等字段。

**原因**：CashCode 无公司 catalog，版本管理毫无意义。缓存失效规则简化为：server 配置变了就重新连接并刷新缓存。

### 决策6：lazy_connect 复用 owner task 模式，不新建抽象

**选择**：`mcp.py` 新增 `lazy_connect(server_name, config, existing_handles)` 异步函数，内部调用 `establish_mcp_sessions({server_name: config})` 并将新 handle 合并进 `loop.py` 的 `self._mcp_handles`。

**原因**：owner task 模式（transport AnyIO cancel scope 必须在同一 task 内开关）已在 V1 验证可行。复用而非重写。

## Risks / Trade-offs

- **[风险] loop.py 每轮都读写 metadata.json** → 会话频繁时 I/O 小量增加。缓解：内存缓存 `self._session_metadata[chat_id]`，只在轮次结束时写磁盘（同现有 history.jsonl 模式）。
- **[风险] BM25 搜索质量** → 对英文工具名效果好，纯中文描述时 bigram 可能漏词。缓解：工具描述建议写中英双语（mock server 已示范）。
- **[trade-off] 首次使用某工具时多一轮 tool_search** → 相比 V1 多消耗一次 LLM 调用。收益：context 大幅减少，长期来看 token 总量降低。
- **[trade-off] 无 cache 时首次 mcp_prepare 较慢** → 需要建立 stdio 子进程 + 握手（~1-2s）。缓解：cache 存在后后续会话不需要重连。
