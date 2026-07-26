[English](README.md) | 简体中文

# CashCode

CashCode 是一个本地运行的个人 AI Agent 框架，参考了Codex、Hermes、OpenClaw来实现。支持跨会话持久记忆、本地 Skill、MCP 工具体系和流式对话等功能。

---

## 功能概览

| 模块 | 功能 |
|---|---|
| WebSocket 通信 | 流式对话、工具事件通知 |
| 记忆体系 | 跨会话持久化、上下文压缩、长期记忆提炼 |
| 工具调用 | ReAct 循环、内置工具与动态工具 |
| Agent 人格 | SOUL.md 驱动的可配置身份 |
| MCP 体系 | 内置/用户目录、市场管理、显式连接、延迟激活、stdio/SSE 传输 |
| Skill 体系 | 自然语言搜索、两阶段懒加载、Session 摘要、管理 API、自进化提案 |

---

## 架构总览

```
                    用户（前端 WebSocket 客户端）
                              │
                    WebSocketChannel
                    (ws://127.0.0.1:8765)
                              │
                         MessageBus
                    (asyncio 队列解耦)
                              │
                    SimpleAgentLoop
              ┌───────────────┴───────────────┐
              │                               │
      ToolRegistry (内置)         DeferredAwareRegistry
      save_memory, web_fetch     (MCP 工具默认隐藏)
      skill_search/load/read     ├── tool_search → 发现 MCP 工具
      tool_search, mcp_prepare   ├── mcp_prepare → 懒连接
              │                  └── skill_search/load → 懒加载 Skill
              │
              ▼
    SimpleAgentRunner（ReAct 非流式循环）
              │
    ┌─────────┴──────────┐
    │                    │
内置工具执行         MCP 工具执行
    │              MCPToolWrapper
    │           session.call_tool()
    │               │
    │           MCP server（stdio/SSE）
    │
    ▼
fake streaming → 前端
              │
        MemoryStore
  ┌─────────────────────┐
  │  history.jsonl      │  ← 对话历史
  │  metadata.json      │  ← 激活集等跨轮次状态（V2新增）
  │  MEMORY.md          │  ← 全局长期记忆
  │  SOUL.md            │  ← Agent 人格配置
  └─────────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
 Consolidator           Dream
(上下文压缩)        (长期记忆提炼)
```

---

## 目录结构

```
CashCode/
├── server/
│   ├── main.py                    # FastAPI + WebSocket 服务入口
│   ├── .env                       # 可选的非 LLM 环境变量配置
│   ├── requirements.txt
│   ├── data/                      # Skill、用户 MCP 与自进化运行数据（不提交 git）
│   │   ├── mcp/servers.json       # 用户创建的 SSE MCP 配置
│   │   └── skills/
│   │       ├── user/              # 用户上传和管理的 Skill
│   │       └── agent/             # 聊天/Agent 创建的 Skill
│   ├── memory/                    # 运行时记忆数据（不提交 git）
│   │   ├── SOUL.md                # Agent 人格文件（提交 git）
│   │   ├── MEMORY.md              # 全局长期记忆（运行时生成）
│   │   ├── .dream_cursor          # Dream 游标（运行时生成）
│   │   └── <chat_id>/             # 各会话历史目录
│   │       ├── history.jsonl
│   │       ├── metadata.json      # 激活集等跨轮次状态（V2）
│   │       └── .cursor
│   └── app/
│       ├── agent/
│       │   ├── loop.py            # SimpleAgentLoop 主循环（含 MCP 初始化）
│       │   ├── runner.py          # SimpleAgentRunner ReAct 循环
│       │   └── tools/
│       │       ├── base.py        # Tool 抽象基类
│       │       ├── registry.py    # ToolRegistry 工具注册表
│       │       ├── mcp.py         # MCP 连接层（stdio/SSE + MCPToolWrapper）
│       │       ├── mcp_cache.py   # 工具 schema 磁盘缓存
│       │       ├── tool_search.py # 延迟激活体系（DeferredAwareRegistry,
│       │       │                  # ActivatedToolSet, ToolSearchTool,
│       │       │                  # MCPPrepareTool, BM25 索引）
│       │       ├── memory.py      # SaveMemoryTool
│       │       ├── web.py         # WebFetchTool, WebSearchTool
│       │       ├── filesystem.py  # ReadFileTool, WriteFileTool...
│       │       ├── search.py      # GlobTool, GrepTool
│       │       ├── shell.py       # ExecTool
│       │       └── result.py      # 工具结果的模型/前端/持久化投影
│       ├── skills/                # Skill 目录、加载、管理和自进化实现
│       │   ├── archive.py         # ZIP 安全校验与解包
│       │   └── builtin/           # 只读内置 Skill（提交 git）
│       ├── api/
│       │   ├── skills.py          # Skill 管理 API
│       │   ├── mcp.py             # MCP 市场、CRUD 与连接 API
│       │   └── skill_evolution.py # Skill 自进化提案 API
│       ├── memory/
│       │   ├── store.py           # MemoryStore（含 session metadata）
│       │   ├── consolidator.py    # 上下文压缩
│       │   └── dream.py           # 长期记忆提炼
│       ├── ws/
│       │   └── channel.py         # WebSocketChannel
│       └── bus/
│           ├── queue.py           # MessageBus
│           └── events.py          # InboundMessage, OutboundMessage
├── mcp_servers/                   # 内置 MCP 配置与测试服务（白名单提交）
│   ├── mcp_config.json            # MCP server 配置（stdio/SSE）
│   ├── test_stdio_mcp/
│   │   └── server.py              # stdio 测试服务（say_hello）
│   └── test_sse_mcp/
│       └── server.py              # SSE 测试服务（say_hello）
├── mcp_cache/                     # 工具 schema 磁盘缓存（不提交 git）
└── openspec/                      # 变更管理
    ├── specs/                     # 主规范文档
    └── changes/archive/           # 已归档的变更记录
```

