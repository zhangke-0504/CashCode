## 1. Test and Runtime Foundations

- [x] 1.1 Add PyYAML and server test dependencies, configure pytest, and add fixtures for isolated workspace, data, memory, and Skill roots.
- [x] 1.2 Introduce a configurable absolute `CASHCODE_DATA_DIR` path service and lifecycle ownership through FastAPI `app.state`.
- [x] 1.3 Add a structured `ToolExecutionResult` with model, public, and durable projections while preserving compatibility for existing string-returning tools.
- [x] 1.4 Add an ordered `TurnTrace` model and update `SimpleAgentRunner` to return all tool-call iterations, results, final content, tools used, and completion status.
- [x] 1.5 Refresh registry definitions before every ReAct model request and test same-turn visibility after tool registration or activation.
- [x] 1.6 Add per-chat turn locks to `SimpleAgentLoop`, retain concurrency across different chats, and clean up unused locks safely.
- [x] 1.7 Refactor in-memory and persistent history projection to retain complete valid tool chains while excluding ephemeral model-only content.
- [x] 1.8 Add regression tests for existing tools, MCP activation, multi-iteration persistence, WebSocket previews, turn failure rollback, and concurrent messages.

## 2. Skill Package Model and Validation

- [x] 2.1 Create `server/app/skills` models for manifests, dependencies, source kinds, availability, validation errors, versions, and effective catalog records.
- [x] 2.2 Implement safe YAML frontmatter parsing with scalar type checks, body and supporting-file size limits, normalized slug validation, and content hashing.
- [x] 2.3 Implement root-contained path resolution that rejects absolute paths, traversal, unsupported entries, and symlink escape for all package reads and writes.
- [x] 2.4 Implement static dependency probes for binaries, environment variables, built-in tools, and configured MCP servers without executing scripts or starting services.
- [x] 2.5 Add unit tests covering malformed packages, non-string metadata, duplicate names, encoding errors, size limits, traversal, symlinks, and dependency availability.

## 3. Catalog, Store, and Index

- [x] 3.1 Implement catalog discovery for packaged built-ins and configurable user/agent roots with explicit precedence and observable shadowing.
- [x] 3.2 Implement enabled/disabled state, immutable built-in enforcement, catalog membership revision, and resilient isolation of invalid packages.
- [x] 3.3 Implement metadata-only BM25 indexing over name, description, tags, and trigger phrases with bounded ranked results and multilingual tokenization reuse.
- [x] 3.4 Implement a locked Skill store for atomic create, replace, delete, enable/disable, and validation operations on mutable source kinds.
- [x] 3.5 Implement package snapshots, version metadata, retention, atomic rollback, and revision/index invalidation after committed writes.
- [x] 3.6 Register one shared catalog/store instance with FastAPI lifespan and inject it into the Agent Loop and API router.
- [x] 3.7 Add catalog/store tests for source precedence, shadowing, concurrent read/write behavior, atomic failure, hot refresh, versions, and rollback.

## 4. Adapted Built-in Skills

- [x] 4.1 Port and adapt the `weather` Skill to CashCode `web_fetch`/`web_search` conventions and validate its package.
- [x] 4.2 Port and split `chart-visualization` into a concise main guide plus lazily read references and template resources.
- [x] 4.3 Port the `github` Skill with a `gh` binary requirement and verify it remains discoverable but unavailable when the binary is missing.
- [x] 4.4 Adapt the `skill-creator` contract and validator to CashCode package fields, ownership kinds, management APIs, and progressive-loading limits.
- [x] 4.5 Add smoke tests that load every built-in and verify names, tool references, dependency states, hashes, and read-only behavior.

## 5. Skill Discovery and Lazy Loading

- [x] 5.1 Implement a task-local `TurnSkillContext` that records loaded name/hash pairs and suppresses duplicate full loads in one turn.
- [x] 5.2 Implement the always-visible `skill_search` tool with bounded metadata results, availability, no body exposure, and no activation side effects.
- [x] 5.3 Implement the always-visible `skill_load` tool with exact lookup, enabled/availability checks, revalidation, dependency handling, and structured ephemeral results.
- [x] 5.4 Add leading `@skill` parsing for one exact catalog slug while preserving original durable user content and rejecting unknown selections with bounded suggestions.
- [x] 5.5 Register Skill tools and bind turn-local Skill state in `SimpleAgentLoop` without injecting all installed Skill descriptions into the system prompt.
- [x] 5.6 Add tests for natural-language search, no-match behavior, exact load, explicit selection, inline at-sign text, disabled/invalid Skills, duplicate loads, and supporting-resource non-loading.

