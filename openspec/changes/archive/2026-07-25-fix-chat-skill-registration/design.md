## Context

The observed chat asked CashCode to create a Skill named `认知扭曲`. The Agent loaded `skill-creator`, wrote `data/skills/user/renzhi-niuqu/SKILL.md` directly, then attempted several ad hoc HTTP commands. None of the API requests succeeded, the package frontmatter used the invalid canonical name `认知扭曲`, the directory and frontmatter identities differed, and no catalog refresh occurred. The Agent nevertheless told the user that creation was complete.

The current architecture made this likely. `skill-creator` says to use the Skill management API, but the Agent registry exposes only generic file/shell tools and read-only Skill discovery/loading tools. `SimpleAgentLoop` owns the live catalog while `server/main.py` constructs the `SkillStore` later for FastAPI, so the Agent cannot call the guarded store directly. Invalid packages are collected in `catalog.invalid`, but the new market does not render that response field.

Spore's foreground authoring flow writes `skills/<slug>/SKILL.md` and lets the filesystem tool add `agentCreated=true`; its loader and local market rescan the filesystem. Spore also has a narrower `AgentSkillManageTool` and guarded Agent Skill store for automatic evolution. CashCode already has the stronger storage primitive, so this design preserves Spore's simple model interaction while adopting the managed-tool implementation instead of its best-effort write hook.

## Goals / Non-Goals

**Goals:**

- Make an explicit chat request create a validated `source=agent` Skill through one structured tool.
- Return success only after atomic publication and live catalog visibility.
- Prevent generic file mutations from bypassing managed user and Agent Skill storage.
- Preserve a safe immutable ASCII slug while allowing localized user-facing names.
- Make legacy invalid packages diagnosable from the Skill market.
- Let users explicitly remove invalid mutable packages without making them selectable or editable.
- Reuse the same `SkillStore` for API, Agent authoring, discovery, and evolution.

**Non-Goals:**

- Automatically infer and persist a Skill from ordinary conversation without an explicit authoring request.
- Automatically adopt, rewrite, move, or delete pre-existing invalid packages.
- Permit Chinese or arbitrary Unicode in the canonical directory/API identity.
- Add binary support-file generation to the chat authoring tool; ZIP import remains the binary package path.
- Implement remote publication, sharing, or market upload for Agent-created Skills.
- Parse arbitrary shell commands to detect every possible indirect write into managed roots.

## Decisions

### Add an always-available managed Agent Skill authoring tool

Register an `agent_skill_manage` tool in the normal Agent registry after the shared store is initialized. Its first supported action is `create`, accepting a canonical `name`, complete `content`, optional text `support_files`, and a bounded audit `reason`. The tool forces `source=agent` and `enabled=true`; ownership and runtime metadata are never model-controlled.

The result is structured JSON. `success=true` is emitted only after `SkillStore.create` returns and the catalog contains the same name, hash, and Agent source. Domain errors are mapped to stable validation/conflict/permission codes without host paths. The built-in `skill-creator` requires this tool, describes lowercase slug construction, and explicitly forbids direct filesystem or ad hoc HTTP creation.

Alternative considered: copy Spore's `_ensure_agent_skill_marker` hook onto `write_file`. That publishes unvalidated partial trees, provides no rollback, and still requires an explicit refresh in CashCode's cached catalog, so it is weaker than the existing store.

### Give the Agent Loop and FastAPI one store instance

Construct `SkillStore` alongside `SkillCatalog` inside `SimpleAgentLoop`, expose read-only `skill_store` and `skill_catalog` properties, and have FastAPI and `EvolutionService` reuse those exact instances. Tool registration occurs only after both are initialized. This makes the existing main-spec requirement true and avoids callbacks that attach storage after the tool registry is already live.

Alternative considered: let `main.py` create the store and later inject it into the Agent. Late registration creates a partially initialized window and forces extra catalog refreshes to make tool dependencies available.

### Protect managed roots in generic filesystem tools

Pass the resolved user and Agent Skill roots into `WriteFileTool` and `EditFileTool` as protected roots. After normal workspace path resolution and before any directory or file mutation, reject a target at or below either root with an actionable instruction to call `agent_skill_manage`. Reads remain available under existing workspace rules.

The `skill-creator` prompt also prohibits `exec`, `curl`, and direct package writes. Reliably parsing arbitrary shell programs is outside this change; the authoritative protection remains that only store-created packages can produce authoring-tool success.

Alternative considered: move the entire Agent workspace away from the server tree. That is a valuable broader isolation change but would affect every file and shell workflow, not only Skill authoring.

