## 1. Session Metadata 存储层

- [x] 1.1 在 `server/app/memory/store.py` 新增 `_metadata_file(chat_id)` 路径方法
- [x] 1.2 在 `server/app/memory/store.py` 新增 `read_session_metadata(chat_id) -> dict` 方法：文件不存在返回 `{}`
- [x] 1.3 在 `server/app/memory/store.py` 新增 `write_session_metadata(chat_id, data: dict)` 方法：原子写入 `memory/<chat_id>/metadata.json`
- [x] 1.4 验证：写入 → 读回数据一致，文件不存在时不报错

## 2. ActivatedToolSet

- [x] 2.1 新建 `server/app/agent/tools/tool_search.py`，实现 `ActivatedToolSet` 类：`OrderedDict` LRU（容量50），`activate / touch / deactivate / is_activated / activated_names`，`visibility_revision` 在成员变化时递增
- [x] 2.2 实现 `ActivatedToolSet.from_session(metadata_dict)` 工厂方法：直接持有 `metadata_dict.setdefault("activated_tools", {})` 的引用
- [x] 2.3 在同文件实现 `use_activated_set(set)` ContextVar 上下文管理器和 `get_activated_set()` getter
- [x] 2.4 验证：activate 后 metadata dict 立即更新；超出50个时 evict 最旧；visibility_revision 在新 activate 时递增

## 3. DeferredAwareRegistry

- [x] 3.1 在 `tool_search.py` 实现 `DeferredAwareRegistry`（继承 `ToolRegistry`）：`get_definitions()` 只返回非 `mcp_` 工具 + 激活集中的 `mcp_` 工具
- [x] 3.2 实现缓存 key = `(full_registry.membership_revision, activated_set.visibility_revision if activated_set else -1)`，内容未变时直接返回缓存
- [x] 3.3 实现 `prepare_call()`：deferred 且未激活的工具返回引导错误字符串，不执行
- [x] 3.4 实现 `execute()`：deferred 已激活工具转发至 FullRegistry；执行后 `activated_set.touch(name)` 更新 LRU 时间戳
- [x] 3.5 验证：未激活 MCP 工具不出现在 definitions；activate 后下次 get_definitions 立即包含该工具

## 4. MCP 工具 Schema 磁盘缓存

- [x] 4.1 新建 `server/app/agent/tools/mcp_cache.py`，实现 `compute_transport_fingerprint(config: dict) -> str`：sha256(command+args+env+url)[:16]
- [x] 4.2 实现 `read_cache(server_name, config) -> list[dict] | None`：读文件 → 验证 fingerprint → 返回 tools 列表或 None
- [x] 4.3 实现 `write_cache(server_name, config, tools, resources=None, prompts=None)`：原子写入 `mcp_cache/<server_name>.json`（tmp→rename），含 `transport_fingerprint`、`cached_at`、`tools`、`resources`、`prompts`
- [x] 4.4 验证：write → read 返回相同数据；config 变化后 read 返回 None

## 5. ToolSearchIndex + CacheFeeder + ToolSearchTool

- [x] 5.1 在 `tool_search.py` 实现 `tokenize / _is_cjk / _camel_split / _ascii_tokens / _cjk_bigrams`（搬运 spore 实现）
- [x] 5.2 实现 `IndexDocument` dataclass 和 `ToolMeta / ServiceMeta` 数据容器
- [x] 5.3 实现 `ToolSearchIndex`：BM25（k1=1.5, b=0.75）+ 倒排索引 + `ensure_fresh(docs)` fingerprint 缓存 + `search(query, limit)` 返回 `list[(score, IndexDocument)]`
- [x] 5.4 实现 `CacheFeeder.iter_documents()`：遍历 mcp_servers 配置，`read_cache()` 读 disk + 扫描 live ToolRegistry，live 优先，返回 IndexDocument 列表（含 callable/source 标记）
- [x] 5.5 实现 `ToolSearchTool`（继承 Tool）：`execute(query, limit=8)` 调用 CacheFeeder → ensure_fresh → search → 激活 callable 命中工具 → 返回结构化结果文本（含"✅ 已激活"提示）
- [x] 5.6 验证：中文查询命中含中文描述的工具；camelCase 工具名可被英文拆分词搜索；无结果时返回友好提示

## 6. MCPPrepareTool + lazy_connect

- [x] 6.1 在 `server/app/agent/tools/mcp.py` 新增 `lazy_connect(server_name, config, handles) -> bool`：调用 `establish_mcp_sessions({server_name: config})`，将新 handle 合并进 handles dict
- [x] 6.2 在 `tool_search.py` 实现 `MCPPrepareTool`（继承 Tool）：接收 `server_name` 参数；server 已连接则跳过 lazy_connect；调用 `list_tools()` → 注册 MCPToolWrapper → write_cache → activate 所有工具 → 返回激活列表
- [x] 6.3 验证：首次 prepare 建立连接、写 cache、激活工具；重复 prepare 不重连；server_name 不存在返回错误字符串

