## 1. Web 工具

- [x] 1.1 创建 `server/app/agent/tools/web.py`，实现 `WebFetchTool`：httpx GET → strip HTML → 截断 3000 字符返回
- [x] 1.2 在同文件实现 `WebSearchTool`：调用 `https://api.duckduckgo.com/?q=<query>&format=json&no_redirect=1`，格式化返回摘要和相关条目

## 2. 文件系统工具

- [x] 2.1 创建 `server/app/agent/tools/filesystem.py`，实现 `_safe_path(workspace, path)` 辅助函数（路径穿越校验）
- [x] 2.2 实现 `ReadFileTool`：读取 workspace 内文件，返回内容
- [x] 2.3 实现 `WriteFileTool`：在 workspace 内创建/覆盖文件（自动创建父目录）
- [x] 2.4 实现 `EditFileTool`：在文件中替换第一处 `old_string`，不存在时报错
- [x] 2.5 实现 `ListDirTool`：列出 workspace 内目录内容，含类型标记

## 3. 搜索工具

- [x] 3.1 创建 `server/app/agent/tools/search.py`，实现 `GlobTool`：`pathlib.Path.rglob()` 按模式匹配，最多100条结果
- [x] 3.2 实现 `GrepTool`：遍历匹配文件，正则搜索内容，返回 `文件名:行号: 内容`，最多50条

## 4. Shell 工具

- [x] 4.1 创建 `server/app/agent/tools/shell.py`，实现 `ExecTool`：`asyncio.create_subprocess_shell`，cwd=workspace，timeout=30s，stdout+stderr 合并截断 4096 字符

## 5. 集成到 AgentLoop

- [x] 5.1 在 `server/.env` 和 `server/.env.example` 中新增 `WORKSPACE_DIR=` 配置项（注释说明用途）
- [x] 5.2 修改 `loop.py`：从 `.env` 读取 `WORKSPACE_DIR`，初始化所有10个工具并注册到 `self._tools`
- [x] 5.3 更新 `base_prompt` / `SOUL.md` 中的工具使用说明，告知 LLM 新增工具的用途

## 6. 验证

- [ ] 6.1 测试 WebFetchTool：让 Agent 抓取一个 URL（如 `https://httpbin.org/get`）并返回内容
- [ ] 6.2 测试 WebSearchTool：让 Agent 搜索一个关键词，确认返回 DuckDuckGo 结果
- [ ] 6.3 测试文件工具：让 Agent 列目录 → 读文件 → 写新文件 → 编辑文件
- [ ] 6.4 测试 GrepTool：让 Agent 在工作目录中搜索某个字符串
- [ ] 6.5 测试 ExecTool：让 Agent 执行 `pwd` 确认在 workspace 内
