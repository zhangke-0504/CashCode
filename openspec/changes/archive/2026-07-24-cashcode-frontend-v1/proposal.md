## Why

CashCode 的后端已实现完整的 Agent 体系（MCP、记忆、工具调用、WebSocket 推流），但缺少前端界面，目前只能通过 Python 脚本测试。第一版前端的目标是让项目可以真正被使用，同时补齐两个后端缺口（会话重命名和删除）以支持基本的会话管理。

## What Changes

- **新增** `client/` 目录：Vite + React 19 + TypeScript + Tailwind v4 前端应用
- **新增** 后端 REST API：`GET /api/sessions`、`PATCH /api/sessions/{chat_id}`、`DELETE /api/sessions/{chat_id}`
- **新增** 前端 WebSocket 连接层，实现流式消息、工具调用进度展示
- **新增** 会话列表侧边栏，支持新建、重命名、删除会话
- **新增** 聊天界面：消息气泡、流式 delta 渲染、工具调用折叠块
- **新增** Composer 输入框，支持发送消息和停止生成
- **修改** `README.md`：移除所有涉及"参考 spore"的表述和与 spore 的对照表
- **替换** 静态资源：Logo 使用 `CashLogo.png`，空态形象使用 `CashMe.png`

## Capabilities

### New Capabilities

- `session-management-api`：后端 REST API，管理会话列表、重命名、删除，读写 MemoryStore 的 session_metadata
- `frontend-app`：Vite + React 前端应用结构，含构建配置、路由、全局状态
- `chat-websocket-client`：前端 WebSocket 连接层，处理连接/重连、帧解析、流式消息队列
- `sidebar-session-list`：会话列表侧边栏，展示历史会话，支持新建/重命名/删除操作
- `chat-view`：聊天消息区，包含消息气泡（markdown 渲染）、工具调用折叠块、自动滚动
- `composer-input`：消息输入区，支持发送、停止生成

### Modified Capabilities

- `session-metadata`：新增 `title` 字段（由前端首轮消息自动生成或用户手动重命名）

## Impact

- **新增文件**：`client/` 目录（约 20 个新文件），`server/app/api/sessions.py`
- **修改文件**：`server/main.py`（注册新路由），`server/app/api/__init__.py`，`README.md`
- **静态资源**：`client/public/` 下放置 CashLogo.png 和 CashMe.png
- **无破坏性变更**：WebSocket 协议不变，现有 Python 测试脚本继续有效
