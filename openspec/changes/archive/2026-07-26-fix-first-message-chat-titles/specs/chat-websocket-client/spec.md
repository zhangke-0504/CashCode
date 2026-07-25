## MODIFIED Requirements

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

## ADDED Requirements

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