---

## 一、WebSocket 通信协议

服务在 `ws://127.0.0.1:8765` 监听，HTTP API 在 `http://127.0.0.1:8000`。

### 客户端 → 服务端

```json
{"type": "message", "chat_id": "uuid", "content": "用户消息"}
{"type": "message", "chat_id": "uuid", "content": "检查仓库", "metadata": {"mentioned_skills": [{"name": "code-review", "label": "代码审查"}], "selected_mcp_connectors": [{"server": "github", "label": "GitHub"}]}}
{"type": "ping"}
{"type": "new_chat"}
{"type": "attach", "chat_id": "uuid"}
{"type": "cancel", "chat_id": "uuid"}
```

### 服务端 → 客户端

```json
{"event": "ready",       "chat_id": "...", "client_id": "..."}
{"event": "tool_call",   "chat_id": "...", "tool_name": "web_fetch", "stream_id": 123}
{"event": "tool_result", "chat_id": "...", "tool_name": "web_fetch", "result": "...", "stream_id": 123}
{"event": "delta",       "chat_id": "...", "text": "...", "stream_id": 123}
{"event": "stream_end",  "chat_id": "...", "stream_id": 123}
{"event": "done",        "chat_id": "...", "duration_sec": 2.3}
{"event": "error",       "detail": "..."}
```

### 架构说明

`MessageBus` 是一个 asyncio 队列，将 WebSocket 通道与 Agent 循环解耦。WebSocketChannel 把客户端帧转换为 `InboundMessage` 投入队列，`SimpleAgentLoop` 消费队列并将 `OutboundMessage` 路由回 WebSocketChannel 发给订阅者。

---

## 二、记忆体系

记忆体系采用三层设计，从短期到长期：

```
InboundMessage
      │
      ▼
 history.jsonl      ← Layer 1：原始对话流（append-only）
      │
      ▼
  Consolidator      ← Layer 2：上下文压缩（每轮，字符数触发）
      │
      ▼
  Dream             ← Layer 3：长期记忆提炼（定时，5分钟）
      │
      ▼
  MEMORY.md         ← 全局长期记忆（注入 system prompt）
```

### Layer 1：MemoryStore（`store.py`）

每个 `chat_id` 对应一个子目录，`history.jsonl` 是追加式的对话流水账：

```jsonl
{"cursor": 1,  "role": "user",       "content": "你好"}
{"cursor": 2,  "role": "assistant",  "content": "你好！"}
{"cursor": 3,  "role": "tool_calls", "content": "[TOOL_CALLS: web_fetch]", "tool_calls": [...]}
{"cursor": 4,  "role": "tool",       "content": "抓取结果...", "tool_call_id": "call_xxx"}
{"cursor": 5,  "role": "assistant",  "content": "根据网页内容..."}
{"cursor": 6,  "role": "summary",    "content": "摘要...", "keep_from_cursor": 3}
```

**重启恢复（Smart Load）**：`load_history_smart()` 找到最后一条 `summary` 记录，读取其 `keep_from_cursor` 字段，只加载摘要 + `cursor >= keep_from_cursor` 的近期消息，避免重启后把已压缩的旧消息再次送入 Consolidator。

**全局文件**：
- `SOUL.md` — Agent 人格（提交 git）
- `MEMORY.md` — 跨会话长期记忆（运行时生成）
- `.dream_cursor` — JSON，记录每个 chat_id 被 Dream 处理到的 cursor 位置

### Layer 2：SimpleConsolidator（`consolidator.py`）

每轮对话结束后触发，超过字符阈值（默认 40,000）时压缩旧消息：

