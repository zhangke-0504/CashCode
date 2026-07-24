## ADDED Requirements

### Requirement: Agent can search Skills by natural-language intent
The system SHALL expose an always-available `skill_search` tool that returns a bounded ranked list of enabled Skill metadata matching a natural-language query.

#### Scenario: Natural-language query matches a Skill
- **WHEN** the model searches for a workflow described by a Skill's name, description, tags, or trigger phrases
- **THEN** `skill_search` returns that Skill with identity, description, version, source, and availability without returning its full body

#### Scenario: Search has no useful match
- **WHEN** no enabled Skill meets the configured relevance threshold
- **THEN** `skill_search` returns an empty result with no Skill activation side effect

### Requirement: Agent loads exact Skill instructions on demand
The system SHALL expose an always-available `skill_load` tool that performs exact lookup, validation, availability checking, dependency resolution, and current-turn instruction loading.

#### Scenario: Available Skill is loaded
- **WHEN** `skill_load` receives the exact name of a valid enabled available Skill
- **THEN** the complete validated `SKILL.md` instructions enter the current model working context and the load result identifies name, version, and hash

#### Scenario: Disabled or unavailable Skill is requested
- **WHEN** `skill_load` receives a disabled, invalid, unknown, or unavailable Skill name
- **THEN** it returns a structured error and does not inject instructions or mark the Skill active

### Requirement: Explicit leading Skill mention bypasses search only
The server SHALL recognize one exact installed Skill token at the beginning of user content in the form `@<slug>` and SHALL route it to exact Skill loading without bypassing validation or security.

#### Scenario: Valid explicit Skill is supplied
- **WHEN** a message begins with an exact enabled Skill mention followed by task text
- **THEN** the turn preserves the original user message, loads that Skill, and uses the remaining text as the task without calling discovery first

#### Scenario: Inline at-sign text is supplied
- **WHEN** an at-sign expression appears anywhere other than the recognized leading position
- **THEN** the server treats it as ordinary user content and does not select a Skill

#### Scenario: Unknown explicit Skill is supplied
- **WHEN** a message begins with an unknown Skill slug
- **THEN** the turn returns a clear selection error with bounded suggestions and does not silently execute as though the Skill were loaded

### Requirement: Full Skill instructions are current-turn-only
The system SHALL expose loaded Skill instructions to the model only for the active turn and SHALL persist a compact receipt instead of the full body in both durable and reusable in-memory history.

#### Scenario: Turn completes after loading a Skill
- **WHEN** a loaded Skill contributed full instructions to a turn
- **THEN** subsequent turns and persisted history contain only a receipt with Skill name, version, and hash unless the Skill is loaded again

#### Scenario: Same Skill version is loaded twice in one turn
- **WHEN** `skill_load` is called again for an already loaded name and content hash
- **THEN** it returns an `already_loaded` receipt without injecting the body a second time

### Requirement: Supporting resources remain progressively loaded
The system SHALL NOT inject all Skill supporting files when `SKILL.md` is loaded and SHALL allow only validated package-relative access to resources selected by the active workflow.

#### Scenario: Skill contains references and templates
- **WHEN** the main Skill is loaded but no supporting resource is requested
- **THEN** only the `SKILL.md` instructions consume model context

