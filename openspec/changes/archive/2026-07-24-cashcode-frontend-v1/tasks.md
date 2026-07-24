## 1. 后端：会话管理 API

- [x] 1.1 在 `server/app/memory/store.py` 的 `MemoryStore` 类新增 `list_sessions()` 方法，扫描 `base_dir` 下所有子目录并读取各自的 `session_metadata.json`，返回 `{chat_id, title, updated_at}` 列表（按 `updated_at` 降序）
- [x] 1.2 在 `MemoryStore` 的 `session_metadata.json` 读写逻辑中加入 `title` 字段支持，在 `_handle_turn` 第一轮时若无 title，自动截取用户消息前 40 字符作为默认标题
- [x] 1.3 创建 `server/app/api/sessions.py`，实现 `GET /api/sessions` 端点，调用 `store.list_sessions()` 返回会话列表
- [x] 1.4 在 `sessions.py` 中实现 `PATCH /api/sessions/{chat_id}` 端点，校验 title 非空后更新 `session_metadata.json` 中的 `title` 字段
- [x] 1.5 在 `sessions.py` 中实现 `DELETE /api/sessions/{chat_id}` 端点，校验目录存在后 `shutil.rmtree`，若目录不存在返回 404
- [x] 1.6 在 `server/app/api/__init__.py` 中导出新路由，并在 `server/main.py` 注册路由前缀 `/api/sessions`

## 2. 前端：项目脚手架

- [x] 2.1 在项目根目录创建 `client/` 目录，用 `npm create vite@latest . -- --template react-ts` 初始化（React 19 + TypeScript）
- [x] 2.2 安装依赖：`tailwindcss@^4`、`@tailwindcss/vite`、`lucide-react`、`motion`、`react-markdown`、`remark-gfm`、`tailwind-merge`
- [x] 2.3 配置 Tailwind v4：在 `client/src/index.css` 中用 `@import "tailwindcss"` 替代 v3 配置；在 `vite.config.ts` 添加 `@tailwindcss/vite` 插件
- [x] 2.4 将 `my_testing/static/CashLogo.png` 和 `CashMe.png` 复制到 `client/public/` 目录
- [x] 2.5 清空 Vite 模板默认内容（`App.tsx`、`App.css`、`index.css` 样式），配置全局深色背景 `#0a0a0a`
- [x] 2.6 在 `client/` 根目录创建 `README.md`，说明 `npm install` 和 `npm run dev` 启动方式

## 3. 前端：WebSocket 状态层

- [x] 3.1 创建 `client/src/types.ts`，定义 `Session`、`Message`、`ToolCallBlock`、`WsFrame` 等 TypeScript 接口
- [x] 3.2 创建 `client/src/hooks/useWebSocket.ts`：连接 `ws://127.0.0.1:8765/`，实现自动重连（指数退避，最大 30s），暴露 `send(frame)` 方法和连接状态
- [x] 3.3 创建 `client/src/context/ChatContext.tsx`：用 `useReducer` 管理 `sessions`、`activeSessionId`、`messages`（按 session 分组）、`streamingStates`；定义 action 类型对应所有 WS 事件类型
- [x] 3.4 在 ChatContext 中处理所有 WS 入站帧：`ready`→更新默认 chat_id；`attached`→切换活跃 session；`delta`→追加 streaming 文本；`stream_end`→标记完成；`tool_call`/`tool_result`→更新 ToolCallBlock；`done`→清空 streaming 状态；`error`→显示错误
- [x] 3.5 创建 `client/src/lib/api.ts`，封装 `fetchSessions()`、`renameSession(chat_id, title)`、`deleteSession(chat_id)` 方法，统一处理错误和 JSON 解析

## 4. 前端：布局与 TitleBar

- [x] 4.1 创建 `client/src/components/TitleBar.tsx`：显示 CashLogo.png（24×24px）+ 文字 "CashCode"，使用深色背景，高度 44px
- [x] 4.2 创建 `client/src/App.tsx`：使用 CSS Grid 或 Flexbox 布局，渲染 `TitleBar + Sidebar + ChatView` 三栏结构，Sidebar 固定宽度 240px

## 5. 前端：Sidebar 组件

- [x] 5.1 创建 `client/src/components/Sidebar.tsx`：从 API `GET /api/sessions` 加载会话列表，渲染滚动列表，高亮 activeSessionId
- [x] 5.2 实现 Sidebar 顶部"+ 新对话"按钮：点击后发送 `{"type": "new_chat"}` WS 帧
- [x] 5.3 实现每行的悬浮 "···" 菜单（使用 Tailwind 定位，不需要独立组件）：菜单项"重命名"和"删除"
- [x] 5.4 实现"重命名"交互：点击后将 title 替换为 `<input>` 内联编辑框；失焦或 Enter 调用 `PATCH /api/sessions/{chat_id}`；Escape 取消
- [x] 5.5 实现"删除"交互：点击后弹出确认对话框（原生 `confirm()` 即可）；确认后调用 `DELETE /api/sessions/{chat_id}` 并从列表移除

## 6. 前端：ChatView 组件

- [x] 6.1 创建 `client/src/components/ChatView.tsx`：空态时居中渲染 CashMe.png（160×160px）和欢迎文案；有消息时渲染消息列表
- [x] 6.2 创建 `client/src/components/MessageBubble.tsx`：用户消息右对齐浅色气泡；助手消息左对齐深色气泡；助手消息用 `react-markdown` + `remark-gfm` 渲染
- [x] 6.3 创建 `client/src/components/ToolProgressBlock.tsx`：渲染 tool_call 的工具名+spinner；tool_result 到达后改为 checkmark + 结果预览
- [x] 6.4 在 ChatView 中实现自动滚动：`useEffect` 监听 messages 变化，若用户未向上滚动则 `scrollToBottom()`；向上滚动时显示"↓ 跳到最新"按钮

## 7. 前端：Composer 组件

- [x] 7.1 创建 `client/src/components/Composer.tsx`：`<textarea>` 输入框，Enter 提交（Shift+Enter 换行），禁用状态（streaming 中不允许输入）
- [x] 7.2 实现 Send 按钮：点击发送 `{"type": "message", "chat_id": activeId, "content": text}` WS 帧并清空输入框
- [x] 7.3 实现 Stop 按钮：streaming 时替换 Send 按钮；点击后发送 `{"type": "cancel", "chat_id": activeId}` WS 帧
- [x] 7.4 切换 session 时 textarea 自动 focus（`useEffect` + `ref.current.focus()`）

## 8. README 清理

- [x] 8.1 在 `README.md` 中删除或改写一切含"参考 spore"、"仿写"、"复现"、"与 spore 的对照"的表述（搜索关键词：spore、参考、复现、仿写、对照）
- [x] 8.2 在 README.md 中新增 "前端" 章节，说明 `client/` 目录结构、`npm run dev` 和后端并行启动方式
