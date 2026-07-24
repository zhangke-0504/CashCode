## Context

CashCode 的 Python 后端已完整实现（FastAPI HTTP + WebSocket + Agent + MCP + 记忆体系），但零前端。后端唯一的 HTTP 端点是 `/api/health`；所有实时通信走 WebSocket（端口 8765）。会话数据以文件形式存储在 `memory/<chat_id>/`，session_metadata.json 里已有 `activated_tools` 等字段，需新增 `title` 字段。

spore（本项目的参考代码库）使用 Next.js 16 + React 19 + Tailwind v4 + motion + lucide-react + react-markdown。CashCode 不需要 SSR 和路由层，因此选用更轻量的 Vite 替代 Next.js，但保留相同的组件模型和样式方案。

## Goals / Non-Goals

**Goals:**
- 新增后端 REST API：`GET /api/sessions`、`PATCH /api/sessions/{chat_id}`、`DELETE /api/sessions/{chat_id}`
- 在 `client/` 下新建前端项目（Vite + React 19 + Tailwind v4）
- 实现可用的第一版 UI：侧边栏 + 聊天视图 + Composer
- 清理 README 中所有"参考 spore"相关表述
- 替换静态资源为 CashLogo.png 和 CashMe.png

**Non-Goals:**
- Electron 打包（V1 只做 Web 应用）
- 用户认证 / 多用户支持
- 会话搜索 / 标签分类
- 文件附件 / 图片上传
- MCP 管理 UI

## Decisions

### D1：前端技术栈选 Vite，而不是 Next.js

**选择**：Vite + React 19 + TypeScript + Tailwind v4

**理由**：CashCode V1 是单页应用，不需要 SSR、ISR 或 Next.js 的文件路由。Vite 启动快（< 200ms）、配置极简、产物是纯静态文件，方便 FastAPI 后续用 `StaticFiles` 托管。Next.js 引入的复杂性（`app/` 目录、Server Components、middleware）对这个场景零收益。

**与 spore 的一致性**：组件模型、Tailwind 类名、lucide-react 图标、react-markdown 均与 spore 保持完全一致，未来如需移植组件无障碍。

---

### D2：后端 session API 通过 MemoryStore 直接读写文件，不引入数据库

**选择**：扫描 `memory/` 目录 + 读写 `session_metadata.json`

**理由**：现有 MemoryStore 已是文件系统抽象层，session_metadata.json 本来就用于持久化 ActivatedToolSet。在 MemoryStore 类上新增几个方法即可完成，零新依赖。

**风险**：高并发时文件锁缺失。缓解：V1 是单用户本地应用，不存在并发写同一 chat_id 的问题；agent loop 已有 per-chat asyncio.Lock 保护历史写入，rename 只改 metadata 字段，可接受。

---

### D3：WebSocket 状态用 React Context + useReducer 管理

**选择**：单一 `ChatContext`，持有 `sessions`、`activeSessionId`、`messages`、`streamingState`

**理由**：V1 状态不复杂，不需要 Zustand 或 Redux。`useReducer` 对事件驱动的 WS 消息天然适配（action = WS 帧类型）。避免引入不必要的依赖。

---

### D4：标题自动生成逻辑放在后端

**选择**：在 `_handle_turn` 第一轮时，若 session_metadata 无 title，截取用户消息前 40 个字符作为默认标题

**理由**：后端是唯一能保证原子性的位置。前端在会话开始时立刻写入标题可能与 WS 消息产生竞争条件；放后端更简单。

---

### D5：深色主题作为默认且唯一主题

**选择**：类似 spore 的深色 UI（`#0a0a0a` 背景、`#1a1a1a` 侧边栏、`zinc-*` 色调）

**理由**：spore 风格即深色，用户期望一致；V1 不实现主题切换，减少复杂度。

## Risks / Trade-offs

- **会话列表不实时刷新**：其他客户端（如测试脚本）新建的会话不会自动出现在侧边栏，需手动刷新。V1 可接受；V2 可通过 WebSocket 推送 `session_created` 事件解决。
- **Markdown 渲染闪烁**：流式 delta 期间逐字追加文本，react-markdown 每次 re-render 都完整解析。可通过 `dangerouslySetInnerHTML` + marked 实现增量追加，但 V1 优先简单，接受轻微闪烁。
- **Tailwind v4 配置差异**：Tailwind v4 使用 `@import "tailwindcss"` 取代 v3 的 `tailwind.config.js`，与网上大量文档不一致。需在脚手架阶段仔细验证。

## Migration Plan

1. 后端 API 纯新增，不改变现有 WebSocket 协议，现有 Python 测试脚本不受影响
2. 前端在新的 `client/` 目录独立开发，不污染 `server/` 代码
3. README 修改在独立 commit 中完成

## Open Questions

- ~~`session_metadata.json` 里是否已有 `title` 字段？~~ → 经探索：无，需新增
- 会话列表按什么排序？ → 按 `updated_at` 降序（最近活跃的在顶部）