## 7. loop.py 改造

- [x] 7.1 修改 `loop.py` 的 `__init__`：新增 `self._session_metadata: dict[str, dict] = {}`；新增 `self._mcp_config: dict = {}`（存原始配置，不建连接）
- [x] 7.2 修改 `loop.py` 的 `_setup_mcp()`：读 `mcp_config.json` 存入 `self._mcp_config`，不调用 `establish_mcp_sessions()`
- [x] 7.3 修改 `loop.py` 的 `__init__`：构建 `DeferredAwareRegistry` 包装 `self._registry`，注册 `ToolSearchTool` 和 `MCPPrepareTool` 到 `self._deferred_registry`
- [x] 7.4 修改 `loop.py` 的 `_handle_turn()`：懒加载 session metadata，绑定 `ActivatedToolSet`，轮次结束写回 metadata
- [x] 7.5 修改 `loop.py` 的 runner 调用：传 `self._deferred_registry` 替代 `self._registry`

## 8. 端到端验证

- [ ] 8.1 启动 agent，确认日志显示"MCP config loaded (lazy mode)"，无连接日志
- [ ] 8.2 发送"查一下北京天气"，确认思考栏出现 `tool_search` 调用（无任何 MCP 工具直接可见）
- [ ] 8.3 确认 tool_search 首次返回"requiresPreparation"提示，LLM 触发 `mcp_prepare`
- [ ] 8.4 确认 `mcp_prepare` 执行后：weather server 连接建立，`mcp_cache/weather.json` 生成，工具激活，LLM 调用 `mcp_weather_get_weather` 返回结果
- [ ] 8.5 重启 agent，再次发"查一下北京天气"，确认 tool_search 从 disk cache 找到工具
- [ ] 8.6 连续两轮询问天气，确认第二轮直接调用工具（不再 tool_search）
- [ ] 1.2 在 `server/app/memory/store.py` 新增 `read_session_metadata(chat_id) -> dict` 方法：文件不存在返回 `{}`
- [ ] 1.3 在 `server/app/memory/store.py` 新增 `write_session_metadata(chat_id, data: dict)` 方法：原子写入 `memory/<chat_id>/metadata.json`
- [ ] 1.4 验证：写入 → 读回数据一致，文件不存在时不报错

## 2. ActivatedToolSet

- [ ] 2.1 新建 `server/app/agent/tools/tool_search.py`，实现 `ActivatedToolSet` 类：`OrderedDict` LRU（容量50），`activate / touch / deactivate / is_activated / activated_names`，`visibility_revision` 在成员变化时递增
- [ ] 2.2 实现 `ActivatedToolSet.from_session(metadata_dict)` 工厂方法：直接持有 `metadata_dict.setdefault("activated_tools", {})` 的引用
- [ ] 2.3 在同文件实现 `use_activated_set(set)` ContextVar 上下文管理器和 `get_activated_set()` getter
- [ ] 2.4 验证：activate 后 metadata dict 立即更新；超出50个时 evict 最旧；visibility_revision 在新 activate 时递增

## 3. DeferredAwareRegistry

- [ ] 3.1 在 `tool_search.py` 实现 `DeferredAwareRegistry`（继承 `ToolRegistry`）：`get_definitions()` 只返回非 `mcp_` 工具 + 激活集中的 `mcp_` 工具
- [ ] 3.2 实现缓存 key = `(full_registry.membership_revision, activated_set.visibility_revision if activated_set else -1)`，内容未变时直接返回缓存
- [ ] 3.3 实现 `prepare_call()`：deferred 且未激活的工具返回引导错误字符串，不执行
- [ ] 3.4 实现 `execute()`：deferred 已激活工具转发至 FullRegistry；执行后 `activated_set.touch(name)` 更新 LRU 时间戳
- [ ] 3.5 验证：未激活 MCP 工具不出现在 definitions；activate 后下次 get_definitions 立即包含该工具

## 4. MCP 工具 Schema 磁盘缓存

- [ ] 4.1 新建 `server/app/agent/tools/mcp_cache.py`，实现 `compute_transport_fingerprint(config: dict) -> str`：sha256(command+args+env+url)[:16]
- [ ] 4.2 实现 `read_cache(server_name, config) -> list[dict] | None`：读文件 → 验证 fingerprint → 返回 tools 列表或 None
- [ ] 4.3 实现 `write_cache(server_name, config, tools, resources=None, prompts=None)`：原子写入 `mcp_cache/<server_name>.json`（tmp→rename），含 `transport_fingerprint`、`cached_at`、`tools`、`resources`、`prompts`
- [ ] 4.4 验证：write → read 返回相同数据；config 变化后 read 返回 None

