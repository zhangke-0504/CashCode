## ADDED Requirements

### Requirement: API lists and inspects local Skills
The server SHALL provide APIs to list effective Skills with filters and inspect one Skill's metadata, validation, dependencies, ownership, versions, and bounded content details.

#### Scenario: Client lists Skills
- **WHEN** `GET /api/skills` is requested with optional source, enabled, availability, or query filters
- **THEN** the response returns bounded catalog records and does not expose every full Skill body

#### Scenario: Client inspects one Skill
- **WHEN** `GET /api/skills/{name}` targets an existing Skill
- **THEN** the response identifies its effective source, metadata, current hash, validation state, dependency availability, and management permissions

### Requirement: API manages mutable Skill packages safely
The server SHALL provide create, replace, enable/disable, delete, and validate operations for mutable user and agent Skills through the shared Skill store.

#### Scenario: Valid user Skill is created
- **WHEN** a create request contains a valid unused name and valid package content
- **THEN** the server atomically creates the package, updates the catalog revision, and makes it discoverable without restart

#### Scenario: Invalid mutation is requested
- **WHEN** a request contains invalid YAML, forbidden paths, unsupported files, excessive content, a stale write precondition, or targets an immutable built-in
- **THEN** the API returns a client or conflict error and leaves the existing catalog and package unchanged

### Requirement: API versions and rolls back mutable Skills
The system SHALL snapshot a mutable Skill before replacement or approved evolution, SHALL expose its available versions, and SHALL validate and atomically restore a selected version.

#### Scenario: Existing Skill is replaced
- **WHEN** a valid replacement is accepted
- **THEN** the previous package is retained as a version snapshot and the new package receives a new version and content hash

#### Scenario: Client rolls back a version
- **WHEN** `POST /api/skills/{name}/rollback/{version}` targets an allowed valid snapshot
- **THEN** the current package is snapshotted, the target version is restored atomically, and the catalog is refreshed

### Requirement: API and agent share one live catalog service
The FastAPI application and Agent Loop SHALL use the same lifecycle-managed catalog/store instance.

#### Scenario: API changes a Skill while server is running
- **WHEN** a management operation commits successfully
- **THEN** later agent searches and loads observe the new catalog revision without process restart