### Keep canonical name and display name separate

Extend `SkillManifest` with `display_name`. `name` remains the lowercase 1-64 character slug used for directories, API routes, mentions, conflicts, snapshots, and exact loading. `display_name` is optional, trimmed, limited to 80 characters, rejects control characters/newlines, and defaults to `name`.

Catalog DTOs return both fields and index both for search. The Skill market and composer show `display_name` as the primary label and retain the canonical name for selection receipts and secondary identity where needed. Editing may change `display_name` but not `name`.

This adapts Spore's separate slug/display fields without weakening CashCode's package identity validation. Automatic transliteration is intentionally avoided because it is dependency-heavy and ambiguous; the Agent supplies a safe slug and can preserve the requested localized title as `display_name`.

### Reject duplicates across physical ownership roots

Move the importer's all-root directory conflict check into a shared store helper and use it for both API and Agent creation. The check includes invalid and currently shadowed directories, preventing a newly created Agent Skill from hiding a built-in or user package and ensuring a successful tool result is actually effective.

### Expose invalid diagnostics with explicit guarded deletion

Keep invalid packages out of normal `items`, exact loading, and composer selection. Sanitize and bound `catalog.invalid` records by source, directory identity, error count, and message length before returning them. The Skill market renders a diagnostic section or rows with an invalid status, no edit/enable actions, and a delete action only for mutable ownership sources.

The repair lifecycle in this change supports only explicit deletion for invalid user and Agent packages. The API identifies the diagnostic by source and direct child directory, rechecks under the store lock that the package is still invalid, moves it out of the active root into an invalid-package snapshot, refreshes the shared catalog, and rolls the move back if refresh fails. Invalid built-ins remain immutable. Diagnostic rows never gain selection, edit, or enable actions.

This follows Spore's visible `localKind=invalid` behavior while preserving CashCode's stricter validation and ownership APIs.

### Keep the creator contract identical to loader validation

The built-in `skill-creator` includes the exact canonical-name pattern, supported frontmatter fields, localized `display_name` rule, and a complete valid template. It requires `agent_skill_manage` and treats validation failure as a correction loop rather than falling back to filesystem, shell, or HTTP creation. The managed tool remains the authority: it parses the complete content with the same `parse_skill_text` function used by the catalog before any directory is created, and the store verifies the published name, source, and content hash before returning.

## Risks / Trade-offs

- [The model still attempts shell-based creation] -> Update `skill-creator`, expose the managed tool directly, reject generic file-tool writes, and require `success=true` before a completion claim.
- [Localized labels are confused with canonical identity] -> Return both fields consistently and use only canonical `name` in routes, receipts, hashes, conflicts, and package paths.
- [A user already has an invalid directory for the desired slug] -> Report a bounded conflict/invalid diagnostic and require explicit repair or removal; never overwrite it automatically.
- [An invalid directory is repaired between display and deletion] -> Revalidate under the store lock and refuse the invalid-delete operation once the package is valid.
- [Invalid exceptions leak host paths] -> Sanitize diagnostics at the catalog/API boundary and test absolute-path removal and length bounds.
- [Moving store construction changes startup order] -> Keep catalog construction order stable, initialize the store before tool exposure, and cover application lifespan startup with API and Agent integration tests.
- [Always exposing one more tool adds prompt cost] -> Keep the schema narrow and creation-focused; defer broader Agent patch/resource actions until a demonstrated chat workflow requires them.
- [Generic shell remains capable of direct writes] -> Treat shell isolation as separate defense-in-depth work; direct writes never produce managed success and remain invalid or stale rather than authoritative.

## Migration Plan

1. Add `display_name` parsing and DTO compatibility with fallback to canonical name.
2. Centralize cross-root conflict checks and move shared store ownership into `SimpleAgentLoop` without changing API routes.
3. Add and register `agent_skill_manage`, then update `skill-creator` and filesystem protected-root guards.
4. Render sanitized invalid diagnostics and localized labels in the market/composer, with guarded deletion for mutable invalid packages.
5. Run a regression based on the recorded `认知扭曲` transcript and verify immediate API, market, search, and composer visibility.

Existing valid packages require no migration because omitted `display_name` falls back to `name`. Existing invalid packages, including `data/skills/user/renzhi-niuqu`, remain untouched until the user explicitly deletes or manually repairs them; deleting from the market moves them into the snapshot area before freeing the slug. Rollback removes the authoring tool and guards while retaining any valid Agent packages already created, which remain readable by the existing catalog.

## Open Questions

None. Agent-side patching and supporting-file mutation can be added later without changing the create contract.
