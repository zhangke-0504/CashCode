## Why

CashCode tells the built-in `skill-creator` to use the Skill management API, but the chat Agent has no managed Skill mutation tool. It falls back to generic filesystem and shell tools, so a request such as creating a Chinese-named Skill can leave an invalid package on disk, fail to refresh the catalog, and still be reported as completed even though the Skill market and chat selector cannot see it.

## What Changes

- Add a server-managed chat authoring tool for creating Agent-owned Skills through the shared `SkillStore`, with validation, atomic publication, duplicate protection, server-owned metadata, and live catalog refresh.
- Update the built-in `skill-creator` contract and Agent guidance so chat creation uses the managed tool instead of direct writes or ad hoc HTTP/shell commands.
- Protect managed user/agent Skill roots from generic `write_file` and `edit_file` mutations that bypass validation and catalog refresh.
- Separate the immutable canonical Skill slug from an optional bounded display name so a package such as `renzhi-niuqu` can be shown as `认知扭曲` without weakening path and identity rules.
- Return structured authoring failures and never report creation success until the new `source=agent` record is visible in the live catalog.
- Surface bounded invalid-package diagnostics in the Skill market so legacy or externally written invalid packages do not disappear silently.
- Allow users to explicitly delete invalid user/Agent packages from the Skill market through a guarded store operation while keeping invalid built-ins immutable.
- Align the built-in `skill-creator` template exactly with CashCode loader rules so localized titles use `display_name` and only validated managed creation can report success.
- Add regression coverage for the observed chat transcript, Agent ownership, immediate market/composer visibility, invalid names, duplicate conflicts, protected roots, and restart-free discovery.

## Capabilities

### New Capabilities

- `chat-skill-authoring`: Managed Agent tool and interaction contract for creating valid Agent-owned Skills from chat and reporting authoritative success or failure.

### Modified Capabilities

- `local-skill-catalog`: Preserve canonical slug identity while exposing a separate display name and bounded invalid-package diagnostics.
- `skill-management-api`: Require chat-created packages to use the shared Skill store with Agent ownership, cross-root conflict checks, and immediate catalog visibility.

## Impact

- Agent tool registration and filesystem mutation guards under `server/app/agent/`.
- Shared Skill store lifecycle, package models/validation, catalog metadata, and Agent creation operations under `server/app/skills/` and `server/main.py`.
- Built-in `skill-creator` instructions and focused server tests for the managed chat workflow.
- Frontend Skill DTOs, market rows, composer labels, invalid-package diagnostics, and explicit invalid-package deletion under `client/src/`.
- The in-progress `add-skill-market-management` change remains the UI foundation; this change replaces its incorrect assumption that a managed chat authoring path already exists.