## 5. ToolSearchIndex + CacheFeeder + ToolSearchTool

- [ ] 5.1 在 `tool_search.py` 实现 `tokenize / _is_cjk / _camel_split / _ascii_tokens / _cjk_bigrams`（搬运 spore 实现）
- [ ] 5.2 实现 `IndexDocument` dataclass 和 `ToolMeta / ServiceMeta` 数据容器
- [ ] 5.3 实现 `ToolSearchIndex`：BM25（k1=1.5, b=0.75）+ 倒排索引 + `ensure_fresh(docs)` fingerprint 缓存 + `search(query, limit)` 返回 `list[(score, IndexDocument)]`
- [ ] 5.4 实现 `CacheFeeder.iter_documents()`：遍历 mcp_servers 配置，`read_cache()` 读 disk + 扫描 live ToolRegistry，live 优先，返回 IndexDocument 列表（含 callable/source 标记）
- [ ] 5.5 实现 `ToolSearchTool`（继承 Tool）：`execute(query, limit=8)` 调用 CacheFeeder → ensure_fresh → search → 激活 callable 命中工具 → 返回结构化结果文本（含"✅ 已激活"提示）
- [ ] 5.6 验证：中文查询命中含中文描述的工具；camelCase 工具名可被英文拆分词搜索；无结果时返回友好提示

## 6. MCPPrepareTool + lazy_connect

- [ ] 6.1 在 `server/app/agent/tools/mcp.py` 新增 `lazy_connect(server_name, config, handles) -> bool`：调用 `establish_mcp_sessions({server_name: config})`，将新 handle 合并进 handles dict
- [ ] 6.2 在 `tool_search.py` 实现 `MCPPrepareTool`（继承 Tool）：接收 `server_name` 参数；server 已连接则跳过 lazy_connect；调用 `list_tools()` → 注册 MCPToolWrapper → write_cache → activate 所有工具 → 返回激活列表
- [ ] 6.3 验证：首次 prepare 建立连接、写 cache、激活工具；重复 prepare 不重连；server_name 不存在返回错误字符串

## 7. loop.py 改造

- [ ] 7.1 修改 `loop.py` 的 `__init__`：新增 `self._session_metadata: dict[str, dict] = {}`；新增 `self._mcp_config: dict = {}`（存原始配置，不建连接）
- [ ] 7.2 修改 `loop.py` 的 `_setup_mcp()`：读 `mcp_config.json` 存入 `self._mcp_config`，从 disk cache 加载已有工具 schema 注册为 callable=false 的占位 wrapper（供 CacheFeeder 用）；不调用 `establish_mcp_sessions()`
- [ ] 7.3 修改 `loop.py` 的 `__init__`：构建 `DeferredAwareRegistry` 包装 `self._registry`，存为 `self._deferred_registry`；注册 `ToolSearchTool` 和 `MCPPrepareTool` 到 `self._registry`（非 deferred）
- [ ] 7.4 修改 `loop.py` 的 `_handle_turn()`：开始时懒加载 `self._session_metadata[chat_id]`；通过 `ActivatedToolSet.from_session(self._session_metadata[chat_id])` 构建激活集；在 `use_activated_set(activated_set)` 上下文内执行 runner；结束时调用 `store.write_session_metadata(chat_id, self._session_metadata[chat_id])`
- [ ] 7.5 修改 `loop.py` 的 runner 调用：传 `self._deferred_registry` 替代 `self._registry`

## 8. 端到端验证

- [ ] 8.1 启动 agent，确认日志显示"no MCP connections at startup"，`self._mcp_handles` 为空
- [ ] 8.2 发送"查一下北京天气"，确认思考栏出现 `tool_search` 调用（无任何 MCP 工具直接可见）
- [ ] 8.3 确认 tool_search 首次返回"requiresPreparation"提示（无 disk cache 时），触发 `mcp_prepare`
- [ ] 8.4 确认 `mcp_prepare` 执行后：weather server 连接建立，`mcp_cache/weather.json` 生成，工具激活，LLM 调用 `mcp_weather_get_weather` 返回结果
- [ ] 8.5 重启 agent，再次发"查一下北京天气"，确认 tool_search 直接从 disk cache 找到工具（无需重新 prepare），`mcp_weather_get_weather` 仍需 mcp_prepare 建立连接后可调用
- [ ] 8.6 连续两轮询问天气，确认第二轮直接调用 `mcp_weather_get_weather`（从激活集里取，不再 tool_search）