```
策略：累计压缩（不是增量）
  to_compress = history[:keep_from]  含已有摘要前缀
  to_keep     = history[keep_from:]  保留最近 50% 字符量的消息

压缩后 history（in-memory）：
  [累计摘要] + [to_keep 消息]

history.jsonl 追加：
  {"role": "summary", "keep_from_cursor": N, ...}
```

**关键设计**：
- **累计压缩**：每次摘要包含前一次摘要的内容，重启后只需最后一条 summary 即可恢复完整上下文
- **keep_from_cursor 元数据**：记录 to_keep 第一条消息的 cursor，Smart Load 据此准确恢复 to_keep 消息（避免 to_keep 消息因 cursor 小于 summary 而被丢弃）
- **原子持久化**：先写 history.jsonl，成功后才更新内存 history（失败时回滚，保持一致性）
- **per-chat-id asyncio.Lock**：防止同一会话的并发请求导致重复压缩

### Layer 3：SimpleDream（`dream.py`）

每5分钟在后台运行（通过 `asyncio.create_task`），两阶段 LLM 处理：

```
Phase 1：分析
  输入：所有 chat_id 的未处理 history 条目 + 当前 MEMORY.md
  输出：分析报告（应新增/更新/删除哪些长期记忆）

Phase 2：生成
  输入：Phase 1 报告 + 当前 MEMORY.md
  输出：完整的新 MEMORY.md（写入文件）
```

每次运行后推进各 chat_id 的 dream cursor（`memory/.dream_cursor`），下次只处理新增的条目。

### MEMORY.md 注入方式

每轮对话构建 system prompt 时：

```python
soul    = store.read_soul() or _DEFAULT_SOUL  # SOUL.md 或内置默认
memory  = store.read_memory()                  # MEMORY.md（若有）

system_prompt = soul
if memory:
    system_prompt += f"\n\n## 你已经记住的信息\n{memory}"
```

---

## 三、工具调用体系

### 架构：两阶段执行

```
用户消息
    │
    ▼
Phase 1: SimpleAgentRunner（非流式 ReAct 循环）
    │
    ├── LLM 调用 tools=[...] stream=False
    │     │
    │     ├── 有 tool_calls → WS 发送 tool_call 事件
    │     │                 → 执行工具
    │     │                 → WS 发送 tool_result 事件
    │     │                 → 追加结果 → 再次调用 LLM
    │     │
    │     └── 无 tool_calls → 返回 final_text
    │
    ▼
Phase 2: fake streaming
    将 final_text 切成 15 字符/块发给前端（_stream_delta 事件）
    前端体验与真实流式相同
```

工具链完整写入 `history.jsonl`（user → tool_calls → tool_result → assistant），重启后可恢复完整工具调用上下文。

### Tool 基类（`tools/base.py`）

```python
class Tool(ABC):
    @property
    def name(self) -> str: ...         # 工具名，对应 tool_call.function.name
    @property
    def description(self) -> str: ... # LLM 据此决定是否调用
    def parameters(self) -> dict: ... # OpenAI JSON Schema 格式的参数定义
    def to_openai_schema(self) -> dict: ...  # 组装成 API 需要的格式
    async def execute(self, **kwargs) -> str: ...  # 执行，返回结果字符串
```

### 内置工具列表

| 工具名 | 类 | 说明 |
|---|---|---|
| `save_memory` | SaveMemoryTool | 即时将重要事实写入 MEMORY.md |
| `web_fetch` | WebFetchTool | 抓取 URL 网页内容（httpx，最多3000字符）|
| `web_search` | WebSearchTool | DuckDuckGo Instant Answer API 搜索 |
| `read_file` | ReadFileTool | 读取 WORKSPACE_DIR 内文件（最多500行）|
| `write_file` | WriteFileTool | 创建或覆盖 WORKSPACE_DIR 内文件 |
| `edit_file` | EditFileTool | 精确字符串替换（old→new，要求唯一）|
| `list_dir` | ListDirTool | 列出目录内容（含类型标记）|
| `glob` | GlobTool | 按文件名模式查找（`**/*.py`，最多100条）|
| `grep` | GrepTool | 正则搜索文件内容（最多50条）|
| `exec` | ExecTool | 在 WORKSPACE_DIR 内执行 shell 命令（30s超时）|

---

## 四、MCP 体系

CashCode 实现了完整的 MCP（Model Context Protocol）体系，支持将外部 MCP server 的工具无缝接入 Agent。

### MCP 市场与配置来源

左侧栏的 `MCP 市场` 会合并显示两类配置：

- `mcp_servers/mcp_config.json` 是随项目提供的只读内置目录，支持 stdio 和 SSE；市场中标记为 `内置`，允许连接或断开，但不能编辑、删除。
- `CASHCODE_DATA_DIR/mcp/servers.json` 是用户目录，默认位于 `server/data/mcp/servers.json`；用户可以在市场中新建、编辑和删除，目前只支持 SSE。

