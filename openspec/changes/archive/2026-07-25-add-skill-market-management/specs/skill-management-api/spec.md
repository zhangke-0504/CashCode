## MODIFIED Requirements

### Requirement: API lists and inspects local Skills
The server SHALL provide APIs to list effective Skills with filters and pagination, inspect one Skill's metadata, validation, dependencies, ownership, versions, and bounded content details, and retrieve complete editable `SKILL.md` content separately without exposing supporting file bodies or filesystem paths.

#### Scenario: Client lists Skills
- **WHEN** `GET /api/skills` is requested with optional source, enabled, availability, query, page, or page-size filters
- **THEN** the response returns bounded catalog records and pagination metadata without exposing every full Skill body

#### Scenario: Client inspects one Skill
- **WHEN** `GET /api/skills/{name}` targets an existing Skill
- **THEN** the response identifies its effective source, metadata, current hash, validation state, dependency availability, and management permissions

#### Scenario: Client loads Skill content for editing
- **WHEN** `GET /api/skills/{name}/content` targets an existing effective Skill
- **THEN** the response returns the complete bounded UTF-8 `SKILL.md`, current content hash, source, and mutability without returning support-file contents or a host filesystem path

### Requirement: API manages mutable Skill packages safely
The server SHALL provide create, replace, enable/disable, delete, and validate operations for mutable user and agent Skills through the shared Skill store, SHALL require mutable content replacement to preserve source and identity, and SHALL keep built-ins immutable regardless of client-supplied fields.

#### Scenario: Valid user Skill is created
- **WHEN** a create request contains a valid unused name and valid package content
- **THEN** the server atomically creates the package, updates the catalog revision, and makes it discoverable without restart

#### Scenario: User edits uploaded Skill content
- **WHEN** a replacement for a `user` Skill contains valid `SKILL.md` content with the same name and current expected hash while omitting supporting files
- **THEN** the server snapshots the previous package, replaces only `SKILL.md`, preserves all existing supporting files byte-for-byte, revalidates the whole package, and refreshes the catalog

#### Scenario: User edits agent-created Skill content
- **WHEN** a replacement for an `agent` Skill contains valid `SKILL.md` content with the same name and current expected hash
- **THEN** the same snapshot, validation, atomic replacement, and live refresh guarantees apply without changing its `agent` ownership

#### Scenario: Invalid mutation is requested
- **WHEN** a request contains invalid YAML, a changed Skill identity, forbidden paths, unsupported files, excessive content, a stale write precondition, or targets an immutable built-in
- **THEN** the API returns a client, conflict, or permission error and leaves the existing catalog and package unchanged
