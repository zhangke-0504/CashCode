## MODIFIED Requirements

### Requirement: Session metadata stores title
Session metadata SHALL include a `title` field that is human-readable and can be set or updated by the user.

#### Scenario: Default title on first message
- **WHEN** a new session receives its first user message and no title has been set
- **THEN** the backend records the first 40 characters of that message as the default title in `session_metadata.json`

#### Scenario: Title updated via rename API
- **WHEN** `PATCH /api/sessions/{chat_id}` is called with a non-empty title string
- **THEN** the `title` field in `memory/<chat_id>/session_metadata.json` is updated and persisted

#### Scenario: Title read in session list
- **WHEN** `GET /api/sessions` is called
- **THEN** each session entry includes the `title` field from its `session_metadata.json`; sessions missing a title file show `"新对话"` as the default
