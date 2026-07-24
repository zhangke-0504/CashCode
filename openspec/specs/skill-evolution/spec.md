# Skill Evolution Specification

## Purpose
Define opt-in, evidence-based Skill evolution through restricted proposals and explicit review.

## Requirements

### Requirement: Skill evolution is disabled by default
The server SHALL leave post-turn Skill evolution disabled unless explicitly enabled by configuration and SHALL never auto-apply a proposal in this release.

#### Scenario: Default server processes a successful turn
- **WHEN** no evolution configuration is enabled
- **THEN** no evolution evidence, model call, proposal, or Skill mutation is produced

### Requirement: Evolution collects bounded reusable evidence
When enabled, the system SHALL collect bounded evidence only after a successfully persisted tool-using turn and SHALL exclude full loaded Skill bodies and sensitive tool-result content from evidence.

#### Scenario: Failed or text-only turn completes
- **WHEN** a turn fails, is not persisted, or uses fewer than the configured tool threshold
- **THEN** the evolution worker skips it without advancing a Skill proposal

#### Scenario: Similar reusable workflows recur
- **WHEN** sanitized evidence for a workflow reaches the configured similarity and occurrence threshold
- **THEN** the evidence becomes eligible for proposal generation

### Requirement: Restricted evolver produces proposals only
The evolution mini-agent SHALL have only bounded Skill inspection, the read-only Skill creator contract, and proposal creation capabilities, and SHALL NOT have general filesystem, shell, Web, MCP, or direct Skill mutation tools.

#### Scenario: Evolver identifies reusable knowledge
- **WHEN** eligible evidence is not already covered by an existing Skill
- **THEN** it may create one agent-Skill proposal containing rationale, evidence references, candidate content, validation report, and base hash

#### Scenario: Existing built-in or user Skill covers the workflow
- **WHEN** the evolver finds the workflow in a non-agent Skill
- **THEN** it creates no modification proposal for that Skill and records the deduplication decision

### Requirement: Evolution proposals require explicit review
The server SHALL expose proposal list, detail, approve, and reject operations and SHALL persist proposal status and audit metadata.

#### Scenario: User rejects a proposal
- **WHEN** a pending proposal is rejected
- **THEN** it becomes durably rejected and no Skill package changes

#### Scenario: User approves a valid proposal
- **WHEN** a pending proposal targets a new agent Skill or the unchanged base hash of an existing agent Skill
- **THEN** the server validates the complete candidate, snapshots any target, atomically applies it, refreshes the catalog, and records the applied version

#### Scenario: Approved proposal is stale
- **WHEN** the target content hash differs from the proposal base hash
- **THEN** approval returns a conflict and does not overwrite the newer Skill

### Requirement: Evolution can modify only agent-owned Skills
The server SHALL enforce source ownership at the storage layer so evolution proposals cannot modify, delete, or add supporting files to built-in or user Skills.

#### Scenario: Proposal targets a protected Skill
- **WHEN** approval attempts to apply an update to a built-in or user Skill
- **THEN** the store rejects the operation regardless of model instructions or proposal content
