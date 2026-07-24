## ADDED Requirements

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
