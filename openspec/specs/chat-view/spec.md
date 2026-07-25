# Chat View Specification

## Purpose
Define conversation rendering, streaming presentation, scrolling behavior, tool progress, and selected capability references in the chat view.

## Requirements

### Requirement: Display conversation messages
The system SHALL render all messages in the active session as a scrollable conversation list.

#### Scenario: Empty state
- **WHEN** the active session has no messages
- **THEN** the chat area displays CashMe.png centered with a welcome prompt

#### Scenario: Messages loaded
- **WHEN** session has existing messages
- **THEN** each message is displayed as a bubble: user messages right-aligned, assistant messages left-aligned with Markdown rendering

#### Scenario: Streaming assistant message
- **WHEN** server is sending delta frames for an active response
- **THEN** the assistant bubble grows in real time and a typing cursor is shown at the end

### Requirement: Auto-scroll to latest message
The system SHALL keep the view scrolled to the newest content during streaming.

#### Scenario: New content arrives
- **WHEN** a new message or delta frame is added and the user has not manually scrolled up
- **THEN** the chat area auto-scrolls to show the newest content

#### Scenario: User has scrolled up
- **WHEN** the user manually scrolls up while streaming is in progress
- **THEN** auto-scroll is paused; a "↓ 跳到最新" button appears; clicking it resumes auto-scroll

### Requirement: Render assistant messages as Markdown
The system SHALL parse and render assistant message content using react-markdown with GFM support.

#### Scenario: Code block rendering
- **WHEN** assistant message contains a fenced code block
- **THEN** it is rendered with syntax highlighting and a copy button

#### Scenario: Table rendering
- **WHEN** assistant message contains a GFM table
- **THEN** it is rendered as an HTML table with horizontal scroll if needed

### Requirement: Display tool call progress blocks
The system SHALL render tool calls as collapsible blocks above the assistant reply.

#### Scenario: Tool call in progress
- **WHEN** a `tool_call` event arrives
- **THEN** a progress row appears showing the tool name and a spinner

#### Scenario: Tool call completed
- **WHEN** the corresponding `tool_result` event arrives
- **THEN** the row updates to show a checkmark and a preview of the result (truncated at 200 chars)

### Requirement: Render selected capability references on user messages
The chat view SHALL render Skill and MCP selection receipts as compact typed references associated with the user message, using the display label with canonical identity as fallback.

#### Scenario: Optimistic selected message is rendered
- **WHEN** the user sends a message with Skill or MCP chips
- **THEN** the optimistic user bubble immediately shows matching Skill/MCP references and plain task content

#### Scenario: Persisted selected message is loaded
- **WHEN** session history returns selection receipts
- **THEN** the restored user bubble shows the same reference types and labels as the sent message

#### Scenario: Display label is absent
- **WHEN** a persisted reference has a canonical identity but no usable label
- **THEN** the chat view displays the canonical Skill name or MCP server name without breaking layout

#### Scenario: Message has no references
- **WHEN** a user message contains no selection metadata
- **THEN** the bubble retains the existing plain-content rendering with no empty reference container
