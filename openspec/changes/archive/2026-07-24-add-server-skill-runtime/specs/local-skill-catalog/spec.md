## ADDED Requirements

### Requirement: Catalog loads validated local Skill packages
The system SHALL discover Skill packages containing a `SKILL.md` with valid YAML frontmatter, a non-empty body, and a normalized name that matches the package identity.

#### Scenario: Valid package is cataloged
- **WHEN** a package contains a valid `SKILL.md` and only supported package entries
- **THEN** the catalog exposes its normalized metadata, source kind, enabled state, content hash, version, and availability

#### Scenario: Malformed package is isolated
- **WHEN** one package has malformed YAML, invalid field types, an empty body, or an invalid name
- **THEN** the catalog marks or reports that package as invalid without preventing valid packages from loading

### Requirement: Catalog enforces package safety boundaries
The system SHALL reject package access or mutation that escapes its configured Skill roots, follows a symbolic link outside a package, exceeds configured size limits, or uses unsupported paths.

#### Scenario: Traversal path is rejected
- **WHEN** a Skill name or supporting-file path is absolute, contains a parent traversal, or resolves outside its package root
- **THEN** validation fails and no file outside the package is read or changed

#### Scenario: Oversized content is rejected
- **WHEN** a `SKILL.md` or supporting file exceeds its configured size limit
- **THEN** validation returns a size error and the content is not indexed or loaded

### Requirement: Catalog distinguishes Skill ownership kinds
The system SHALL classify effective Skills as `builtin`, `user`, or `agent`, SHALL keep built-ins read-only, and SHALL expose source and shadowing information when names overlap.

#### Scenario: Built-in mutation is denied
- **WHEN** a management operation attempts to replace, disable through package mutation, or delete a built-in Skill
- **THEN** the operation is rejected without changing the built-in package

#### Scenario: Higher-precedence source shadows a name
- **WHEN** enabled packages from multiple allowed sources have the same normalized name
- **THEN** the configured precedence selects one effective record and the catalog reports the shadowed sources

### Requirement: Catalog indexes metadata without loading bodies
The system SHALL index only bounded discovery metadata including name, description, tags, and trigger phrases, and SHALL NOT place all Skill bodies in the search index or model prompt.

#### Scenario: Catalog contains many Skills
- **WHEN** the catalog is built for any number of valid enabled packages
- **THEN** discovery index size and prompt exposure depend on bounded metadata rather than the combined `SKILL.md` bodies

### Requirement: Catalog reports dependency availability
The system SHALL report whether declared binaries, environment variables, built-in tools, and known MCP configurations are available without executing Skill scripts or starting optional services during catalog refresh.

#### Scenario: Required binary is missing
- **WHEN** an enabled Skill declares a required binary that is not found
- **THEN** the Skill remains discoverable with `missing_dependency` availability and identifies the missing binary

### Requirement: CashCode ships adapted built-in Skills
The system SHALL ship validated built-in packages for `weather`, `chart-visualization`, `github`, and `skill-creator` that reference CashCode tool names and runtime conventions.

#### Scenario: Built-in catalog starts
- **WHEN** the server initializes a new data directory
- **THEN** all four built-in packages appear in the catalog and `github` reports missing availability when `gh` is absent

