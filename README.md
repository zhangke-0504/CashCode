# CashCode

参考 [spore](https://github.com/spore-sh/spore) 逐步复现的个人 AI Agent 框架，目标是理解并实践 spore 的核心架构。

---

## 功能概览

| 模块 | 功能 |
|---|---|
| WebSocket 通信 | 流式对话、工具事件通知 |
| 记忆体系 | 跨会话持久化、上下文压缩、长期记忆提炼 |
| 工具调用 | ReAct 循环、10种内置工具 |
| Agent 人格 | SOUL.md 驱动的可配置身份 |

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
                    ┌─────────┴──────────┐
                    │                    │
             工具调用路径          无工具路径
                    │                    │
          SimpleAgentRunner        DeepSeek API
          (ReAct 非流式循环)       (streaming)
          ├── Tool 1..N                  │
          └── WS 事件通知           流式输出
                    │                    │
            fake streaming ──────────────┘
                    │
              MemoryStore
        ┌─────────────────────┐
        │  history.jsonl      │  ← 对话历史（每个 chat_id 独立）
        │  MEMORY.md          │  ← 全局长期记忆
        │  SOUL.md            │  ← Agent 人格配置
        │  .dream_cursor      │  ← Dream 处理进度
        └─────────────────────┘
                    │
          ┌─────────┴──────────┐
          │                    │
     Consolidator           Dream
   (上下文压缩，            (定时长期记忆
    每轮触发)                提炼，5分钟)
```

---

## 目录结构

```
CashCode/
├── server/
│   ├── main.py                    # FastAPI + WebSocket 服务入口
│   ├── .env                       # 环境变量配置
│   ├── requirements.txt
│   ├── memory/                    # 运行时记忆数据（不提交 git）
│   │   ├── SOUL.md                # Agent 人格文件（提交 git）
│   │   ├── MEMORY.md              # 全局长期记忆（运行时生成）
│   │   ├── .dream_cursor          # Dream 游标（运行时生成）
│   │   └── <chat_id>/             # 各会话历史目录
│   │       ├── history.jsonl
│   │       └── .cursor
│   └── app/
│       ├── agent/
│       │   ├── loop.py            # SimpleAgentLoop 主循环
│       │   ├── runner.py          # SimpleAgentRunner ReAct 循环
│       │   └── tools/
│       │       ├── base.py        # Tool 抽象基类
│       │       ├── memory.py      # SaveMemoryTool
│       │       ├── web.py         # WebFetchTool, WebSearchTool
│       │       ├── filesystem.py  # ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
│       │       ├── search.py      # GlobTool, GrepTool
│       │       └── shell.py       # ExecTool
│       ├── memory/
│       │   ├── store.py           # MemoryStore 文件 I/O 层
│       │   ├── consolidator.py    # SimpleConsolidator 上下文压缩
│       │   └── dream.py           # SimpleDream 长期记忆提炼
│       ├── ws/
│       │   └── channel.py         # WebSocketChannel
│       └── bus/
│           ├── queue.py           # MessageBus
│           └── events.py          # InboundMessage, OutboundMessage
└── openspec/                      # 变更管理（OpenSpec 工作流）
    ├── specs/                     # 主规范文档
    └── changes/archive/           # 已归档的变更记录
```

---

## 一、WebSocket 通信协议

服务在 `ws://127.0.0.1:8765` 监听，HTTP API 在 `http://127.0.0.1:8000`。

### 客户端 → 服务端

```json
{"type": "message", "chat_id": "uuid", "content": "用户消息"}
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

记忆体系参考 spore 的三层设计，从短期到长期：

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

## 四、SOUL.md — Agent 人格配置

`server/memory/SOUL.md` 定义 Agent 的身份和行为规则。直接编辑此文件即可调整 Agent 风格，无需修改代码，重启服务生效。

文件不存在时自动回落到代码内的 `_DEFAULT_SOUL` 默认字符串。

---

## 五、快速启动

### 环境准备

```bash
cd server
pip install -r requirements.txt
cp .env.example .env  # 填入 DEEPSEEK_API_KEY
```

### 配置（server/.env）

```ini
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

WS_HOST=127.0.0.1
WS_PORT=8765

# 文件系统工具和 exec 工具的工作目录（默认为服务启动目录）
# WORKSPACE_DIR=/your/workspace/path
```

### 启动服务

```bash
cd server
python main.py
```

服务启动后：
- HTTP API：`http://127.0.0.1:8000`
- WebSocket：`ws://127.0.0.1:8765`
- Dream 后台任务每5分钟运行一次

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
            "content": "你好，帮我记住我叫张珂"
        }))
        async for msg in ws:
            data = json.loads(msg)
            print(data)
            if data.get("event") == "done":
                break

asyncio.run(test())
```

---

## 参考

本项目是对 [spore](https://github.com/spore-sh/spore) 核心架构的学习性复现，主要参考：
- `spore/server/core/agent/memory.py` — MemoryStore / Consolidator / Dream
- `spore/server/core/agent/runner.py` — AgentRunner ReAct 循环
- `spore/server/core/agent/tools/` — 各类工具实现
- `spore/server/core/channels/websocket.py` — WebSocket 通道协议
