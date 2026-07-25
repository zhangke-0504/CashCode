# MCP Market View Specification

## Purpose
Define the MCP market experience for discovering managed servers, distinguishing built-in and user entries, and managing user-configured SSE connections.

## Requirements

### Requirement: Display the MCP market
The system SHALL provide an `MCP 市场` main view that loads and displays every managed MCP server with its display name, description, transport, source badge, lifecycle status, and tool count.

#### Scenario: Market opens successfully
- **WHEN** the user selects `MCP 市场` in the sidebar
- **THEN** the application switches from chat to the market, requests `GET /api/mcp/servers`, and renders the returned entries

#### Scenario: Market is loading
- **WHEN** the server list request is pending
- **THEN** the market shows stable loading placeholders without shifting the page controls

#### Scenario: Market fails to load
- **WHEN** the server list request fails
- **THEN** the market displays a bounded error and an explicit retry action

### Requirement: Distinguish built-in and user MCP entries
The market SHALL label built-in entries as `内置`, hide edit/delete actions for them, and expose edit/delete actions only for mutable user entries.

#### Scenario: Built-in entry is rendered
- **WHEN** an MCP DTO has `builtin: true`
- **THEN** its row shows the `内置` label and provides connection controls but no edit or delete command

#### Scenario: User entry is rendered
- **WHEN** an MCP DTO has `mutable: true`
- **THEN** its row provides edit and delete commands in addition to connection controls

### Requirement: Create and edit user MCP entries
The market SHALL provide a validated user MCP form for internal name, display title, description, SSE URL, and optional header key/value pairs.

#### Scenario: User opens the create form
- **WHEN** the user activates the market's new MCP command
- **THEN** the form opens in SSE mode with empty identity and connection fields and Save/Cancel actions

#### Scenario: Invalid form is submitted
- **WHEN** a required field is empty, the internal name is invalid, the URL is not HTTP(S), or a header row is malformed
- **THEN** submission is blocked and the relevant field receives a concise validation error

#### Scenario: User saves a new MCP
- **WHEN** the form is valid and the create API succeeds
- **THEN** the form closes, the new disconnected entry appears in the market, and no connection is claimed

#### Scenario: User edits an MCP
- **WHEN** a mutable entry is edited and the update API succeeds
- **THEN** the market refreshes that entry and shows it disconnected if it was previously connected

### Requirement: Connect and disconnect from the market
Each market entry SHALL expose a connection command appropriate to its current lifecycle state and SHALL refresh authoritative status after the operation.

#### Scenario: User connects a disconnected MCP
- **WHEN** the user activates `连接`
- **THEN** the control enters a stable working state, calls the connect API once, and then displays connected status and discovered tool count on success

#### Scenario: Connection fails
- **WHEN** the connect API returns error status
- **THEN** the entry shows `连接失败`, exposes the bounded server error, and permits a later retry

#### Scenario: User disconnects a connected MCP
- **WHEN** the user activates `断开`
- **THEN** the market calls the disconnect API and renders the returned disconnected state with zero live tools

### Requirement: Delete user MCP entries with confirmation
The market SHALL require confirmation before deleting a mutable user entry and SHALL keep the entry visible when deletion fails.

#### Scenario: User confirms delete
- **WHEN** the user confirms deletion and the delete API succeeds
- **THEN** the market removes the entry and it is absent from future composer MCP lists

#### Scenario: User cancels delete
- **WHEN** the user cancels the confirmation
- **THEN** no API request is sent and the entry remains unchanged

#### Scenario: Delete fails
- **WHEN** runtime cleanup or persistence fails during deletion
- **THEN** the entry remains visible and the market displays the returned error instead of claiming deletion
