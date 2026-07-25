## Context

CashCode already merges three local Skill roots into one live catalog: read-only built-ins, mutable user packages, and mutable agent-created packages. The FastAPI application and Agent Loop share the same `SkillCatalog`/`SkillStore`, and the store already validates `SKILL.md`, snapshots mutable packages, uses hash preconditions, and refreshes the catalog after managed writes. The client currently exposes chat and the MCP market only. Skill listing is used only by the composer selector, which filters out disabled and unavailable entries.

Spore provides useful interaction references for a Skill navigation entry, installed-Skill list, upload modal, source-aware actions, and detail views. Its cloud discovery, sharing, publishing, and remote version model do not apply to CashCode's local-first, single-user runtime.

ZIP import is a new untrusted-input boundary. Supporting package files may be binary, so it cannot be implemented through the existing JSON `support_files: dict[str, str]` contract without corrupting assets. The default user and agent roots are under `server/data/`, while built-in packages live under `server/app/skills/builtin/`.

## Goals / Non-Goals

**Goals:**

- Provide a first-class local Skill market alongside chat and the MCP market.
- Show effective built-in, uploaded, and agent-created Skills, including disabled or dependency-blocked entries.
- Protect built-in ownership at both the UI and API/store layers.
- Import one ZIP package safely and atomically into the user Skill root.
- Let users edit the complete `SKILL.md` of user and agent packages with optimistic concurrency and snapshots.
- Keep binary and text supporting files unchanged when only `SKILL.md` is edited.
- Keep runtime user MCP and Skill data out of Git while retaining the built-in test assets.

**Non-Goals:**

- A remote Skill marketplace, publishing, sharing, ratings, or remote version synchronization.
- Editing built-in Skills.
- Renaming an installed Skill or changing its ownership source.
- Browser editing of `references/`, `templates/`, `scripts/`, or `assets/`; package-wide changes can be made outside the first-version editor.
- ZIP-based replacement of an existing Skill, TAR/GZIP import, or bulk archive import.
- A new chat authoring engine; this change consumes valid `agent` Skills created through the existing managed authoring path.
- Version rollback UI, even though the existing API remains available.

## Decisions

### Use a dedicated `skill-market` application view

Extend `AppView` with `skill-market`, add a sidebar navigation row near `MCP 市场`, and render a dedicated `SkillMarket` main view. The market uses the existing paginated `GET /api/skills` contract without the composer selector's `enabled=true&availability=available` filters. This keeps disabled and dependency-blocked packages manageable.

The view presents a dense list with search, paging, refresh, upload, stable loading/error/empty states, and source/status badges. `builtin` is labeled `内置`; `user` and `agent` receive distinct user-facing source labels. Mutable rows expose edit, enable/disable, and delete commands. Built-in rows expose inspection only. A selected session remains attached while either market is open, and choosing a conversation returns to chat.

Alternative considered: reuse the composer Skill picker. It omits unavailable entries and has selection-oriented interaction, so it cannot represent management state or protected actions cleanly.

### Add a browser-oriented multipart ZIP endpoint

Add `POST /api/skills/import` accepting one multipart file and add `python-multipart` to server dependencies. The endpoint accepts `.zip` only, forces `source=user`, and never accepts ownership or enabled metadata from the archive. Multipart keeps the frontend implementation native with `FormData` and avoids base64 expansion.

Alternative considered: send base64 or raw bytes in JSON. That increases memory and payload size and does not fit existing browser file upload conventions.

### Treat archive extraction as a bounded validation pipeline

The importer reads the upload under configured compressed-size, entry-count, per-file, and total-uncompressed-size limits. It rejects encrypted entries, absolute or parent-traversal paths, Windows drive paths, duplicate normalized paths, symlinks, and other special file types. It writes members itself rather than calling unrestricted `extractall`.

The archive may contain `SKILL.md` at its root or inside exactly one top-level directory. The canonical install name comes from validated frontmatter; an outer wrapper directory is not authoritative. Package contents must still satisfy the existing allowed-root-entry and file-size rules. Archive `_meta.json` ownership fields are discarded and replaced with server-owned metadata for an enabled `user` Skill.