用户 MCP 包含内部名称、显示标题、描述、HTTP(S) SSE 地址和可选 Headers。Headers 的实际值保存在本地用户数据文件中，不承诺静态加密；API 和编辑表单只返回 `********`，提交该占位符会保留原值。连接错误、工具信息与聊天历史不会返回 Header 值。

新建或编辑配置不会自动连接。点击 `连接` 后，服务端完成传输握手和 `list_tools` 才会显示为已连接；`断开` 会关闭传输并移除该服务拥有的实时工具。连接失败会在市场中显示可重试的脱敏错误。

| API | 说明 |
|---|---|
| `GET/POST /api/mcp/servers` | 查询合并目录或创建用户 SSE MCP |
| `PUT/DELETE /api/mcp/servers/{name}` | 编辑或删除用户 MCP；内置项返回 403 |
| `POST /api/mcp/servers/{name}/connect` | 显式连接并发现工具 |
| `POST /api/mcp/servers/{name}/disconnect` | 显式断开并清理实时工具 |
| `GET /api/mcp/servers/{name}/tools` | 查询实时工具或配置指纹有效的缓存信息 |

### 在聊天中选择 MCP 或 Skill

在聊天输入框的词元边界输入 `@`，先选择 `MCP` 或 `Skill`，再从当前可用列表中搜索并选择。MCP 列表只包含已连接且发现了实时工具的服务，Skill 列表只包含已启用且依赖可用的 Skill。选择结果显示为可移除芯片，一条消息最多合计选择 8 项，正文不能为空。

选择通过 WebSocket 结构化 metadata 发送，不会拼接到任务正文。显式选择的 MCP 工具权限只对当前轮生效，但市场建立的传输会保持连接，直到用户断开、编辑、删除或服务退出。Skill/MCP 引用会随用户消息写入历史并在重新打开会话后恢复。开头的旧式 `@<skill>` 文本语法仍保留兼容。

### 核心设计：延迟激活（Deferred Activation）

直接把所有工具暴露给 LLM 会撑爆 context。CashCode 采用**延迟激活**机制：

```
LLM 默认只看到：                 MCP 工具默认隐藏：
  tool_search  ← 搜索工具           mcp_test_stdio_mcp_say_hello ✗
  mcp_prepare  ← 按需连接           mcp_test_sse_mcp_say_hello   ✗
  save_memory
  web_fetch    ...

用户要求「调用 stdio 测试 MCP」
    ↓
LLM 调用 tool_search("stdio Hello Cash")
    ↓ BM25 搜索命中 stdio 测试服务存根
LLM 调用 mcp_prepare("test_stdio_mcp")
    ↓ 建立 stdio 连接 → list_tools → 激活
LLM 调用 mcp_test_stdio_mcp_say_hello()
    ↓
返回 "Hello, Cash"（下次可直接调用，跳过搜索）
```

### 架构分层

```
┌──────────────────────────────────────────────────────────┐
│  DeferredAwareRegistry（对 LLM 的视图层）                  │
│  - 内置工具（tool_search, mcp_prepare, 文件/Web等）永远可见│
│  - MCP 工具：默认隐藏，activate 后立即可见（同轮生效）       │
│  - 缓存 key 含 activation_revision，激活后缓存自动失效       │
├──────────────────────────────────────────────────────────┤
│  ActivatedToolSet（会话状态层）                             │
│  - LRU dict，容量 50，{tool_name: timestamp}               │
│  - ContextVar 绑定到当前 async task，跨层传递               │
│  - 持久化到 memory/<chat_id>/metadata.json，重启不丢失       │
├──────────────────────────────────────────────────────────┤
│  ToolSearchTool + ToolSearchIndex（发现层）                 │
│  - BM25（k1=1.5, b=0.75）+ CJK bigram + camelCase 分词    │
│  - CacheFeeder：合并 disk cache（callable=false）          │
│    + live registry（callable=true），live 优先              │
│  - 无工具时生成服务级存根，引导 LLM 调用 mcp_prepare        │
├──────────────────────────────────────────────────────────┤
│  mcp_cache.py（离线缓存层）                                 │
│  - 每个 server 一个 JSON 文件（mcp_cache/<name>.json）     │
│  - transport fingerprint 失效（command/args/url 变化自动刷新）│
│  - mcp_prepare 连接成功后写入，重启后 tool_search 可直接搜索 │
├──────────────────────────────────────────────────────────┤
│  MCPPrepareTool + lazy_connect（连接层）                   │
│  - 调用 lazy_connect → establish_mcp_sessions             │
│  - stdio：spawn 子进程；SSE：连接 HTTP 端点               │
│  - 握手 → list_tools → 注册 MCPToolWrapper → write_cache  │
├──────────────────────────────────────────────────────────┤
│  MCPToolWrapper（适配层）                                  │
│  - 对外：实现 Tool 接口（name/description/execute）        │
│  - 对内：session.call_tool(original_name, arguments)      │
│  - 命名：mcp_{server_name}_{tool_name}                    │
└──────────────────────────────────────────────────────────┘
```

