## ADDED Requirements

### Requirement: Connect to WebSocket server
The system SHALL establish a WebSocket connection to `ws://127.0.0.1:8765/` and maintain it with auto-reconnect.

#### Scenario: Initial connection
- **WHEN** app mounts
- **THEN** WebSocket connects and server sends `{"event": "ready", "chat_id": "...", "client_id": "..."}`

#### Scenario: Auto-reconnect on disconnect
- **WHEN** WebSocket connection drops unexpectedly
- **THEN** client retries connection with exponential backoff (1s, 2s, 4s, max 30s)

### Requirement: Send chat message over WebSocket
The system SHALL send user messages as JSON frames to the WebSocket server.

#### Scenario: User sends message
- **WHEN** user submits a message in the Composer
- **THEN** client sends `{"type": "message", "chat_id": "<active_chat_id>", "content": "<text>"}` over WebSocket

### Requirement: Receive and render streaming response
The system SHALL process delta frames from the server and render text incrementally.

#### Scenario: Streaming in progress
- **WHEN** server sends multiple `{"event": "delta", "chat_id": "...", "text": "...", "stream_id": N}` frames
- **THEN** client appends each `text` fragment to the current assistant message in real time

#### Scenario: Stream ends
- **WHEN** server sends `{"event": "stream_end", "chat_id": "...", "stream_id": N}`
- **THEN** client marks the current assistant message as complete and stops showing the typing indicator

### Requirement: Display tool call progress
The system SHALL show tool call and result events as collapsible blocks in the message list.

#### Scenario: Tool call event received
- **WHEN** server sends `{"event": "tool_call", "chat_id": "...", "tool_name": "web_fetch", "stream_id": N}`
- **THEN** client renders a collapsible progress block labeled with the tool name

#### Scenario: Tool result event received
- **WHEN** server sends `{"event": "tool_result", "chat_id": "...", "tool_name": "web_fetch", "result": "...", "stream_id": N}`
- **THEN** client updates the corresponding block to show a truncated result preview

### Requirement: Stop generation
The system SHALL allow the user to cancel an ongoing generation.

#### Scenario: User clicks Stop
- **WHEN** user clicks the Stop button while a response is streaming
- **THEN** client sends `{"type": "cancel", "chat_id": "..."}` and the Stop button reverts to Send