Extraction occurs in a hidden temporary directory under the user Skill root so the final rename stays on one filesystem. The complete tree is validated before `os.replace` publishes it. Failures remove the temporary tree and leave the catalog and existing packages unchanged.

### Reject duplicate names across every ownership root

Import returns `409` when the canonical name exists in built-in, user, or agent storage, including a currently shadowed directory. This prevents an upload from hiding a built-in or from succeeding without appearing because an agent package has higher precedence. Existing catalog precedence remains for backward compatibility with pre-existing data; explicit editing remains the only supported replacement path.

Alternative considered: use the current `builtin < user < agent` precedence for uploads. That produces surprising UI behavior and weakens the meaning of the `内置` protection.

### Edit complete `SKILL.md` with an immutable identity

Add `GET /api/skills/{name}/content`, returning the complete UTF-8 `SKILL.md`, current content hash, source, and mutability without returning supporting file bodies or filesystem paths. The maximum existing `SKILL.md` size keeps the response bounded. The market editor uses a monospaced text area and submits the existing replace payload with `expected_hash` while omitting `support_files`.

Omitting `support_files` intentionally exercises the store's copy-and-replace path: the existing package tree is copied, only `SKILL.md` changes, the whole package is revalidated, and binary assets remain byte-identical. Frontmatter `name` must continue to match the URL/directory identity, so rename is not supported. A `409` keeps the user's draft open and offers a reload rather than overwriting a newer version.

Alternative considered: a structured frontmatter form. Re-serializing YAML can discard comments, formatting, or unknown forward-compatible fields; raw editing preserves the package contract exactly.

### Preserve defense in depth for ownership actions

The UI uses `mutable` only to decide which commands to render, but the server/store remains authoritative. Replace, enable/disable, and delete requests against built-ins continue to return `403`. Delete requires confirmation and snapshots the current mutable package before removal. Every successful import or mutation refreshes the shared live catalog, so later agent searches and market reloads observe the change without restart.

### Express Git ownership with an MCP allowlist

Keep `/server/data/` ignored; it already covers default user MCP configuration, uploaded user Skills, agent-created Skills, snapshots, and evolution data. Change `mcp_servers/` to ignore all children and re-include only `mcp_config.json`, `test_stdio_mcp/**`, and `test_sse_mcp/**`. Built-in Skill code under `server/app/skills/builtin/**` remains trackable. Verification uses `git check-ignore` against representative built-in and user paths.

## Risks / Trade-offs

- [ZIP bombs or malicious archive paths] -> Enforce independent compressed, expanded, entry-count, type, and path limits before publishing any file.
- [Concurrent edits overwrite newer content] -> Require the content hash returned by the edit-read endpoint and return `409` without changing either version.
- [A valid package contains binary assets] -> Preserve raw archive bytes and omit supporting files from text-only edit payloads.
- [Catalog precedence hides legacy duplicate packages] -> Reject new duplicates across all roots; leave legacy precedence intact and expose `shadowed_sources` for diagnosis.
- [Large catalogs make an unbounded page slow] -> Reuse server-side query and pagination instead of loading every body or every row at once.
- [Agent-created package bypasses the managed store] -> The supported authoring path remains the management API/store; direct filesystem writes are outside the guarantee and may require restart or an explicit refresh.
- [Multipart dependency adds deployment weight] -> Pin `python-multipart` within the server requirements and exercise startup/upload in API tests.

## Migration Plan

1. Add the ZIP importer, content-read API, and server tests without changing existing endpoints.
2. Add frontend types, API wrappers, view routing, and Skill market interactions.
3. Apply the `.gitignore` allowlist and verify existing tracked built-ins remain trackable while representative user paths are ignored.
4. Update README documentation for market behavior, package limits, editing scope, ownership labels, and Git data locations.

Rollback removes the new client view and endpoints while leaving imported user packages intact under `server/data/skills/user/`. Existing catalog loading and API behavior continue to recognize those packages.

## Open Questions

None. Package-resource editing and ZIP replacement are intentionally deferred rather than left as implementation-time choices.
