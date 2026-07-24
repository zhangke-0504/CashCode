## Context

CashCode currently routes WebSocket messages through `SimpleAgentLoop` and a non-streaming ReAct `SimpleAgentRunner`. Built-in tools are always registered, MCP tools are discovered from cached metadata and connected lazily, and an `ActivatedToolSet` stored in session metadata controls deferred MCP visibility. This provides most of the primitives needed for Skill discovery, but there is no Skill package model, catalog, loader, context-lifetime policy, management API, or evolution boundary.

Three current runtime details must change for a correct Skill implementation:

- `SimpleAgentRunner` snapshots tool schemas once before the ReAct loop, so a dependency activated during an iteration is not visible in the next iteration.
- `SimpleAgentLoop` launches each inbound message as an independent task, so turns for one chat can race while mutating history and metadata.
- Tool results are plain strings copied into working messages, in-memory history, persistent history, and WebSocket previews, so a loaded `SKILL.md` cannot remain current-turn-only.

The first release is local-first and single-user. It must remain useful with thousands of installed Skills without placing all descriptions or bodies in the prompt. Built-in Skills ship with the server; user and agent-created Skills live under a configurable data directory.

## Goals / Non-Goals

**Goals:**

- Discover an unbounded local catalog through bounded metadata search.
- Load full Skill guidance only after an exact Skill is selected.
- Support both model-selected Skills and explicit leading `@skill` selection.
- Make declared built-in and MCP dependencies usable in the same turn.
- Keep Skill bodies ephemeral while retaining compact session continuity.
- Provide validated management, version, snapshot, and rollback operations.
- Provide a restricted, disabled-by-default evolution preview that creates reviewable proposals.
- Preserve complete, correctly ordered turn traces while exposing separate model, public, and durable tool-result projections.

**Non-Goals:**

- A remote Skill market, online installation, account-level synchronization, or multi-tenant authorization.
- Automatic execution of scripts merely because a Skill is loaded.
- Automatic modification of built-in or user-authored Skills.
- Default automatic application of evolution proposals.
- Frontend Skill management UI or rich `@skill` autocomplete in this server-focused change.
- Keeping every installed Skill description or full Skill body in the model prompt.

## Decisions

### 1. Use a three-source catalog with a single effective namespace

The catalog reads, in increasing precedence, read-only built-ins, mutable user Skills, and mutable agent-created Skills. Each package is a directory containing `SKILL.md` and optional `references/`, `templates/`, `scripts/`, and `assets/`. Runtime metadata such as source kind, enabled state, content hash, version, availability, and agent-created ownership is stored in `_meta.json` and is never accepted from untrusted frontmatter as authority.

The catalog rejects duplicate effective names within a source and resolves cross-source names by explicit precedence. API responses expose both the effective record and its source so shadowing is observable. Built-in packages remain immutable through management APIs.

Alternative considered: copy built-ins into the user directory. Rejected because copies drift from packaged versions and blur the read-only trust boundary.

### 2. Index metadata only and expose two permanent Skill tools

`skill_search(query, limit)` searches normalized `name`, `description`, `tags`, and optional trigger phrases using the existing BM25 tokenization approach. It returns bounded metadata and availability, never `SKILL.md` bodies.

`skill_load(name)` performs exact lookup, enabled and availability checks, validation, dependency handling, hash verification, and full instruction loading. It records the Skill in the turn-local loaded set and the session activation LRU.

This is the two-stage lazy-loading contract: search selects metadata and load supplies instructions. Supporting resources are a third progressive-disclosure level and remain unread until a Skill explicitly directs the agent to read or execute them.

Alternative considered: inject every enabled Skill description into the system prompt, as in the small-catalog Spore path. Rejected because prompt cost scales linearly with installed count.

### 3. Treat `@skill` as an exact-load hint, not a permission bypass

Until the frontend sends structured selection metadata, the server recognizes one leading `@<slug>` token only when the slug exactly matches a catalog entry. The original user text remains the durable conversation record; the parsed task text and requested Skill are turn inputs. Unknown, disabled, invalid, or unavailable Skills return a clear selection error with bounded suggestions.

