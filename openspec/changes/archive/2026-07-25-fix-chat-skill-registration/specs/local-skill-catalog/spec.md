## ADDED Requirements

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
