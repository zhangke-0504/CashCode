## Why

CashCode already has a local Skill catalog and mutable user/agent Skill storage, but users cannot manage those Skills from the application and cannot import packaged Skills. Adding a local Skill market closes the interaction gap with the Spore reference while preserving CashCode's local-first ownership and security boundaries.

## What Changes

- Add a `Skill 市场` sidebar destination that lists the effective built-in, uploaded, and agent-created Skills with source, version, availability, and dependency status.
- Mark built-in Skills as `内置` and keep them read-only, while exposing edit and delete actions only for mutable uploaded and agent-created Skills.
- Add ZIP upload for one validated Skill package, with bounded extraction, path and symlink defenses, duplicate-name rejection, atomic installation into the user Skill root, and live catalog refresh.
- Add full `SKILL.md` retrieval and optimistic-concurrency editing for mutable Skills while preserving supporting package files and existing snapshots.
- Ensure valid Skills created through the existing chat/agent authoring path appear in the same market and remain editable under their `agent` ownership.
- Update repository ignore rules so only the built-in MCP catalog and test MCP implementations under `mcp_servers/` are trackable; runtime user MCP and user/agent Skill data remain untracked while built-in Skills remain tracked.

## Capabilities

### New Capabilities

- `skill-market-view`: Local Skill discovery and management UI, including source/status presentation and protected actions.
- `skill-package-import`: Secure ZIP validation and atomic installation of user-owned Skill packages.

### Modified Capabilities

- `skill-management-api`: Expose complete editable Skill content and preserve conflict-safe mutations for mutable user and agent Skills.
- `sidebar-session-list`: Add navigation to the Skill market while preserving the active chat and session history state.

## Impact

- Frontend routing, sidebar navigation, API types and wrappers, and new Skill market/upload/edit UI components under `client/src/`.
- Skill API, storage, package validation/import code, and focused API/store tests under `server/app/` and `server/tests/`.
- A multipart upload dependency may be required if the import endpoint uses FastAPI `UploadFile`/`FormData`.
- `.gitignore` rules for the repository-owned `mcp_servers/` allowlist and explicit documentation of built-in versus runtime Skill ownership.
- Existing chat, MCP market, Skill loading, and built-in package behavior remain compatible.
