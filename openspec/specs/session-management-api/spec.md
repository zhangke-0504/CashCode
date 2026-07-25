# Session Management API Specification

## Purpose
Define session listing, renaming, deletion, and safe persistence and retrieval of selected capability references.

## Requirements

### Requirement: List all sessions
The system SHALL provide a REST endpoint to list all existing sessions with metadata.

#### Scenario: Sessions exist
- **WHEN** client sends `GET /api/sessions`
- **THEN** system returns `{"sessions": [{"chat_id": "...", "title": "...", "created_at": "...", "updated_at": "..."}]}` with HTTP 200

#### Scenario: No sessions exist
- **WHEN** client sends `GET /api/sessions` and the memory directory is empty
- **THEN** system returns `{"sessions": []}` with HTTP 200

### Requirement: Rename a session
The system SHALL allow renaming a session by updating its title in session metadata.

#### Scenario: Successful rename
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` with body `{"title": "新标题"}`
- **THEN** system updates the title in `memory/<chat_id>/session_metadata.json` and returns `{"chat_id": "...", "title": "新标题"}` with HTTP 200

#### Scenario: Session not found
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` for a non-existent chat_id
- **THEN** system returns HTTP 404 with `{"detail": "session not found"}`

#### Scenario: Empty title rejected
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` with an empty or whitespace-only title
- **THEN** system returns HTTP 422

### Requirement: Delete a session
The system SHALL allow deleting a session and all its associated data.

#### Scenario: Successful delete
- **WHEN** client sends `DELETE /api/sessions/{chat_id}`
- **THEN** system removes the `memory/<chat_id>/` directory entirely and returns HTTP 204

#### Scenario: Session not found on delete
- **WHEN** client sends `DELETE /api/sessions/{chat_id}` for a non-existent chat_id
- **THEN** system returns HTTP 404 with `{"detail": "session not found"}`

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
