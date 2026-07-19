# Spec: mcp-tool-cache

## Purpose

为 MCP server 的工具列表提供磁盘缓存，避免每次启动都需要重新连接 server，通过 transport fingerprint 验证缓存有效性，原子写入保证文件完整性。

## Requirements

### Requirement: transport fingerprint 验证缓存有效性
`read_cache(server_name, config)` SHALL 计算当前 config 的 `sha256(command+args+env+url)[:16]`，与缓存文件中的 `transport_fingerprint` 比对，不一致时返回 None（缓存失效）。

#### Scenario: 配置未变时缓存有效
- **WHEN** server config 与缓存写入时相同，调用 `read_cache("weather", cfg)`
- **THEN** 返回 tools 列表

#### Scenario: 配置变更后缓存失效
- **WHEN** server config 的 `command` 或 `args` 改变后，调用 `read_cache("weather", cfg)`
- **THEN** 返回 None

### Requirement: mcp_prepare 成功后写入缓存
`write_cache(server_name, config, tools)` SHALL 在 `mcp_prepare` 连接成功并 `list_tools()` 完成后调用，将 tools schema 原子写入 `mcp_cache/<server_name>.json`。

#### Scenario: 写入后可读
- **WHEN** `write_cache("weather", cfg, tools)` 执行完毕
- **THEN** `read_cache("weather", cfg)` 返回相同的 tools 列表

### Requirement: 缓存文件格式
缓存文件 SHALL 包含 `transport_fingerprint`（str）、`cached_at`（ISO8601）、`tools`（list）、`resources`（list）、`prompts`（list），不含 company catalog 版本字段。

#### Scenario: 缓存结构完整
- **WHEN** `write_cache` 写入后读取 JSON 文件
- **THEN** 包含 `transport_fingerprint`、`cached_at`、`tools` 字段，tools 每项含 `name`、`description`、`inputSchema`
