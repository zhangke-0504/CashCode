## MODIFIED Requirements

### Requirement: Display session list
The system SHALL render all existing sessions as a scrollable list beneath a collapsible `历史记录` control in the sidebar.

#### Scenario: Sessions loaded
- **WHEN** app loads and `GET /api/sessions` returns a list
- **THEN** the expanded history group displays each session as a row with its title and relative timestamp

#### Scenario: Active session highlighted
- **WHEN** user selects a session
- **THEN** the application returns to chat view and that session row is visually highlighted with a distinct background

#### Scenario: History group is collapsed
- **WHEN** the user activates the expanded `历史记录` control
- **THEN** the session rows are hidden without changing or detaching the active chat

#### Scenario: History group is expanded
- **WHEN** the user activates the collapsed `历史记录` control
- **THEN** the existing session rows become visible again without another session being selected

### Requirement: Create new session
The system SHALL retain a visible `新建对话` command and allow the user to start a new conversation from any main view.

#### Scenario: New session created
- **WHEN** user clicks `新建对话`
- **THEN** app sends `{"type": "new_chat"}` over WebSocket, receives `{"event": "attached", "chat_id": "..."}`, switches to chat view, and displays the new empty chat

## ADDED Requirements

### Requirement: Navigate to the MCP market
The sidebar SHALL provide an `MCP 市场` navigation button separate from conversation creation and history expansion.

#### Scenario: User opens MCP market
- **WHEN** the user activates `MCP 市场`
- **THEN** the main area renders the MCP market while preserving the active chat and history group state

#### Scenario: User returns to a conversation
- **WHEN** the market is open and the user selects a history row
- **THEN** the application switches to chat view and attaches the selected session

