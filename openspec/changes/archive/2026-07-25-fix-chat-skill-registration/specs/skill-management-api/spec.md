## MODIFIED Requirements

### Requirement: API manages mutable Skill packages safely
The server SHALL provide create, replace, enable/disable, delete, and validate operations for mutable user and agent Skills through the shared Skill store, SHALL reject new duplicate identities across every ownership root, and SHALL expose the same guarded store to managed Agent authoring.

#### Scenario: Valid user Skill is created
- **WHEN** a create request contains a valid unused name and valid package content
- **THEN** the server atomically creates the package, updates the catalog revision, and makes it discoverable without restart

#### Scenario: Valid Agent Skill is created
- **WHEN** the managed Agent authoring tool submits valid content for an unused canonical name
- **THEN** the shared store atomically creates an enabled Agent-owned package and makes it visible to API listing, Skill search, and chat selection without restart

#### Scenario: Duplicate exists in another root
- **WHEN** create or import targets a canonical name whose directory exists in any built-in, user, or Agent root
- **THEN** the store returns a conflict without shadowing, replacing, or publishing another package

#### Scenario: Invalid mutation is requested
- **WHEN** a request contains invalid YAML, forbidden paths, unsupported files, excessive content, a stale write precondition, a mismatched canonical identity, or targets an immutable built-in
- **THEN** the API or managed tool returns a client, conflict, or permission error and leaves the existing catalog and package unchanged

#### Scenario: Invalid package deletion is requested
- **WHEN** a source/directory diagnostic identifies an invalid user or Agent package and the user confirms deletion
- **THEN** the shared store revalidates the physical directory, snapshots and removes it from the active root atomically, refreshes the catalog, and returns success without treating it as a normal Skill identity

#### Scenario: Invalid deletion target became valid
- **WHEN** the target package is valid, built-in, missing, nested, or no longer matches an invalid diagnostic
- **THEN** the API rejects the request without deleting or moving that package

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
