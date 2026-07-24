## ADDED Requirements

### Requirement: Display session list
The system SHALL render all existing sessions in the sidebar as a scrollable list.

#### Scenario: Sessions loaded
- **WHEN** app loads and `GET /api/sessions` returns a list
- **THEN** sidebar displays each session as a row with its title and relative timestamp

#### Scenario: Active session highlighted
- **WHEN** user selects a session
- **THEN** that session row is visually highlighted with a distinct background

### Requirement: Create new session
The system SHALL allow the user to start a new conversation.

#### Scenario: New session created
- **WHEN** user clicks the "+" button in the sidebar
- **THEN** app sends `{"type": "new_chat"}` over WebSocket, receives `{"event": "attached", "chat_id": "..."}`, and switches to the new empty chat

### Requirement: Rename session via context menu
The system SHALL allow renaming a session through a hover context menu.

#### Scenario: Rename flow
- **WHEN** user hovers over a session row, clicks "···" menu, then selects "重命名"
- **THEN** the session title becomes an inline editable field; on blur or Enter, client sends `PATCH /api/sessions/{chat_id}` with the new title and updates the sidebar label

#### Scenario: Rename cancelled
- **WHEN** user presses Escape during inline rename
- **THEN** the title reverts to the original value without any API call

### Requirement: Delete session via context menu
The system SHALL allow deleting a session through a hover context menu.

#### Scenario: Delete with confirmation
- **WHEN** user selects "删除" from the session context menu
- **THEN** a confirmation dialog appears; on confirm, client sends `DELETE /api/sessions/{chat_id}` and removes the row from the sidebar

#### Scenario: Delete active session
- **WHEN** user deletes the currently active session
- **THEN** app switches to the most recent remaining session, or shows an empty state if none remain
