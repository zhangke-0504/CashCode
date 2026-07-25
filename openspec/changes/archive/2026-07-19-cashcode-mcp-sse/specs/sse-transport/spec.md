## ADDED Requirements

### Requirement: establish_mcp_sessions 支持 SSE 传输
`establish_mcp_sessions()` 的 owner task SHALL 识别 `type: "sse"`（或 url 字段存在且不以 stdio 方式配置时），调用 `sse_client(url)` 建立传输，其余握手流程与 stdio 完全一致。

#### Scenario: SSE server 已启动时成功连接
- **WHEN** mcp_config 包含 `{"calculator": {"type": "sse", "url": "http://127.0.0.1:8090/sse"}}` 且 calculator server 正在运行
- **THEN** owner task 通过 `sse_client(url)` 建立连接，握手完成，`handle.session` 不为 None，`handle` 进入 accepted 字典

#### Scenario: SSE server 未启动时连接失败但不崩溃
- **WHEN** mcp_config 中配置了 SSE server 但目标 URL 无法连接
- **THEN** owner task 捕获异常，`errors_out[server_name]` 记录错误，server 不进入 accepted 字典，其他 server 不受影响

#### Scenario: 传输类型自动推断
- **WHEN** config 无显式 `type` 字段但有 `url` 字段（非以 `/sse` 结尾）
- **THEN** 推断为 `streamableHttp`；若 url 以 `/sse` 结尾则推断为 `sse`（与 spore 保持一致）