### 两种传输协议

| 传输 | 配置 | server 启动方式 | 典型场景 |
|---|---|---|---|
| **stdio** | `command + args` | 无需独立启动；`mcp_prepare` 时由 CashCode 拉起 | 本地命令行工具 |
| **SSE** | `url` | 需**独立启动** HTTP 服务 | 公网 MCP 服务、第三方 API |

```json
// mcp_servers/mcp_config.json
{
  "test_stdio_mcp": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp_servers/test_stdio_mcp/server.py"],
    "display_name": "stdio 测试 MCP",
    "description": "提供返回 Hello, Cash 的 say_hello 工具"
  },
  "test_sse_mcp": {
    "type": "sse",
    "url": "http://127.0.0.1:8090/sse",
    "display_name": "SSE 测试 MCP",
    "description": "提供返回 Hello, Cash 的 say_hello 工具；需要单独启动服务"
  }
}
```

### 本地测试 MCP 服务

| Server | 传输 | 工具 | 启动方式 |
|---|---|---|---|
| `test_stdio_mcp` | stdio | `say_hello()` → `Hello, Cash` | `mcp_prepare` 自动拉起 |
| `test_sse_mcp` | SSE | `say_hello()` → `Hello, Cash` | 需手动启动 |

```bash
# 使用 SSE server 前需先启动（独立终端）
python mcp_servers/test_sse_mcp/server.py
```

### 完整会话流程

```
1. agent 启动（lazy mode）
   → 读 mcp_config.json，不建任何连接
   → 有 disk cache 时，tool_search 可直接搜索（即使未连接）

2. 用户要求调用 stdio 测试 MCP
   → tool_search("stdio Hello Cash") 搜到 test_stdio_mcp 服务存根
   → 提示需先调用 mcp_prepare("test_stdio_mcp")

3. mcp_prepare("test_stdio_mcp")
   → 启动 stdio 子进程
   → list_tools → 注册 MCPToolWrapper → write mcp_cache
   → activate mcp_test_stdio_mcp_say_hello

4. mcp_test_stdio_mcp_say_hello()
   → 返回 "Hello, Cash"

5. 下轮再次调用该测试能力
   → DeferredAwareRegistry 发现工具已在 ActivatedToolSet
   → 直接调用，跳过 tool_search（激活集跨轮次持久化）
```

---

## 五、Skill 体系

CashCode 在服务端提供本地 Skill 运行时。模型始终可见 `skill_search`、`skill_load`、`skill_read_resource` 和受管的 `agent_skill_manage`，但系统不会把所有已安装 Skill 的描述或正文一次性注入上下文。

### 存储目录

`CASHCODE_DATA_DIR` 默认指向 `server/data`，目录结构如下：

```text
skills/user/          用户管理的 Skill 包
skills/agent/         聊天创建或审批通过后由 Agent 持有的 Skill 包
skill-snapshots/      replace、rollback 和 invalid 删除使用的恢复快照
skill-evolution/      自进化证据与提案
```

内置 Skill 位于 `server/app/skills/builtin`，运行时只读。有效命名空间按 `builtin < user < agent` 处理，同名高优先级包会遮蔽低优先级包，并在目录元数据中暴露遮蔽来源。

### Skill 包格式

每个 Skill 是一个包含 `SKILL.md` 的目录，还可按需包含 `references/`、`templates/`、`scripts/` 和 `assets/`。目录名必须与 frontmatter 的 canonical `name` 一致。`name` 只允许 1-64 位小写字母、数字、点、下划线和连字符，用于目录、API 路由、搜索精确身份、`@` 选择、冲突判断、hash 和快照；可选 `display_name` 最多 80 个字符，仅用于市场和聊天选择器中的显示标签。

```yaml
---
name: example-workflow
display_name: 示例工作流
description: 描述该能力以及应该在什么场景使用
version: 1
tags: [example]
triggers: [example request]
requires:
  tools: [read_file]
  mcp_servers: []
  bins: []
  env: []
optional:
  tools: []
  mcp_servers: []
---
```

加载器会校验 YAML 字段类型、名称、UTF-8 编码、文件大小、支持目录和路径边界，并拒绝绝对路径、`..` 穿越与逃逸包目录的符号链接。Skill 被加载时不会自动执行脚本、安装二进制、修改环境变量、进行认证或启动未声明的 MCP。

