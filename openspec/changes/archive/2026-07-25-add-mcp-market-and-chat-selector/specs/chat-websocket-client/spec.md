## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Handle selection validation errors
The WebSocket client SHALL surface server rejection of invalid, stale, or unavailable capability metadata without marking the turn as successfully started.

#### Scenario: Server rejects selected capability metadata
- **WHEN** the server returns an error for unknown, malformed, or unavailable Skill/MCP selection metadata
- **THEN** the active chat displays the error, stops the optimistic streaming state, and retains enough visible selection context for the user to revise the message