## 6. Session Activation and MCP Dependencies

- [x] 6.1 Implement a bounded LRU `ActivatedSkillSet` stored in session metadata with name, short description, version, hash, and last-used timestamp only.
- [x] 6.2 Add bounded recent-Skill system-prompt hints with stale, disabled, missing, and changed-hash filtering and explicit reload instructions.
- [x] 6.3 Extend Skill loading to validate required built-in tools and prepare declared required MCP servers through the existing lazy-connect callback.
- [x] 6.4 Activate declared required MCP tools after registration so they appear in the next iteration of the same turn.
- [x] 6.5 Report optional MCP dependencies without connecting them and keep textual `mcp_*` scanning diagnostic-only.
- [x] 6.6 Add tests for required MCP success/failure, optional deferral, undeclared textual names, same-turn visibility, summary LRU eviction, and absence of full bodies in metadata/history.

## 7. Skill Management API

- [x] 7.1 Add response/request models and `GET /api/skills` filtering and pagination without returning all Skill bodies.
- [x] 7.2 Add `GET /api/skills/{name}` and `POST /api/skills/{name}/validate` with metadata, permissions, dependency availability, and bounded inspection details.
- [x] 7.3 Add create, replace, enable/disable, and delete endpoints with ownership enforcement, precondition hashes, validation, and atomic store calls.
- [x] 7.4 Add version-list and rollback endpoints that snapshot the current package and refresh the live catalog after restoration.
- [x] 7.5 Add API tests for success, not found, conflict, invalid input, immutable built-ins, stale writes, immediate agent visibility, versions, and rollback.

## 8. Controlled Skill Evolution Preview

- [x] 8.1 Define disabled-by-default evolution configuration, independent cursor/state storage, bounded concurrency, and lifecycle-managed background scheduling.
- [x] 8.2 Collect sanitized bounded evidence only from successfully persisted tool-using turns, excluding full Skill loads and sensitive tool outputs.
- [x] 8.3 Implement deterministic evidence fingerprints, recurrence thresholds, deduplication, retention, and skip reasons before any evolver model call.
- [x] 8.4 Implement a restricted evolution runner with only bounded Skill inspection, read-only `skill-creator` contract access, and proposal creation tools.
- [x] 8.5 Implement proposal models and storage for create/patch intent, candidate content or exact diff, evidence references, base hash, validation report, status, and audit timestamps.
- [x] 8.6 Add proposal list/detail/reject APIs and an approve API that rechecks ownership/base hash, validates, snapshots, atomically applies, and refreshes the catalog.
- [x] 8.7 Enforce at the Skill store layer that evolution can create agent Skills and modify only existing agent Skills, never built-in or user Skills.
- [x] 8.8 Add evolution tests for disabled mode, failed/text-only turns, redaction, recurrence gates, restricted tools, deduplication, rejection, stale approval, protected ownership, successful apply, and rollback.

## 9. End-to-End Verification and Operations

- [x] 9.1 Add an end-to-end WebSocket test for natural-language `skill_search` -> `skill_load` -> required MCP/tool execution -> final content with durable receipts only.
- [x] 9.2 Add an end-to-end explicit `@skill` test covering exact load, session summary reuse hint, reload on the next turn, and no accumulated full-body context.
- [x] 9.3 Add stress tests with a large synthetic catalog to verify bounded search results, bounded prompt summaries, no eager body reads, and stable registry behavior.
- [x] 9.4 Document Skill roots, manifest schema, dependency semantics, API routes, limits, feature flags, evolution proposal workflow, and rollback operations.
- [x] 9.5 Run the complete server test suite and OpenSpec validation, resolving all failures before enabling the Skill runtime by default while keeping evolution disabled.