### Skill 市场、上传与编辑

左侧栏的 `Skill 市场` 会分页显示当前有效目录中的内置、用户上传和聊天/Agent 创建 Skill。列表使用 `display_name` 作为主标签，并保留 canonical `name` 作为稳定身份。列表保留已禁用和缺少依赖的项目，便于重新启用或排查；内置项标记为 `内置`，只能查看，不能编辑、禁用或删除。用户和 Agent Skill 可以查看完整 `SKILL.md`、编辑、启用/禁用和确认删除。

上传入口只接受一个 ZIP Skill 包。ZIP 可以在根目录直接包含 `SKILL.md`，也可以使用一个顶层包装目录；最终目录名由经过校验的 frontmatter `name` 决定。服务端限制压缩包为 10 MiB、成员数为 256、解压后总量为 20 MiB，并继续应用 `SKILL.md` 80 KB、单个支持文件 200 KB 的限制。路径穿越、盘符路径、重复路径、加密成员、符号链接和特殊文件会被拒绝。

上传包始终写入 `skills/user/`，归档中的 `_meta.json` 不能声明内置或 Agent 所有权。同名包只要存在于 `builtin`、`user` 或 `agent` 任一目录都会返回 `409`，不会覆盖或遮蔽已有 Skill。解包和完整校验在隐藏临时目录中完成，通过后才原子发布并刷新运行中 catalog。

用户在聊天中明确要求创建 Skill 时，Agent 会先加载内置 `skill-creator`，再调用 `agent_skill_manage(action=create)`。该工具强制写入 `skills/agent/` 并启用包，在创建目录之前使用 catalog 相同的 loader 校验完整内容，再通过共享 `SkillStore` 完成跨根重名检查、原子发布和 catalog 刷新；只有返回 `success=true` 且同名、同 hash、`source=agent` 的记录已经可见时才算成功。校验失败时 Agent 只能修正内容后重试该管理工具或报告失败。通用 `write_file` 和 `edit_file` 会拒绝 user/agent Skill 根，创建流程也不得使用 `exec`、`curl` 或临时 HTTP 请求绕过管理工具。

Python 工具注册和内置 `skill-creator` 合约只在服务启动时加载。更新服务端代码后必须重启 CashCode；旧进程不会自动获得 `agent_skill_manage` 或目录写保护，历史版本可能仍尝试 `write_file/exec`，不能用旧进程验证新的创建链路。

无效目录不会进入搜索、`@` 选择或正常 Skill 列表。市场会在独立诊断区显示经过脱敏和限长的来源、目录名与错误信息；诊断行不能查看内容、编辑、启停或选择。user/agent 来源提供显式删除按钮，确认后服务端会再次校验目标仍然无效，再把整个目录移到 `skill-snapshots/invalid/<source>/...` 并刷新 catalog；内置来源没有删除按钮。系统不会自动迁移、改写或删除 legacy 包。

若 legacy 包（例如 `server/data/skills/user/renzhi-niuqu`）因 frontmatter 使用 `name: 认知扭曲` 而无效，可选择一种显式修复方式：保留目录时先停止服务，将 `name` 改为与目录一致的 `renzhi-niuqu`，再添加 `display_name: 认知扭曲` 并检查包根只含允许的文件，随后重启；放弃旧包时可直接在市场确认删除，目录会保存在 invalid 恢复快照中。只要旧目录仍存在于活动根，上传和聊天创建同名 Skill 都会返回冲突，防止静默覆盖。

市场编辑器第一版只修改完整 `SKILL.md`，不支持重命名，也不逐文件编辑 `references/`、`templates/`、`scripts/` 或 `assets/`。保存请求携带读取时的内容 hash；发生并发修改时返回 `409` 并保留当前草稿。保存会创建版本快照，未提交的支持文件会原样复制，因此二进制资产不会被文本编码改写。

### 搜索、加载与上下文生命周期

自然语言调用采用两阶段懒加载：

```text
用户问题
  → skill_search(query)        搜索 canonical/display 名称、描述、标签和触发词
  → skill_load(exact_name)     校验后把完整 SKILL.md 注入当前 Turn
  → skill_read_resource(...)   工作流需要时再读取单个支持文件
  → 业务工具
  → final content
```

消息开头可使用 `@name` 精确选择 Skill。`@name` 只跳过搜索，不会绕过 enabled 状态、格式、安全和依赖校验。完整 Skill 正文与支持文件只存在于当前 Turn；历史仅保存 `[Skill loaded: ...]` 和 `[Skill resource read: ...]` receipt。

Session metadata 中的 `activated_skills` 是有界 LRU 摘要，只包含名称、简短描述、版本、内容 hash 和最后使用时间。后续 Turn 可看到近期 Skill 提示，但必须再次调用 `skill_load` 才能获得完整指令。Skill 被删除、禁用或 hash 变化后，旧摘要不会被当作已加载正文使用。

