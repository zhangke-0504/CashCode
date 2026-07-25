## ADDED Requirements

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

