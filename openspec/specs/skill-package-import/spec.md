# Skill Package Import Specification

## Purpose
Define safe ZIP package ingestion and atomic publication for user-owned Skills.

## Requirements

### Requirement: API accepts one ZIP Skill package
The server SHALL provide a multipart Skill import endpoint that accepts exactly one `.zip` archive containing one package and always installs it as a user-owned Skill.

#### Scenario: Flat Skill archive is uploaded
- **WHEN** a valid archive contains `SKILL.md` and allowed supporting directories at the ZIP root
- **THEN** the importer derives the canonical name from validated frontmatter and installs one user Skill under that name

#### Scenario: Wrapped Skill archive is uploaded
- **WHEN** a valid archive contains `SKILL.md` inside exactly one top-level directory
- **THEN** the importer treats that directory as a wrapper, derives identity from validated frontmatter, and installs one user Skill

#### Scenario: Archive contains no unique Skill root
- **WHEN** an archive has no `SKILL.md` root or has multiple candidate package roots
- **THEN** the API returns a validation error and installs nothing

#### Scenario: Unsupported archive type is uploaded
- **WHEN** the upload is not a valid ZIP archive
- **THEN** the API returns a client error and does not inspect it as another archive format

### Requirement: Import enforces archive safety bounds
The importer MUST enforce configured compressed size, entry count, per-file size, and total uncompressed size limits and MUST reject unsafe member types or paths before publishing the package.

#### Scenario: Archive path escapes extraction root
- **WHEN** a normalized member path is absolute, drive-qualified, or contains parent traversal
- **THEN** import fails without reading or writing outside the temporary extraction root

#### Scenario: Archive contains unsafe member metadata
- **WHEN** an archive contains an encrypted entry, symlink, duplicate normalized path, or unsupported special file type
- **THEN** import fails and no package is published

#### Scenario: Archive exceeds a configured bound
- **WHEN** compressed bytes, entry count, an individual file, or total expanded bytes exceed the configured limit
- **THEN** import fails before the package becomes visible and temporary data is cleaned up

### Requirement: Imported package uses server-owned metadata
The importer SHALL validate the extracted package with the existing Skill package rules and SHALL replace any archive-provided runtime metadata with server-owned user metadata.

#### Scenario: Archive supplies ownership metadata
- **WHEN** a valid package includes `_meta.json` claiming built-in or agent ownership or a disabled state
- **THEN** the installed package is recorded as an enabled `user` Skill and the untrusted ownership fields do not take effect

#### Scenario: Extracted package violates Skill format
- **WHEN** `SKILL.md` has invalid frontmatter, an invalid or empty body, an invalid name, or the package has unsupported root entries
- **THEN** the API returns a validation error and installs nothing

#### Scenario: Package contains binary supporting assets
- **WHEN** a valid allowed supporting file is binary and within configured limits
- **THEN** import preserves its bytes without coercing it through a text encoding

### Requirement: Import rejects every existing Skill name
The importer SHALL reject a canonical name that already exists in any built-in, user, or agent Skill root, including a source currently hidden by catalog precedence.

#### Scenario: Uploaded name matches a built-in
- **WHEN** the imported frontmatter name matches a built-in Skill
- **THEN** the API returns `409`, preserves the built-in package, and creates no user shadow

#### Scenario: Uploaded name matches a mutable Skill
- **WHEN** the imported frontmatter name matches an existing user or agent package
- **THEN** the API returns `409` and directs replacement through the existing edit lifecycle rather than overwriting files

### Requirement: Import publishes atomically to the live catalog
The importer SHALL fully validate a hidden temporary tree before atomically publishing the final directory and refreshing the shared catalog.

#### Scenario: Import succeeds
- **WHEN** all archive and package validation completes and the destination is still unused
- **THEN** one final package directory is published, the catalog revision advances, and both API listing and later agent discovery observe the Skill without restart

#### Scenario: Import fails before publication
- **WHEN** extraction, validation, metadata creation, or final conflict checking fails
- **THEN** temporary files are removed, the catalog is unchanged, and no partial destination directory remains
