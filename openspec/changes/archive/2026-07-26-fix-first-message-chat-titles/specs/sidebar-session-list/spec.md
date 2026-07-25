## MODIFIED Requirements

### Requirement: Create new session
The system SHALL retain a visible `新建对话` command, allow the user to start an empty draft from any main view, and add that chat to history only after the first valid user question creates authoritative session metadata.

#### Scenario: New draft created
- **WHEN** user clicks `新建对话`
- **THEN** app sends `{"type": "new_chat"}` over WebSocket, receives `{"event": "attached", "chat_id": "..."}`, switches to chat view, and displays the new empty draft without adding a `新对话` history row

#### Scenario: Empty draft is abandoned
- **WHEN** user creates or receives a draft chat ID but sends no valid question before switching away or reconnecting
- **THEN** the draft does not appear in session history

#### Scenario: First question promotes the draft
- **WHEN** the backend accepts the draft's first valid user question and publishes authoritative session metadata
- **THEN** the sidebar adds one history row using the assigned title and timestamp and highlights it as active

## ADDED Requirements

### Requirement: Apply live session metadata updates
The sidebar SHALL apply authoritative session metadata updates without a full session-list reload.

#### Scenario: Update for an existing row
- **WHEN** a session metadata event identifies a chat already displayed in history
- **THEN** the sidebar updates that row's title and timestamp without changing the user's active chat

#### Scenario: Repeated update for the same chat
- **WHEN** multiple session metadata events identify the same chat ID
- **THEN** the sidebar maintains exactly one row for that chat ID
