## ADDED Requirements

### Requirement: WebFetchTool fetches URL content
`WebFetchTool` SHALL 接受 `url: str` 参数，发起 HTTP GET 请求，剥离 HTML 标签，返回前 3000 字符的纯文本内容（含来源 URL 前缀）。

#### Scenario: URL fetched and HTML stripped
- **WHEN** LLM 调用 `web_fetch(url="https://example.com")`
- **THEN** 返回格式为 `[来自 https://example.com]\n<纯文本内容>`，不含 HTML 标签

#### Scenario: Timeout or error returns error message
- **WHEN** URL 无法访问或超时（15秒）
- **THEN** 返回描述错误的字符串，不抛出异常

### Requirement: WebSearchTool searches via DuckDuckGo
`WebSearchTool` SHALL 接受 `query: str` 参数，调用 DuckDuckGo Instant Answer API，返回摘要 + 相关条目列表（最多10条，每条含标题和文字）。

#### Scenario: Search returns structured results
- **WHEN** LLM 调用 `web_search(query="Python 3.12 新特性")`
- **THEN** 返回格式化文本，包含搜索摘要（如有）和相关条目列表

#### Scenario: Empty results handled gracefully
- **WHEN** DuckDuckGo 返回空结果
- **THEN** 返回 "未找到相关结果，建议使用 web_fetch 访问具体网页"
