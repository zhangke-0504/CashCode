## Why

工具调用基础设施已经完备（SaveMemoryTool + SimpleAgentRunner）。将 spore 中高频日常工具搬运到 CashCode，使 Agent 具备网页获取、本地文件操作和命令执行能力，覆盖绝大多数个人助手使用场景。

## What Changes

- 新增 `server/app/agent/tools/web.py`：`WebFetchTool`（抓取网页）、`WebSearchTool`（DuckDuckGo 搜索）
- 新增 `server/app/agent/tools/filesystem.py`：`ReadFileTool`、`WriteFileTool`、`EditFileTool`、`ListDirTool`
- 新增 `server/app/agent/tools/search.py`：`GlobTool`（按文件名模式查找）、`GrepTool`（按内容搜索）
- 新增 `server/app/agent/tools/shell.py`：`ExecTool`（执行 shell 命令）
- 修改 `server/app/agent/loop.py`：注册所有新工具
- 修改 `server/.env`（及 `.env.example`）：新增 `WORKSPACE_DIR` 配置项

## Capabilities

### New Capabilities

- `web-tools`: LLM 主动抓取网页内容 + DuckDuckGo 搜索
- `filesystem-tools`: LLM 读写编辑用户工作目录下的文件
- `search-tools`: LLM 按文件名或内容搜索工作目录
- `shell-tool`: LLM 在工作目录下执行 shell 命令

## Impact

- **新增文件**: `web.py`、`filesystem.py`、`search.py`、`shell.py`（均在 `server/app/agent/tools/`）
- **修改文件**: `server/app/agent/loop.py`、`server/.env`
- **新增环境变量**: `WORKSPACE_DIR`（默认当前工作目录），文件工具和 ExecTool 限制在此目录下
- **外部依赖**: `httpx`（已安装）；DuckDuckGo 无需 API key
- **安全边界**: 所有文件操作路径校验（禁止路径穿越），ExecTool 限制在 `WORKSPACE_DIR`，stdout 截断 4096 字符
