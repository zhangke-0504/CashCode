# Chat WebSocket Client Specification

## Purpose
Define WebSocket connection management, message submission, streaming events, tool progress, cancellation, and capability-selection validation behavior.

## Requirements

### Requirement: Connect to WebSocket server
The system SHALL establish a WebSocket connection to `ws://127.0.0.1:8765/`, maintain it with auto-reconnect, and treat connection-assigned chat IDs as drafts rather than persisted history entries.

#### Scenario: Initial connection
- **WHEN** app mounts
- **THEN** WebSocket connects and server sends `{"event": "ready", "chat_id": "...", "client_id": "..."}` with a chat ID that can be used as an active draft

#### Scenario: Ready draft is not history
- **WHEN** the client receives a `ready` frame for a chat ID that has no authoritative session metadata
- **THEN** the client does not add a `新对话` row to session history

#### Scenario: Auto-reconnect on disconnect
- **WHEN** WebSocket connection drops unexpectedly
- **THEN** client retries connection with exponential backoff (1s, 2s, 4s, max 30s) without appending a placeholder session row for each reconnect

### Requirement: Receive authoritative session updates
The WebSocket client SHALL process authoritative session metadata updates without reloading the complete session list.

#### Scenario: First question assigns a title
- **WHEN** server sends `{"event": "session_updated", "chat_id": "...", "title": "...", "updated_at": "..."}` for the active draft
- **THEN** the client inserts that chat into the session list with the supplied title and timestamp and keeps it active

#### Scenario: Existing session metadata is updated
- **WHEN** server sends a `session_updated` frame for a chat ID already present in the session list
- **THEN** the client updates that row with the supplied title and timestamp without creating a duplicate

#### Scenario: Session update precedes assistant completion
- **WHEN** the first question is accepted and assistant generation is still running
- **THEN** the client can display the authoritative title before receiving `stream_end` or `done`

### Requirement: Send chat message over WebSocket
The system SHALL send user messages as JSON frames to the WebSocket server with plain content and optional bounded structured capability-selection metadata.

#### Scenario: User sends message without selections
- **WHEN** user submits a message in the Composer without Skill or MCP chips
- **THEN** client sends `{"type": "message", "chat_id": "<active_chat_id>", "content": "<text>"}` over WebSocket without selection arrays

#### Scenario: User sends message with selections
- **WHEN** user submits a message with Skill or MCP chips
- **THEN** client sends canonical records in `metadata.mentioned_skills` and `metadata.selected_mcp_connectors` while keeping `content` equal to the plain task text

#### Scenario: Client metadata exceeds the selection bound
- **WHEN** message construction receives more than eight combined selections or an invalid canonical identifier
- **THEN** the client rejects frame construction, preserves the draft, and displays a bounded error

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

### Requirement: Handle selection validation errors
The WebSocket client SHALL surface server rejection of invalid, stale, or unavailable capability metadata without marking the turn as successfully started.

#### Scenario: Server rejects selected capability metadata
- **WHEN** the server returns an error for unknown, malformed, or unavailable Skill/MCP selection metadata
- **THEN** the active chat displays the error, stops the optimistic streaming state, and retains enough visible selection context for the user to revise the message
