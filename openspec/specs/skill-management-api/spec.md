# Skill Management API Specification

## Purpose
Define safe inspection, mutation, versioning, rollback, and live catalog behavior for Skill management APIs.

## Requirements

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
The server SHALL provide create, replace, enable/disable, delete, and validate operations for mutable user and agent Skills through the shared Skill store, SHALL require mutable content replacement to preserve source and identity, SHALL keep built-ins immutable regardless of client-supplied fields, SHALL reject new duplicate identities across every ownership root, and SHALL expose the same guarded store to managed Agent authoring.

#### Scenario: Valid user Skill is created
- **WHEN** a create request contains a valid unused name and valid package content
- **THEN** the server atomically creates the package, updates the catalog revision, and makes it discoverable without restart

#### Scenario: Valid Agent Skill is created
- **WHEN** the managed Agent authoring tool submits valid content for an unused canonical name
- **THEN** the shared store atomically creates an enabled Agent-owned package and makes it visible to API listing, Skill search, and chat selection without restart

#### Scenario: Duplicate exists in another root
- **WHEN** create or import targets a canonical name whose directory exists in any built-in, user, or Agent root
- **THEN** the store returns a conflict without shadowing, replacing, or publishing another package

#### Scenario: User edits uploaded Skill content
- **WHEN** a replacement for a `user` Skill contains valid `SKILL.md` content with the same name and current expected hash while omitting supporting files
- **THEN** the server snapshots the previous package, replaces only `SKILL.md`, preserves all existing supporting files byte-for-byte, revalidates the whole package, and refreshes the catalog

#### Scenario: User edits agent-created Skill content
- **WHEN** a replacement for an `agent` Skill contains valid `SKILL.md` content with the same name and current expected hash
- **THEN** the same snapshot, validation, atomic replacement, and live refresh guarantees apply without changing its `agent` ownership

#### Scenario: Invalid mutation is requested
- **WHEN** a request contains invalid YAML, forbidden paths, unsupported files, excessive content, a stale write precondition, a mismatched canonical identity, or targets an immutable built-in
- **THEN** the API or managed tool returns a client, conflict, or permission error and leaves the existing catalog and package unchanged

#### Scenario: Invalid package deletion is requested
- **WHEN** a source/directory diagnostic identifies an invalid user or Agent package and the user confirms deletion
- **THEN** the shared store revalidates the physical directory, snapshots and removes it from the active root atomically, refreshes the catalog, and returns success without treating it as a normal Skill identity

#### Scenario: Invalid deletion target became valid
- **WHEN** the target package is valid, built-in, missing, nested, or no longer matches an invalid diagnostic
- **THEN** the API rejects the request without deleting or moving that package

### Requirement: API versions and rolls back mutable Skills
The system SHALL snapshot a mutable Skill before replacement or approved evolution, SHALL expose its available versions, and SHALL validate and atomically restore a selected version.

#### Scenario: Existing Skill is replaced
- **WHEN** a valid replacement is accepted
- **THEN** the previous package is retained as a version snapshot and the new package receives a new version and content hash

#### Scenario: Client rolls back a version
- **WHEN** `POST /api/skills/{name}/rollback/{version}` targets an allowed valid snapshot
- **THEN** the current package is snapshotted, the target version is restored atomically, and the catalog is refreshed

### Requirement: API and agent share one live catalog service
The FastAPI application and Agent Loop SHALL use the same lifecycle-managed `SkillCatalog` and `SkillStore` instances for API mutations, chat authoring, discovery, loading, and evolution approval.

#### Scenario: API changes a Skill while server is running
- **WHEN** a management operation commits successfully
- **THEN** later agent searches and loads observe the new catalog revision without process restart

#### Scenario: Agent creates a Skill while server is running
- **WHEN** managed chat authoring commits successfully
- **THEN** the Skill list API and composer-selectable query observe the same new Agent record without process restart or explicit filesystem refresh

#### Scenario: Store is unavailable during startup
- **WHEN** the shared store has not completed lifecycle initialization
- **THEN** neither the API nor Agent tool exposes a partially initialized mutation path
