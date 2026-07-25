# Skill Market View Specification

## Purpose
Define discovery, inspection, upload, editing, and lifecycle management behavior for the local Skill market.

## Requirements

### Requirement: Display the local Skill market
The application SHALL provide a `Skill 市场` main view that lists effective local Skills through the paginated Skill API without filtering out disabled or dependency-blocked entries.

#### Scenario: Skill market opens successfully
- **WHEN** the user selects `Skill 市场` in the sidebar
- **THEN** the application preserves the attached chat, requests the first Skill page, and renders each returned Skill with its name, description, version, source, enabled state, availability, and missing dependencies

#### Scenario: Skill market is loading
- **WHEN** a Skill list request is pending
- **THEN** the market displays stable loading placeholders without shifting its search, paging, or upload controls

#### Scenario: Skill market fails to load
- **WHEN** the Skill list request fails
- **THEN** the market displays a bounded error and an explicit retry action without claiming the list is empty

#### Scenario: Skill catalog is empty
- **WHEN** the Skill list succeeds with no entries
- **THEN** the market displays an empty state and keeps the upload action available

### Requirement: Search and page through Skills
The Skill market SHALL use server-side query and pagination so navigation cost does not depend on loading every installed Skill body.

#### Scenario: User searches the market
- **WHEN** the user submits or debounces a non-empty Skill query
- **THEN** the market requests matching catalog metadata, resets to the first page, and renders the authoritative result count

#### Scenario: User changes page
- **WHEN** more results exist and the user selects another page
- **THEN** the market requests that page while keeping the controls and list dimensions stable

### Requirement: Distinguish Skill ownership and status
The market SHALL label built-in Skills as `内置`, distinguish user-uploaded and agent-created Skills, and present unavailable states without treating them as usable.

#### Scenario: Built-in Skill is rendered
- **WHEN** a Skill record has `source=builtin` and `mutable=false`
- **THEN** its row displays `内置` and offers no edit, enable/disable, or delete command

#### Scenario: Uploaded Skill is rendered
- **WHEN** a Skill record has `source=user` and `mutable=true`
- **THEN** its row identifies user ownership and exposes mutable management commands

#### Scenario: Agent-created Skill is rendered
- **WHEN** a valid Skill created through the managed chat/agent path has `source=agent`
- **THEN** it appears in the same market with an agent-created label and mutable management commands

#### Scenario: Skill has a missing dependency
- **WHEN** a Skill record has `availability=missing_dependency`
- **THEN** its row identifies the blocked status and displays the bounded missing-dependency list

### Requirement: Edit mutable Skill instructions
The market SHALL allow users to inspect complete Skill instructions and edit the full `SKILL.md` only when the server reports the Skill as mutable.

#### Scenario: User opens an uploaded or agent Skill
- **WHEN** the user selects edit for a mutable Skill
- **THEN** the editor loads the complete current `SKILL.md`, records its content hash, keeps the Skill name immutable, and exposes Save and Cancel actions

#### Scenario: Valid Skill edit succeeds
- **WHEN** the user saves valid changed content with the current hash
- **THEN** the editor closes, the market refreshes the row, and the updated Skill is available to later agent turns without restart

#### Scenario: Skill edit is invalid
- **WHEN** the server rejects edited YAML, identity, body, size, or dependency metadata
- **THEN** the editor remains open with the draft preserved and displays the returned validation error

#### Scenario: Skill changed concurrently
- **WHEN** save returns a hash conflict
- **THEN** the editor preserves the user's draft, reports that the installed Skill changed, and does not claim the draft was saved

### Requirement: Manage mutable Skill lifecycle
The market SHALL expose enable/disable and confirmed deletion only for mutable Skills and SHALL refresh authoritative catalog state after each operation.

#### Scenario: User disables a mutable Skill
- **WHEN** an enabled mutable Skill is disabled successfully
- **THEN** it remains visible in the market as disabled and is absent from later selectable-Skill results

#### Scenario: User confirms deletion
- **WHEN** the user confirms deletion of a mutable Skill and the API succeeds
- **THEN** the market removes the row after refreshing and the Skill is unavailable to later searches and selections

#### Scenario: User cancels deletion
- **WHEN** the user cancels the delete confirmation
- **THEN** no delete request is sent and the installed Skill remains unchanged

#### Scenario: Mutable action fails
- **WHEN** enable, disable, or delete fails
- **THEN** the market retains the authoritative row and displays the bounded server error

### Requirement: Upload a Skill package from the market
The market SHALL provide a ZIP upload dialog that submits one selected package and reports server validation outcomes.

#### Scenario: User selects a non-ZIP file
- **WHEN** the selected file is not a `.zip` package
- **THEN** the client blocks submission and displays a concise file-type error

#### Scenario: Skill upload succeeds
- **WHEN** the user submits a valid non-conflicting ZIP and the import API succeeds
- **THEN** the dialog closes, the market refreshes, and the new user-owned Skill is visible

#### Scenario: Skill upload fails validation
- **WHEN** the import API rejects the archive or package
- **THEN** the dialog stays open with the selected filename and displays the bounded server error