### MCP 依赖联动

`requires.mcp_servers` 中的必需 MCP 只在 `skill_load` 后通过现有懒连接机制准备，并在同一 Turn 的下一次 ReAct 迭代中暴露相应工具。`optional.mcp_servers` 只报告状态，不会在加载时连接。正文中出现但未在 frontmatter 声明的 `mcp_*` 名称不能触发连接或获得激活权限。

### 管理 API

服务提供以下 REST API：

| API | 说明 |
|---|---|
| `GET/POST /api/skills` | 分页查询或创建 Skill |
| `GET/PUT/DELETE /api/skills/{name}` | 查看、替换或删除 Skill |
| `POST /api/skills/import` | 安全导入单个用户 Skill ZIP |
| `GET /api/skills/{name}/content` | 读取完整 `SKILL.md`、hash、来源和可变状态 |
| `DELETE /api/skills/invalid/{source}/{directory}` | 重新校验并快照删除无效 user/agent 包 |
| `POST /api/skills/{name}/validate` | 重新校验 Skill 包 |
| `PATCH /api/skills/{name}/enabled` | 启用或禁用可变 Skill |
| `GET /api/skills/{name}/versions` | 查询版本快照 |
| `POST /api/skills/{name}/rollback/{version}` | 原子回滚到指定版本 |

内置 Skill 不允许修改。用户和 Agent Skill 的写操作统一经过名称、内容、路径、hash 前置条件和原子替换校验；替换及回滚前会保留快照。默认的用户/Agent Skill 与用户 MCP 配置都位于 `server/data/`，不会进入 Git；`server/app/skills/builtin/` 和 `mcp_servers/` 白名单中的内置测试资源会被追踪。

### Skill 自进化预览

自进化默认关闭，可通过在server/.env中添加环境变量启用提案生成：

```ini
SKILL_EVOLUTION_ENABLED=true

# 以下是默认值
SKILL_EVOLUTION_MIN_TOOL_CALLS=2
SKILL_EVOLUTION_RECURRENCE=2
```

一个 Turn 只有同时满足以下条件，才会成为自进化证据：

- Evolution 已开启。
- Turn 已成功完成并持久化。
- 本轮至少调用 `SKILL_EVOLUTION_MIN_TOOL_CALLS` 次工具，默认至少 2 次。
- 本轮没有工具调用错误。
- 本轮没有达到 Runner 最大迭代次数。

证据进入提案生成还需要满足重复门槛：具有相同流程指纹的证据至少出现 `SKILL_EVOLUTION_RECURRENCE` 次，默认至少 2 次。流程指纹由规范化后的用户输入和本轮使用的工具名称集合生成。

符合条件的 Turn 只会贡献经过截断和脱敏的证据。重复门槛达到后，受限 Evolver 只能读取有界 Skill 摘要和 `skill-creator` 合约，并创建待审提案，不能直接访问通用文件系统、Shell、Web、MCP 或修改 Skill。

提案通过 `/api/skill-evolution/proposals` 查询、审批或拒绝，永不自动应用。审批时会重新检查所有权、base hash 和完整包校验，只允许创建或修改 `agent` Skill，不能修改内置或用户 Skill；应用前会创建版本快照，之后可通过版本 API 回滚。

---

## 六、SOUL.md — Agent 人格配置

`server/memory/SOUL.md` 定义 Agent 的身份和行为规则。直接编辑此文件即可调整 Agent 风格，无需修改代码，重启服务生效。

文件不存在时自动回落到代码内的 `_DEFAULT_SOUL` 默认字符串。

---

## 七、快速启动

### 环境准备

```bash
cd server
pip install -r requirements.txt
```

### LLM 配置

后端不要求预先创建 `.env`，也会在尚未配置模型服务时正常启动。启动前后端后，在左侧栏底部打开 `设置` → `LLM 设置`，保存连接信息：

- `通用 API`：API Base URL 和 API Key，支持 OpenAI-compatible 接口。
- `Ollama`：Ollama 服务地址，例如 `http://127.0.0.1:11434`。

模型不在设置页激活或保存。返回对话页后，在发送箭头左侧的模型列表中选择本轮使用的模型；列表会分别发现已配置的通用 API 和 Ollama 模型。每条消息携带自己的提供方和模型选择，切换模型不会修改密钥配置。

首次有效保存时，CashCode 会自动创建仅供当前用户使用的 `settings/llm.json`。默认文件位于 Git 工作区之外：

- Windows：`%LOCALAPPDATA%\CashCode\settings\llm.json`
- macOS：`~/Library/Application Support/CashCode/settings/llm.json`
- Linux：`$XDG_CONFIG_HOME/cashcode/settings/llm.json`，未设置 XDG 时使用 `~/.config/cashcode/settings/llm.json`

