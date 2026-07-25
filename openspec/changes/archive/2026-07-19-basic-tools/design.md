## Context

SaveMemoryTool + SimpleAgentRunner 已就位，9个新工具只需实现各自的 `execute()` 方法即可接入。文件工具和 ExecTool 共享 `WORKSPACE_DIR` 安全边界；Web 工具不依赖本地文件系统。

## Goals / Non-Goals

**Goals:**
- 9个工具实现覆盖日常助手场景
- 所有工具注册到 `self._tools`，通过现有 Runner 自动调用
- 文件工具路径校验：禁止工作目录外访问
- ExecTool 在 WORKSPACE_DIR 执行，stdout 截断防止超长

**Non-Goals:**
- 精确复现 spore 工具（如多模态、沙箱隔离）
- 工具权限审批
- SpawnTool / CronTool / NotebookTool

## Decisions

### D1：WORKSPACE_DIR 通过 .env 配置，默认 CWD

```python
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()
```

文件工具初始化时接收 `workspace` 参数，loop.py 在初始化工具时传入。

---

### D2：WebFetch — httpx GET + HTML 清理 + 截断 3000 字符

```python
async def execute(self, url: str) -> str:
    async with httpx.AsyncClient(...) as client:
        resp = await client.get(url, follow_redirects=True, timeout=15)
    text = strip_html(resp.text)[:3000]
    return f"[来自 {url}]\n{text}"
```

---

### D3：WebSearch — DuckDuckGo Instant Answer API（无 key）

```
GET https://api.duckduckgo.com/?q=<query>&format=json&no_redirect=1
```

返回 Abstract + RelatedTopics 列表，格式化为可读文本。限制：InstantAnswer 覆盖范围有限，复杂查询效果一般（符合用户预期）。

---

### D4：文件工具安全策略 — 路径解析后校验在 WORKSPACE_DIR 内

```python
def _safe_path(self, path: str) -> Path:
    resolved = (self._workspace / path).resolve()
    if not str(resolved).startswith(str(self._workspace)):
        raise PermissionError(f"路径 {path} 超出工作目录")
    return resolved
```

---

### D5：EditFileTool — 精确字符串替换（参考 spore edit_file）

参数：`path`、`old_string`、`new_string`。若 `old_string` 不唯一，报错要求用户提供更多上下文。与 CashCode 自身使用的 Edit 工具语义一致。

---

### D6：ExecTool — subprocess + timeout + 截断

```python
result = await asyncio.create_subprocess_shell(
    command,
    cwd=self._workspace,
    stdout=PIPE, stderr=PIPE,
)
stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=30)
output = (stdout + stderr).decode()[:4096]
```

---

### D7：loop.py 工具注册

```python
workspace = Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()
self._tools = [
    SaveMemoryTool(self._store),
    WebFetchTool(),
    WebSearchTool(),
    ReadFileTool(workspace),
    WriteFileTool(workspace),
    EditFileTool(workspace),
    ListDirTool(workspace),
    GlobTool(workspace),
    GrepTool(workspace),
    ExecTool(workspace),
]
```

## Risks / Trade-offs

- **[风险] DuckDuckGo InstantAnswer 覆盖有限** → 接受；用户期望已知，未来可换 Tavily
- **[风险] ExecTool 执行任意命令** → 限制 cwd=workspace，不传递危险环境变量；用户在本机运行，风险可控
- **[风险] 工具列表长 → system prompt 中工具说明增大** → LLM 会选择合适工具，无明显问题

## Migration Plan

无需迁移。新工具只是扩充 `self._tools` 列表，现有对话和记忆不受影响。`WORKSPACE_DIR` 未配置时回落当前目录。
