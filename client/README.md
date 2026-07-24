# CashCode 前端

基于 Vite + React 19 + TypeScript + Tailwind v4 的 CashCode AI 助手前端界面。

## 启动开发环境

确保后端已在运行（先启动后端）：

```bash
# 终端1：启动后端
cd ../server
python main.py
# HTTP API: http://127.0.0.1:8000
# WebSocket: ws://127.0.0.1:8765

# 终端2：启动前端开发服务器
cd client
npm install
npm run dev
# 浏览器访问: http://localhost:5173
```

## 构建生产版本

```bash
npm run build
# 产物输出到 dist/
```

## 目录结构

```
src/
├── types.ts               # TypeScript 类型定义
├── App.tsx                # 根组件（TitleBar + Sidebar + ChatView）
├── components/
│   ├── TitleBar.tsx       # 顶部标题栏（Logo + 连接状态）
│   ├── Sidebar.tsx        # 会话列表（新建/重命名/删除）
│   ├── ChatView.tsx       # 聊天区域（消息列表 + 自动滚动）
│   ├── MessageBubble.tsx  # 消息气泡（Markdown 渲染）
│   ├── ToolProgressBlock.tsx  # 工具调用进度块
│   └── Composer.tsx       # 消息输入框（发送/停止）
├── context/
│   └── ChatContext.tsx    # 全局状态（WebSocket + 会话 + 消息）
├── hooks/
│   └── useWebSocket.ts    # WebSocket 连接（自动重连）
└── lib/
    └── api.ts             # REST API 封装（sessions CRUD）
```

## 技术栈

- React 19 + TypeScript + Vite
- Tailwind v4 · lucide-react · react-markdown + remark-gfm
