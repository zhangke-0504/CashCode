## ADDED Requirements

### Requirement: Session metadata stores a bounded Skill activation summary
Session metadata SHALL store a bounded LRU `activated_skills` map whose entries contain only Skill name, short description, version, content hash, and last-used timestamp.

#### Scenario: Skill is successfully loaded
- **WHEN** a valid Skill contributes instructions to a completed turn
- **THEN** its summary is inserted or refreshed in `activated_skills` and session metadata is persisted

#### Scenario: Activation limit is exceeded
- **WHEN** adding a Skill would exceed the configured session activation limit
- **THEN** the least recently used summary is evicted without deleting the installed Skill

#### Scenario: Full Skill body is inspected
- **WHEN** session metadata is written after a Skill load
- **THEN** it contains no full `SKILL.md` body or supporting-resource content

### Requirement: Recent Skill summaries are bounded prompt hints
The Agent Loop SHALL include a bounded recent-Skill summary in turn system context and SHALL require exact reloading before the model relies on full Skill instructions.

#### Scenario: New turn follows prior Skill use
- **WHEN** the session has valid recent activated Skill entries
- **THEN** the system prompt identifies them within the configured count and character budget and directs the model to call `skill_load` for complete guidance

#### Scenario: Activated summary is stale
- **WHEN** the installed Skill is missing, disabled, invalid, or has a different hash
- **THEN** the prompt omits or marks the summary stale and never treats it as loaded instructions

