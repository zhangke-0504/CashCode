## ADDED Requirements

### Requirement: Open a two-level capability picker with at-sign
The Composer SHALL open a first-level capability picker when the user types `@` at a valid token boundary, with `MCP` and `Skill` as the available categories.

#### Scenario: At-sign is typed at a boundary
- **WHEN** the caret follows the start of input or whitespace and the user types `@`
- **THEN** the Composer opens the category picker without submitting or modifying other task text

#### Scenario: At-sign appears inside ordinary text
- **WHEN** the user types an at-sign inside an email address or another non-boundary token
- **THEN** the Composer treats it as ordinary text and does not open the capability picker

#### Scenario: User chooses a category
- **WHEN** the user selects `MCP` or `Skill`
- **THEN** the picker opens the corresponding searchable second-level list and provides a way to return to the category level

### Requirement: List only currently usable capabilities
The second-level picker SHALL list only connected managed MCP servers for `MCP` and only enabled, available local Skills for `Skill`.

#### Scenario: MCP category opens
- **WHEN** the user opens the MCP list
- **THEN** the client refreshes managed MCP status and lists entries that are connected with at least one discovered tool

#### Scenario: Skill category opens
- **WHEN** the user opens the Skill list
- **THEN** the client requests Skills filtered to `enabled=true` and `availability=available` and displays their names and descriptions

#### Scenario: Capability list request fails
- **WHEN** the active category cannot be loaded
- **THEN** the picker shows a bounded retryable error and does not display stale entries as selectable

### Requirement: Search and navigate picker results
The Composer SHALL filter second-level results by display name, canonical name, and description and SHALL support mouse and keyboard selection.

#### Scenario: User types a picker query
- **WHEN** the second-level list is open and the user types after the `@` trigger
- **THEN** visible results are filtered case-insensitively without adding the query to submitted task content

#### Scenario: User uses keyboard navigation
- **WHEN** the picker is open and the user presses ArrowUp, ArrowDown, Enter, Escape, or the defined back command
- **THEN** focus moves predictably, Enter chooses the active row, Escape closes the picker, and back returns to the category level when applicable

### Requirement: Represent selections as removable chips
The Composer SHALL remove the consumed `@` trigger/query from task text and render each chosen Skill or MCP as a stable removable chip associated with its canonical identity.

#### Scenario: User selects a Skill
- **WHEN** the user chooses an available Skill
- **THEN** one Skill chip is added and the task-text caret returns to the Composer

#### Scenario: User selects an MCP
- **WHEN** the user chooses a connected MCP server
- **THEN** one MCP chip is added and the task-text caret returns to the Composer

#### Scenario: Duplicate capability is selected
- **WHEN** the same canonical Skill or MCP is chosen again
- **THEN** the Composer keeps one chip rather than creating a duplicate

#### Scenario: User removes a chip
- **WHEN** the user activates a chip's remove control
- **THEN** that selection is removed from the pending message without altering task text

#### Scenario: Selection limit is reached
- **WHEN** the pending message already contains eight combined Skill/MCP selections
- **THEN** the Composer prevents another selection and presents a concise limit message

### Requirement: Submit selection metadata with task text
The Composer SHALL submit plain task text together with canonical chip metadata and SHALL clear text and chips only after the message is accepted for sending.

#### Scenario: Message with selections is submitted
- **WHEN** the user submits non-empty task text with one or more chips
- **THEN** the outgoing action contains the text plus matching `mentioned_skills` and `selected_mcp_connectors` records

#### Scenario: Only chips are present
- **WHEN** the task text is empty or whitespace-only but chips are selected
- **THEN** the Composer preserves the existing empty-message rule and does not send the message

#### Scenario: Send begins
- **WHEN** a valid selected message is accepted for sending
- **THEN** the Composer clears its task text, selection chips, picker state, and query

