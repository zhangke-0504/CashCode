## ADDED Requirements

### Requirement: Return persisted capability references with session messages
The system SHALL persist bounded canonical Skill/MCP selection receipts on user history entries and return them from `GET /api/sessions/{chat_id}/messages` without exposing model-only instructions or MCP secrets.

#### Scenario: Selected message is persisted
- **WHEN** a completed user turn contained sanitized Skill or MCP selections
- **THEN** its durable user entry stores task content plus canonical identity and bounded display label receipts

#### Scenario: Selected message history is requested
- **WHEN** the client requests messages for a session containing selection receipts
- **THEN** the corresponding user message includes normalized `mentioned_skills` and `selected_mcp_connectors` arrays

#### Scenario: Legacy history is requested
- **WHEN** a persisted user message has no selection receipts
- **THEN** the API returns its existing role and content without fabricating selection metadata

#### Scenario: Persisted MCP configuration contains headers
- **WHEN** history is projected for a turn that selected an MCP configured with secret headers
- **THEN** no URL header key, header value, or other transport secret appears in the history response