The explicit hint bypasses search but not validation, enabled state, dependency checks, or tool security. Inline mentions and email-like text do not trigger selection.

### 4. Add a turn-local Skill context and projected tool results

A `TurnSkillContext`, bound with `ContextVar`, tracks loaded `(name, hash)` pairs. Loading the same hash twice in one turn returns a compact `already_loaded` result instead of duplicating instructions.

Tool execution returns a structured result with at least:

- `model_content`: content appended to current Runner working messages.
- `public_content`: bounded content emitted in WebSocket tool-result events.
- `persisted_content`: durable history representation.
- `ephemeral`: whether model content must be excluded from in-memory and persistent history after the turn.

For `skill_load`, `model_content` is the validated Skill body and `persisted_content` is a receipt containing name, version, and hash. The Runner uses model content during the current turn; the Loop persists the durable projection and rebuilds in-memory history from that same projection.

Alternative considered: remove Skill tool messages from history after the turn. Rejected because it would leave incomplete tool-call chains; compact receipts preserve protocol ordering without retaining the body.

### 5. Refresh visible schemas on every ReAct iteration

The Runner asks the registry for definitions immediately before every model request. Registry revision caching remains responsible for avoiding unnecessary schema reconstruction. A tool activated by `skill_load`, `tool_search`, or `mcp_prepare` in iteration N is therefore visible in iteration N+1 of the same turn.

The Runner returns a complete ordered `TurnTrace`, including every assistant tool-call message, tool result, final content, tools used, and success/error metadata. The Loop no longer infers a trace by retaining only the last tool-call message.

### 6. Serialize turns per chat without globally blocking users

`SimpleAgentLoop` maintains a lock per `chat_id`. `_handle_turn` acquires it before loading or mutating chat history and releases it after persistence and session metadata updates. Different chats continue concurrently. Lock entries are cleaned up when sessions are deleted or no task references them.

### 7. Model dependencies explicitly and preserve MCP laziness

Skill frontmatter supports `requires.tools`, `requires.mcp_servers`, `optional.tools`, `optional.mcp_servers`, `bins`, and `env`. Catalog availability reports missing static dependencies without executing them.

On `skill_load`:

- Required built-in tools must exist or loading fails.
- Required MCP servers are prepared through the existing lazy-connect callback; declared tools are activated after registration.
- Optional MCP servers are reported but not connected.
- A failed required MCP connection fails the load with a structured dependency error.
- Loading never executes a Skill script and never starts undeclared servers.

Structured declarations are authoritative. A compatibility scan for textual `mcp_*` names may emit diagnostics but cannot grant activation authority.

### 8. Persist only a bounded activation summary

Session metadata gains `activated_skills`, an LRU map of at most the configured limit, containing only name, short description, version, content hash, and last-used timestamp. At turn construction, the system prompt includes a bounded summary of recent entries and tells the model to call `skill_load` whenever full guidance is needed.

If a catalog record no longer exists, is disabled, or its hash changes, the summary is marked stale or omitted; it never substitutes for validation at load time.

### 9. Centralize all writes in a lifecycle-managed Skill service

The FastAPI lifespan creates one `SkillCatalog`/`SkillStore` service and places it on `app.state`; the Agent Loop and Skill API share that instance. Writes use temporary files followed by atomic replacement, update metadata and snapshots, and increment a catalog revision that invalidates the search index.

The API provides list, detail, create, replace, enable/disable, delete, validate, versions, and rollback operations. Built-ins cannot be changed. Names and support paths are normalized and checked after resolution; absolute paths, `..`, symlink escapes, oversized files, invalid UTF-8, malformed YAML, and unsupported package entries are rejected.

### 10. Ship a small adapted built-in set

The initial built-ins are:

- `weather`, rewritten to prefer CashCode `web_fetch`/`web_search` tools.
- `chart-visualization`, with a concise `SKILL.md` and lazily read references/template.
- `github`, whose catalog availability reports a missing `gh` binary rather than hiding the Skill.
- `skill-creator`, adapted to CashCode package metadata, validation, and management APIs and used as a read-only evolution contract.

The memory save trigger remains in the fixed system prompt because correctness must not depend on discovering a lazy Skill.

### 11. Implement evolution as evidence and proposals, not direct writes

After a successfully persisted, tool-using turn, an independent background worker may collect a bounded, redacted evidence excerpt. Evolution is disabled by default. When enabled, similar evidence must reach a configured threshold before a restricted mini-agent runs.

The mini-agent can inspect bounded Skill summaries, read the `skill-creator` contract, and create one proposal. It cannot use general filesystem, shell, Web, or MCP tools and cannot mutate packages. A proposal contains target kind/name, base hash, create-or-patch operation, proposed content or exact diff, reason, evidence references, validation report, and status.

Approval rechecks the base hash and permissions, snapshots the target, validates the candidate package, applies it atomically, and records an audit entry. Only `agent` Skills may be updated; a proposal may create a new `agent` Skill when no existing Skill covers the workflow. Rejection is durable. Auto-apply is outside this release.

Alternative considered: port Spore's post-turn evolver that directly invokes `agent_skill_manage`. Rejected for v1 because CashCode lacks user feedback signals and operational history needed to trust automatic writes.

### 12. Keep data roots configurable and independent of the process working directory

`CASHCODE_DATA_DIR` resolves the durable root. User/agent Skills, snapshots, proposals, and evidence use explicit child directories. Built-ins resolve from the installed Python package. Existing `memory/` storage is not migrated by this change, but all new Skill paths avoid implicit current-working-directory behavior.

## Risks / Trade-offs

- [A loaded Skill can contain prompt injection] -> Treat it as untrusted lower-priority instructions, validate structure and size, preserve system/tool security, and never auto-execute scripts.
- [Large Skill bodies can still consume one turn's context] -> Enforce body limits, reject oversized packages, encourage concise main files, and load supporting resources separately.
- [BM25 may miss indirect natural-language intent] -> Index trigger phrases and multilingual tokens, return bounded results, and retain explicit `@skill` selection; semantic embeddings remain a future option.
- [Required MCP startup increases load latency] -> Only prepare declared required servers, leave optional dependencies lazy, and reuse existing connection handles/cache.
- [Concurrent API writes can race with loading] -> Use catalog/store write locking, atomic replacement, immutable content snapshots, and hash-based load/proposal checks.
- [Evolution can learn a one-off or erroneous workflow] -> Require repeated evidence, default the feature off, generate proposals only, expose diffs, and require approval.
- [Existing malformed history tool chains may remain] -> Apply the new projection and complete-trace rules prospectively; no historical rewrite is required.
- [The bundled GitHub Skill is unavailable on some machines] -> Report dependency state explicitly and refuse loading until `gh` is available.

## Migration Plan

1. Add the structured result and complete `TurnTrace` abstractions while preserving plain-string tool compatibility.
2. Add per-chat serialization and per-iteration schema refresh; verify existing MCP deferred activation still works.
3. Introduce the catalog, validator, data roots, built-ins, search, load, and turn-local context behind a feature flag.
4. Add session summaries and durable Skill receipts, then enable the Skill runtime by default.
5. Add management/version APIs and share the catalog through FastAPI lifespan state.
6. Add evolution evidence/proposal storage and APIs with evolution disabled by default.

Rollback disables the Skill runtime and evolution flags; existing Skill data and receipts remain inert. Atomic snapshots allow individual agent/user Skill rollback without reverting server code.

## Open Questions

- The initial default limits for Skill body size, supporting-file size, search result count, and activation-summary budget should be finalized during implementation from model context and expected local data sizes.
- The project currently lacks user feedback events; evolution evidence initially relies on technical completion signals rather than explicit user satisfaction.
- Frontend structured `@skill` metadata and Skill management UI are intentionally deferred, but the server request/response shapes should remain forward-compatible with them.
