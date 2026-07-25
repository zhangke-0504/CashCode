# Local Skill Catalog Specification

## Purpose
Define secure discovery, validation, ownership, indexing, and availability reporting for local Skill packages.

## Requirements

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

### Requirement: Catalog separates canonical identity from display name
The catalog SHALL retain the validated lowercase package `name` as the immutable path, API, mention, and lookup identity and SHALL expose an optional bounded `display_name` for user-facing labels, falling back to the canonical name when absent.

#### Scenario: Skill declares a localized display name
- **WHEN** `renzhi-niuqu/SKILL.md` declares `name: renzhi-niuqu` and `display_name: 认知扭曲`
- **THEN** the catalog indexes and returns `renzhi-niuqu` as the canonical identity and `认知扭曲` as its display name

#### Scenario: Skill omits a display name
- **WHEN** a valid package has no `display_name`
- **THEN** catalog, market, and composer consumers use the canonical name as its display label

#### Scenario: Display name is edited
- **WHEN** a mutable Skill receives valid replacement content with the same canonical `name` and a changed valid `display_name`
- **THEN** the identity and package path remain unchanged while refreshed user-facing metadata uses the new display name

### Requirement: Catalog exposes bounded invalid-package diagnostics
The catalog SHALL keep malformed packages out of selectable results while exposing bounded source-aware diagnostics that do not include host paths, file contents, or unbounded exception text.

#### Scenario: Legacy direct write is invalid
- **WHEN** a directory under a configured Skill root contains `SKILL.md` with an invalid name, mismatched identity, malformed YAML, or unsupported package entry
- **THEN** valid Skills continue loading and the list response includes a bounded invalid-package diagnostic keyed by source and package directory

#### Scenario: Skill market receives invalid diagnostics
- **WHEN** the paginated Skill response contains invalid-package diagnostics
- **THEN** the market renders them as non-selectable error rows or a diagnostic section, with deletion as the only available action for mutable ownership sources

#### Scenario: User deletes an invalid mutable package
- **WHEN** the user confirms deletion of an invalid package from the user or Agent root
- **THEN** the server revalidates it as invalid, moves it out of the active root into a recoverable snapshot, refreshes the catalog, and removes its diagnostic without exposing edit, enable, or selection actions

#### Scenario: Invalid built-in package is displayed
- **WHEN** a diagnostic belongs to the built-in root
- **THEN** the market shows the error without a delete action and the server rejects direct deletion attempts

#### Scenario: Diagnostic contains a filesystem error
- **WHEN** underlying validation raises an error containing an absolute host path or excessive detail
- **THEN** the API returns a sanitized bounded message without exposing that path or content
