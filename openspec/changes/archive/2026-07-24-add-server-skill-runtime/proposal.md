## Why

CashCode can discover and lazily connect MCP tools, but it has no local Skill runtime for reusable workflows, domain instructions, or bundled resources. Adding a server-side Skill system now lets natural-language requests select specialized guidance without placing every installed Skill in the model context, while preserving CashCode's local-first architecture.

## What Changes

- Add a validated local Skill catalog with read-only built-in Skills and mutable user and agent-created Skills.
- Bundle CashCode-adapted `weather`, `chart-visualization`, `github`, and `skill-creator` Skills; dependency availability is reported rather than hidden.
- Add permanent `skill_search` and `skill_load` tools for metadata search followed by exact, on-demand instruction loading.
- Support an optional leading `@skill` mention that selects an installed Skill without requiring frontend changes.
- Keep full Skill instructions in the current agent turn only, while persisting a compact load receipt and bounded session activation summary.
- Resolve declared required and optional built-in/MCP dependencies without eagerly starting unrelated MCP servers.
- Add REST APIs for listing, inspecting, validating, creating, updating, enabling, deleting, versioning, and rolling back local Skills.
- Add a disabled-by-default Skill evolution preview that gathers reusable evidence and produces reviewable proposals; approved proposals are validated, snapshotted, and atomically applied only to agent-created Skills.
- Harden the agent turn runtime so mid-turn tool visibility refreshes, messages for one chat execute serially, and complete tool traces can be projected differently for model context, WebSocket previews, and persisted history.

## Capabilities

### New Capabilities

- `local-skill-catalog`: Skill package shape, source kinds, validation, availability, indexing, versioning, and bundled built-in Skills.
- `skill-discovery-loading`: Natural-language search, optional `@skill` selection, two-stage lazy loading, and current-turn-only full instructions.
- `skill-mcp-dependencies`: Structured Skill dependency declarations and required/optional MCP activation behavior.
- `skill-management-api`: Server APIs for managing, validating, enabling, versioning, and rolling back local Skills.
- `skill-evolution`: Restricted post-turn evidence collection, proposal review, approval, atomic application, and rollback for agent-created Skills.
- `agent-turn-runtime`: Per-chat serialization, dynamic tool schema refresh, complete turn traces, and ephemeral versus durable tool-result projections.

### Modified Capabilities

- `session-metadata`: Persist a bounded recent-Skill activation summary without persisting full Skill instructions.

## Impact

- Adds a new `server/app/skills` subsystem, built-in Skill assets, Skill REST router, and lifecycle-managed catalog/evolution services.
- Changes `SimpleAgentLoop`, `SimpleAgentRunner`, tool result handling, history persistence, WebSocket tool previews, and session metadata.
- Extends MCP deferred activation so Skill-declared dependencies become visible in the same turn after loading.
- Adds YAML parsing and a server test suite dependency.
- Introduces local Skill data, snapshot, and evolution-proposal storage under a configurable CashCode data directory.
