## MODIFIED Requirements

### Requirement: Rename a session
The system SHALL allow renaming a session by updating both its durable title and any live Agent metadata for that session, and the renamed title SHALL remain authoritative across later turns.

#### Scenario: Successful rename
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` with body `{"title": "新标题"}`
- **THEN** system updates the title in `memory/<chat_id>/metadata.json`, synchronizes the Agent's loaded session metadata, and returns `{"chat_id": "...", "title": "新标题"}` with HTTP 200

#### Scenario: Later turn follows rename
- **WHEN** a renamed session completes another Agent turn
- **THEN** the Agent persists other metadata without restoring the previous automatic title

#### Scenario: Rename occurs during a turn
- **WHEN** a valid rename is processed while the Agent is executing a turn for the same chat ID
- **THEN** both the in-flight metadata state and durable metadata retain the renamed title after that turn finishes or fails

#### Scenario: Session not found
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` for a non-existent chat_id
- **THEN** system returns HTTP 404 with `{"detail": "session not found"}`

#### Scenario: Empty title rejected
- **WHEN** client sends `PATCH /api/sessions/{chat_id}` with an empty or whitespace-only title
- **THEN** system returns HTTP 422
