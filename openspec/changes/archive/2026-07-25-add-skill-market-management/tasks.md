## 1. Skill Package Import Foundation

- [x] 1.1 Add the multipart upload dependency and centralize ZIP upload, entry-count, per-file, and expanded-size limits alongside the existing Skill package limits.
- [x] 1.2 Implement archive inspection and safe member extraction that accepts flat or single-wrapper ZIP layouts and rejects invalid formats, traversal, drive paths, duplicate paths, encryption, symlinks, special files, and limit violations.
- [x] 1.3 Implement a `SkillStore` import operation that derives the canonical frontmatter name, checks every ownership root for duplicates, rewrites runtime metadata as enabled `user`, validates the complete tree, publishes atomically, cleans up failures, and refreshes the catalog.
- [x] 1.4 Add focused importer/store tests for flat and wrapped packages, binary asset preservation, untrusted metadata replacement, built-in/user/agent conflicts, malicious paths and member types, size bounds, rollback cleanup, and live catalog visibility.

## 2. Skill Management API

- [x] 2.1 Add `GET /api/skills/{name}/content` returning complete bounded `SKILL.md`, current hash, source, and mutability without host paths or supporting-file contents.
- [x] 2.2 Add `POST /api/skills/import` as a one-file multipart endpoint with consistent `422`, `409`, and permission/error mapping to the Skill domain errors.
- [x] 2.3 Verify replacement requests for both `user` and `agent` Skills require matching identity/hash, preserve omitted support files byte-for-byte, retain ownership, snapshot the old package, and keep built-in mutations forbidden.
- [x] 2.4 Add API tests covering content reads, valid upload, malformed archives, duplicate conflicts, built-in protection, stale edits, validation failures, user/agent edits, deletion, enable/disable, and no-restart catalog refresh.

## 3. Frontend Data And Navigation

- [x] 3.1 Extend frontend Skill DTOs with list pagination, content-detail, upload, update, enabled-state, and deletion contracts while keeping composer-selectable filtering unchanged.
- [x] 3.2 Update the shared API request helper to support `FormData` without forcing a JSON content type, and add wrappers for paginated Skill listing/search, full content reads, import, replace, enable/disable, and delete.
- [x] 3.3 Extend `AppView`, `AppLayout`, and `Sidebar` with a `skill-market` route and `Skill 市场` navigation row that preserves active chat/history state and returns to chat on session selection or new conversation.
- [x] 3.4 Add focused frontend tests for Skill query construction, multipart request behavior, view selection, and sidebar navigation state.

## 4. Skill Market Experience

- [x] 4.1 Build the paginated Skill market list with debounced search, refresh, stable loading/error/empty states, result counts, and dense rows showing identity, description, version, source, enabled/availability status, and bounded missing dependencies.
- [x] 4.2 Render `内置`, uploaded-user, and agent-created source labels and gate edit, enable/disable, and delete commands from `mutable`, while keeping built-in inspection read-only.
- [x] 4.3 Build the full `SKILL.md` editor with immutable name, monospaced draft, Save/Cancel, server validation messages, working state, expected-hash submission, conflict handling that preserves the draft, and authoritative refresh after success.
- [x] 4.4 Build the ZIP upload dialog with file-type validation, selected-file feedback, stable submit state, bounded server errors, and list refresh after successful import.
- [x] 4.5 Implement mutable enable/disable controls and a deletion confirmation flow that retain authoritative rows on failure and refresh the composer-visible catalog after success.
- [x] 4.6 Add UI/helper tests for ownership action gating, source/status labels, paging/search state, editor conflict behavior, upload validation, lifecycle failures, and delete cancellation.

## 5. Repository Data Boundaries And Documentation

- [x] 5.1 Replace the permissive `mcp_servers/` tracking behavior with an ignore-all allowlist for `mcp_config.json`, `test_stdio_mcp/**`, and `test_sse_mcp/**`, while retaining `/server/data/` exclusion and built-in Skill tracking.
- [x] 5.2 Verify representative paths with `git check-ignore`: user-created MCP directories and default user/agent Skill roots are ignored, while the MCP catalog, both test MCP implementations, and `server/app/skills/builtin/**` remain trackable.
- [x] 5.3 Update README architecture, API, frontend, Skill package, upload-security, editing-scope, source-label, and Git ownership documentation.

## 6. End-To-End Verification

- [x] 6.1 Run the focused server Skill/import/API test suite and resolve failures without weakening archive or ownership checks.
- [x] 6.2 Run client unit tests, lint, TypeScript compilation, and production build.
- [ ] 6.3 Start the backend and frontend, then verify desktop and mobile Skill market screenshots for loading, populated, missing-dependency, upload, edit, conflict/error, disabled, and delete-confirmation states with no overlap or layout shift.
- [ ] 6.4 Exercise an end-to-end flow that uploads a Skill with a binary asset, edits only `SKILL.md`, confirms the asset hash is unchanged, confirms the Skill is immediately selectable by chat, and confirms built-in edit/delete remain unavailable and server-forbidden.
