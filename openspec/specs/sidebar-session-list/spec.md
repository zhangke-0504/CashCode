# Sidebar Session List Specification

## Purpose
Define session history navigation, conversation creation and management, and access to the MCP market from the sidebar.

## Requirements

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

### Requirement: Navigate to the MCP market
The sidebar SHALL provide an `MCP 市场` navigation button separate from conversation creation and history expansion.

#### Scenario: User opens MCP market
- **WHEN** the user activates `MCP 市场`
- **THEN** the main area renders the MCP market while preserving the active chat and history group state

#### Scenario: User returns to a conversation
- **WHEN** the market is open and the user selects a history row
- **THEN** the application switches to chat view and attaches the selected session

### Requirement: Navigate to the Skill market
The sidebar SHALL provide a `Skill 市场` navigation button separate from conversation creation, the MCP market, and history expansion.

#### Scenario: User opens Skill market
- **WHEN** the user activates `Skill 市场`
- **THEN** the main area renders the Skill market while preserving the active chat attachment and history expansion state

#### Scenario: Skill market navigation is active
- **WHEN** the Skill market is the current main view
- **THEN** its sidebar navigation row is visually identified as the current page without highlighting the MCP market

#### Scenario: User returns to a conversation from Skill market
- **WHEN** the Skill market is open and the user selects a history row or creates a new conversation
- **THEN** the application switches to chat view and attaches or creates the requested session

### Requirement: Navigate to LLM settings from a bottom settings menu
The sidebar SHALL pin a `设置` control with a gear icon below the scrollable session history and SHALL open an upward menu containing an `LLM 设置` command.

#### Scenario: User opens the settings menu
- **WHEN** the user activates the bottom `设置` control
- **THEN** an upward menu appears above the control with `LLM 设置` as its only current item and the control exposes its expanded state accessibly

#### Scenario: User opens LLM settings
- **WHEN** the user activates `LLM 设置`
- **THEN** the application closes the menu, renders the LLM settings view in the main area, and preserves the active chat and session history state

#### Scenario: User dismisses the settings menu
- **WHEN** the menu is open and the user presses Escape, clicks outside it, or activates the settings control again
- **THEN** the menu closes without changing the current main view

#### Scenario: User opens LLM settings on mobile
- **WHEN** the mobile sidebar is open and the user activates `LLM 设置`
- **THEN** the application renders the settings view and closes the mobile sidebar overlay
