# Chat Skill Authoring Specification

## Purpose
Define managed, validated Skill creation from chat and protection of managed Skill roots.

## Requirements

### Requirement: Chat uses a managed Agent Skill authoring tool
The Agent runtime SHALL expose a server-managed Skill authoring tool for explicit user requests to create a Skill, and the tool SHALL route every mutation through the lifecycle-managed `SkillStore` rather than generic filesystem, shell, or HTTP commands.

#### Scenario: User requests a new Skill in chat
- **WHEN** the Agent has loaded the `skill-creator` contract and receives an explicit request to create a reusable Skill
- **THEN** it calls the managed authoring tool with a canonical slug and complete valid `SKILL.md` content

#### Scenario: Creator prepares localized metadata
- **WHEN** the requested title contains Chinese or other characters outside the canonical-name pattern
- **THEN** `skill-creator` uses an ASCII canonical `name`, preserves the requested title in `display_name`, and emits only frontmatter fields accepted by the CashCode loader

#### Scenario: Managed creation succeeds
- **WHEN** the authoring tool commits a valid unused package through the shared store
- **THEN** it returns structured success containing the canonical name, display name, hash, and `source=agent` only after the live catalog exposes that record

### Requirement: Chat-created Skills use protected Agent ownership
The managed authoring tool MUST force new packages into the Agent Skill root with server-owned enabled metadata and MUST NOT accept a caller-selected ownership source.

#### Scenario: Agent creates a package
- **WHEN** valid content is submitted through the managed authoring tool
- **THEN** the package is atomically published under the Agent root with `source=agent`, `enabled=true`, and server-owned runtime metadata

#### Scenario: Name conflicts with another ownership root
- **WHEN** the canonical name already exists in the built-in, user, or Agent root, including an invalid or shadowed directory
- **THEN** creation returns a structured conflict and no package or catalog record is changed

### Requirement: Authoring failures remain authoritative
The managed authoring tool SHALL return bounded structured validation, conflict, or permission errors and the Agent guidance SHALL prohibit claiming success when the tool did not return `success=true`.

#### Scenario: User supplies a Chinese title
- **WHEN** the Agent submits a safe ASCII slug, a bounded Chinese display name, and otherwise valid content
- **THEN** creation succeeds under the slug and subsequent user-facing Skill metadata uses the Chinese display name

#### Scenario: Canonical identity is invalid
- **WHEN** the submitted canonical name contains unsupported characters or does not match the package frontmatter identity
- **THEN** creation fails with an actionable slug error and no invalid package is left behind

#### Scenario: Creator receives validation failure
- **WHEN** managed creation rejects generated content under the current CashCode loader rules
- **THEN** the Agent corrects the content and retries the managed tool or reports failure, without writing a package through another tool

#### Scenario: Store operation fails
- **WHEN** validation, metadata creation, publication, or catalog refresh fails
- **THEN** the tool returns `success=false`, cleans temporary state, and does not report the Skill as created

### Requirement: Generic file tools protect managed Skill roots
Generic Agent filesystem mutation tools SHALL reject writes and edits targeting configured user or Agent Skill roots and SHALL direct the model to the managed Skill authoring tool.

#### Scenario: Agent attempts a direct SKILL.md write
- **WHEN** `write_file` or `edit_file` resolves a target below a managed Skill root
- **THEN** the operation is rejected before changing the filesystem and identifies the managed authoring tool to use

#### Scenario: Agent writes an ordinary workspace artifact
- **WHEN** a generic file mutation targets a path outside managed Skill roots but inside the allowed workspace
- **THEN** existing workspace file behavior remains unchanged
