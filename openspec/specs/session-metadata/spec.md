# Spec: session-metadata

## Purpose

为每个 chat session 提供持久化的元数据存储，支持跨轮次保存 activated tools 等状态，由 MemoryStore 负责读写，SimpleAgentLoop 在内存中缓存并在每轮结束时写回磁盘。

## Requirements

### Requirement: MemoryStore 支持 session metadata 读写
`MemoryStore` SHALL 提供 `read_session_metadata(chat_id)` 和 `write_session_metadata(chat_id, data)` 两个方法，将任意 dict 持久化到 `memory/<chat_id>/metadata.json`。

#### Scenario: 首次读取不存在的 metadata
- **WHEN** 调用 `read_session_metadata("chat-123")`，且文件不存在
- **THEN** 返回空 dict `{}`，不抛出异常

#### Scenario: 写入后再读回
- **WHEN** 调用 `write_session_metadata("chat-123", {"activated_tools": {"mcp_weather_get_weather": 1721358000.0}})`，再调用 `read_session_metadata("chat-123")`
- **THEN** 返回的 dict 与写入内容一致

#### Scenario: loop 每轮结束时写回 metadata
- **WHEN** `_handle_turn()` 完成一轮对话
- **THEN** `store.write_session_metadata(chat_id, self._session_metadata[chat_id])` 被调用，将内存缓存持久化到磁盘

### Requirement: loop 内存缓存 session metadata
`SimpleAgentLoop` SHALL 维护 `self._session_metadata: dict[str, dict]`，在 `_handle_turn()` 开始时懒加载（首次从磁盘读，后续从内存取），结束时写回磁盘。

#### Scenario: 首次处理某 chat_id 时加载 metadata
- **WHEN** `_handle_turn()` 收到从未处理过的 `chat_id`
- **THEN** 调用 `store.read_session_metadata(chat_id)` 并存入 `self._session_metadata[chat_id]`