API 查询不会返回已保存的密钥。测试或受管部署可以通过 `CASHCODE_CONFIG_DIR` 指定配置根目录；若将其指向项目内的 `server/data`，该目录及 LLM 密钥 fallback 已被 `.gitignore` 排除。

旧版本用户在新配置文件不存在时，现有 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_API_BASE` 会被一次性迁移到新文件；`DEEPSEEK_MODEL` 不再迁移，因为模型由对话输入框选择。迁移不会修改 `.env`；新文件创建后，LLM 配置不再读取这些旧变量。

### 可选运行配置

以下非 LLM 参数可以通过进程环境或可选的 `server/.env` 覆盖；不配置时均使用默认值：

```ini
WS_HOST=127.0.0.1
WS_PORT=8765
CASHCODE_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

# 文件系统工具和 exec 工具的工作目录（默认为服务启动目录）
# WORKSPACE_DIR=/your/workspace/path
# CASHCODE_DATA_DIR=/your/runtime/data/path
# CASHCODE_CONFIG_DIR=/your/private/config/path

# 持久化运行日志（以下为默认值）
# CASHCODE_LOG_DIR=logs
CASHCODE_FILE_LOG_LEVEL=DEBUG
CASHCODE_CONSOLE_LOG_LEVEL=INFO
CASHCODE_LOG_RETENTION_DAYS=10
```

### 运行日志与测试输出

后端默认以 UTF-8 追加写入 `server/logs/cashcode.log`。本地时间跨过午夜后的第一条记录会触发轮转，保留当天和此前 9 天，共 10 个日历日。相对路径形式的 `CASHCODE_LOG_DIR` 始终以 `server/` 为基准，不受进程工作目录影响；运行日志无法创建时服务会启动失败。生成的运行日志不会进入 Git。

本地服务端验证统一使用已有的 Miniconda `AuWork` 环境。从仓库根目录执行以下命令，只依据项目 requirements 同步环境；需要持久化 pytest 输出时只能写入 `server/pytest_logs`：

```powershell
conda run -n AuWork python -m pip install --upgrade -r server/requirements.txt
conda run -n AuWork python -m pytest server/tests *>> server/pytest_logs/pytest.log
```

前端开发与测试进程输出统一放在 `client/logs`。以下 PowerShell 命令使用追加模式，不会截断已有日志：

```powershell
npm --prefix client run dev *>> client/logs/vite.log
npm --prefix client test *>> client/logs/test.log
```

`server/pytest_logs` 和 `client/logs` 都不是程序运行日志目录。浏览器控制台错误仍只保留在开发者工具中，不会自动上传。

### 启动服务

```bash
cd server
python main.py
```

服务启动后：
- HTTP API：`http://127.0.0.1:8000`
- WebSocket：`ws://127.0.0.1:8765`
- MCP server 按需连接（lazy mode），首次使用时由 Agent 自动触发
- 也可在前端 `MCP 市场` 中显式连接或断开
- Dream 后台任务每5分钟运行一次

### 使用 SSE MCP Server（可选）

SSE server 需要独立启动（stdio server 不需要）：

```bash
# 另开一个终端
python mcp_servers/test_sse_mcp/server.py
# 启动后：SSE 测试 MCP 已启动：http://127.0.0.1:8090/sse
```

### 测试连接

```python
import asyncio, json, websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        ready = json.loads(await ws.recv())
        chat_id = ready["chat_id"]
        await ws.send(json.dumps({
            "type": "message",
            "chat_id": chat_id,
            "content": "你好，帮我记住我叫Cash"
        }))
        async for msg in ws:
            data = json.loads(msg)
            print(data)
            if data.get("event") == "done":
                break

asyncio.run(test())
```

---

## 八、前端界面

前端位于 `client/` 目录，基于 Vite + React 19 + TypeScript + Tailwind v4。

### 启动前端（与后端并行运行）

```bash
# 终端1：启动后端
cd server && python main.py

# 终端2：启动前端
cd client && npm install && npm run dev
# 浏览器访问: http://localhost:5173
```

### 前端功能

- 侧边栏导航（新建对话 / MCP 市场 / Skill 市场 / 可折叠历史记录）
- MCP 市场（内置标识、用户 SSE 配置、Headers、连接 / 断开 / 编辑 / 删除）
- Skill 市场（来源/状态、搜索分页、ZIP 上传、完整配置编辑、启停与删除）
- 聊天框两级 `@` 选择器与 Skill/MCP 引用芯片
- 流式聊天消息（Markdown 渲染，含代码高亮和表格）
- 工具调用进度显示（spinner → 结果预览）
- WebSocket 自动重连
- 深色主题
