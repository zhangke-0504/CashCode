## MODIFIED Requirements

### Requirement: Session metadata stores title
Session metadata SHALL include a human-readable `title` field, assign it automatically only for a new session's first accepted user question, and preserve every existing or user-provided title from later automatic replacement.

#### Scenario: Default title on first accepted message
- **WHEN** a session with no title and no prior durable user history has its first non-empty user question accepted
- **THEN** the backend trims the question, collapses consecutive whitespace to one space, stores at most the first 40 Unicode characters as `title` in `memory/<chat_id>/metadata.json`, and does so before assistant execution completes

#### Scenario: Accepted first turn later fails
- **WHEN** the first user question has been accepted and titled but assistant or tool execution later fails
- **THEN** the assigned session title remains persisted

#### Scenario: Existing title is not automatically replaced
- **WHEN** any user message is accepted for a session whose metadata already contains a non-empty title
- **THEN** automatic title assignment leaves that title unchanged

#### Scenario: Legacy untitled session has durable history
- **WHEN** a session has durable user history but no persisted title and receives another message
- **THEN** the backend does not derive a title from that later message and the session remains eligible for manual rename

#### Scenario: Title updated via rename API
- **WHEN** `PATCH /api/sessions/{chat_id}` is called with a non-empty title string
- **THEN** the `title` field in `memory/<chat_id>/metadata.json` is updated and persisted

#### Scenario: Title read in session list
- **WHEN** `GET /api/sessions` is called
- **THEN** each session entry includes the title from its metadata and sessions missing a title show `新对话` as the presentation fallback
