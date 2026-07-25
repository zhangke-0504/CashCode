## Context

CashCode currently reads `mcp_servers/mcp_config.json` once when `SimpleAgentLoop` starts. The loop can lazily establish stdio or SSE sessions, register wrappers, cache tool schemas, and activate tools through `mcp_prepare`, but it has no mutable catalog, live status API, server-level tool ownership, or hot reload path. The frontend is a single chat view with a fixed session-list sidebar and a plain textarea composer. `InboundMessage` already has a metadata field, but the WebSocket channel does not accept client metadata.

The application is local-first and single-user. Existing built-in stdio and SSE configurations must remain compatible, while user-created entries are deliberately limited to SSE for this change. Skill management and exact Skill loading already exist and should be reused.

## Goals / Non-Goals

**Goals:**

- Provide authoritative CRUD and runtime lifecycle management for configured MCP servers.
- Preserve built-in configurations as read-only entries while persisting user entries outside the source tree.
- Make connection state and failure information observable to the market and composer.
- Add a usable MCP market and reorganize the sidebar without regressing session workflows.
- Support explicit, structured, current-turn Skill and MCP selection from a two-level `@` picker.
- Persist enough selection metadata to reproduce sent-message references after a reload.
- Keep connection, registry, cache, Skill availability, and session activation state coherent during edits, deletion, and disconnects.

**Non-Goals:**

- A remote/community MCP catalog, installation service, ratings, billing, or account synchronization.
- OAuth, browser-based login, secret encryption at rest, stdio creation by users, or streamable HTTP transport.
- Editing or deleting built-in MCP definitions.
- Automatically connecting every configured MCP server at startup.
- Replacing model-driven `tool_search`, `mcp_prepare`, or `skill_search` behavior when no explicit selection is supplied.
- Building a full Skill marketplace; the selector consumes the existing local Skill catalog.

## Decisions

### 1. Merge read-only built-ins with a writable user catalog

`mcp_servers/mcp_config.json` remains the source-controlled built-in source. A new path under `CASHCODE_DATA_DIR`, such as `mcp/servers.json`, stores only user entries and is written atomically. The catalog exposes a normalized record containing a stable ASCII `name`, `display_name`, `description`, transport details, source, `builtin`, and `mutable` flags.

User names use `[a-z0-9][a-z0-9_-]{0,63}` and cannot collide with a built-in name. Display names remain Unicode. User records MUST use `type: "sse"` with an HTTP(S) URL. Built-in records may continue to use existing stdio or SSE transports.

Alternative considered: write user changes back to `mcp_config.json`. This would mix runtime data with source-controlled fixtures, make built-in protection ambiguous, and create avoidable merge churn.

### 2. Put catalog mutation and lifecycle orchestration behind one service

A server-side MCP management service owns the catalog, an async mutation lock, and calls into `SimpleAgentLoop` for runtime operations. FastAPI routes obtain the service from `app.state`; they do not manipulate loop dictionaries or files directly.

The API surface is:

- `GET /api/mcp/servers`
- `POST /api/mcp/servers`
- `PUT /api/mcp/servers/{name}`
- `DELETE /api/mcp/servers/{name}`
- `POST /api/mcp/servers/{name}/connect`
- `POST /api/mcp/servers/{name}/disconnect`
- `GET /api/mcp/servers/{name}/tools`

Create and edit persist configuration but do not report a connection until a real handshake and `list_tools` succeed. Editing a connected user entry disconnects the old generation and leaves the saved entry disconnected. Delete disconnects and cleans runtime state before removing the user record. Built-in mutation routes reject requests authoritatively even if a client hides the controls.

Alternative considered: expose the loop directly to the router as spore does in some paths. A dedicated service better isolates file persistence, validation, and rollback/error behavior in this smaller codebase.

### 3. Track server-owned tools and lifecycle state explicitly

`SimpleAgentLoop` gains a per-server tool-name ownership map, per-server operation locks, and status records. Status is one of `disconnected`, `connecting`, `connected`, or `error`, with a bounded public error and tool count. Connect is idempotent and coalesces concurrent attempts for the same server. Disconnect closes the handle, unregisters every owned wrapper, removes the handle and ownership entry, refreshes the Skill catalog, and invalidates affected cached projections.

Edits and deletes also remove stale `activated_tools` entries with the server's exact owned tool names from loaded and persisted session metadata. This prevents deleting and later recreating a server with the same name from silently inheriting old activation authority.

Alternative considered: infer ownership from the `mcp_{server}_` prefix. An explicit ownership map avoids prefix ambiguity and makes cleanup reliable when tool names or normalization rules evolve.

### 4. Treat request headers as local secrets without promising encryption

User SSE entries may include optional HTTP headers so token-authenticated third-party servers are usable. The MCP transport passes these headers to `sse_client`. The local runtime file contains the actual values, but list/get responses expose header names and masked values only. Editing preserves an existing value when the corresponding masked placeholder is submitted and replaces it only with an explicit new value.

This change does not claim encryption at rest; the data directory remains local user data. Header values MUST never be included in connection errors, logs, tool cache fingerprints returned to clients, or chat history.

Alternative considered: URL-only SSE. That would exclude a large class of third-party MCP services and fail the stated connection goal.

### 5. Use structured message metadata for explicit selections

The composer sends canonical selections in the existing message envelope:

```json
{
  "type": "message",
  "chat_id": "...",
  "content": "查询今天的天气",
  "metadata": {
    "mentioned_skills": [{"name": "weather", "label": "天气"}],
    "selected_mcp_connectors": [{"server": "weather-mcp", "label": "天气 MCP"}]
  }
}
```

The WebSocket channel accepts only these bounded fields, limits the combined selection count to eight, validates canonical identifiers, and treats labels as display-only. The server resolves current catalog state instead of trusting client-supplied availability or tool names. Unknown, disabled/unavailable Skills and missing or failed MCP servers produce a clear turn error rather than silently falling back.

The existing leading `@<skill>` parser remains supported. When structured and legacy selections name the same Skill, the server loads it once.

Alternative considered: encode selections into visible text. Text parsing cannot reliably distinguish display labels from stable identities and creates an authorization path based on mutable user content.

### 6. Make explicit selection current-turn-only

Selected Skills are loaded through the existing `SkillLoadTool` and `TurnSkillContext`. Selected MCP servers are prepared if necessary, then their owned tool names are added to a non-persisting turn activation overlay consumed by `DeferredAwareRegistry`. The overlay composes with the existing session activation set but is discarded after the turn. A market connection remains alive until explicit disconnect, edit/delete, or server shutdown; only tool exposure caused by the composer selection is turn-scoped.

When no structured selection is supplied, existing lazy discovery and persistent activation behavior remains unchanged.

Alternative considered: call the existing persistent `ActivatedToolSet.activate` for selected MCP tools. That would make a one-message chip affect later turns after the visible selection disappeared.

### 7. Keep chips separate from task text and persist display receipts

The textarea remains the task-text editor. Typing `@` at a valid token boundary opens a category menu (`MCP`, `Skill`); choosing a category opens a searchable second-level list. Selection removes the trigger text and adds a stable removable chip adjacent to the input. The picker supports mouse and keyboard navigation, Escape/back navigation, deduplication, and removal.

The optimistic user message stores the same selection receipts as the outbound metadata. Durable user history stores canonical identity plus bounded label, and `GET /api/sessions/{chat_id}/messages` projects them back to the frontend. The model receives the plain task content; display labels are not added to model instructions.

Alternative considered: migrate to a contenteditable rich-text editor like spore. Keeping the existing textarea and a separate chip row is substantially smaller and avoids selection/caret serialization complexity while meeting the required interaction.

### 8. Add a small application view state rather than a router

The root layout uses a `chat | mcp-market` view state. `MCP 市场` selects the market; selecting a session or creating a conversation returns to chat. The sidebar keeps `新建对话` as a primary command, adds the market navigation item, and renders session rows beneath a collapsible `历史记录` control. Collapsing history does not change the active chat.

Alternative considered: introduce React Router. Two local views do not justify a routing dependency or URL contract in this desktop-style application.

## Risks / Trade-offs

- [A failed disconnect can leave a transport task alive] -> Make cleanup idempotent, await handle closure with the existing timeout, always unregister wrappers in `finally`, and surface a bounded warning.
- [Configuration and runtime state cannot be one filesystem transaction] -> Serialize mutations, validate before changes, clean runtime before delete, use atomic file replacement, and return explicit partial-failure errors without claiming success.
- [Plaintext headers exist in the local data directory] -> Mask all API responses and logs, document the local-only boundary, and defer OS keychain/encryption support to a separate change.
- [A connection can drop after the picker fetched its list] -> Revalidate and prepare selected servers at turn start; fail clearly if reconnection does not succeed.
- [Loading several Skills can expand model context] -> Bound combined explicit selections to eight and rely on existing Skill validation/current-turn loading semantics.
- [Status can become stale without push events] -> Refresh the market on entry and after every mutation; composer fetches fresh lists when the picker opens. Realtime status streaming is out of scope.
- [Existing code has little tracked automated coverage] -> Add focused pytest coverage for storage, APIs, concurrency, cleanup, metadata sanitization, and turn scoping; add pure TypeScript picker tests plus build/lint and browser verification.

## Migration Plan

1. Add the user MCP data path and catalog loader; treat the existing static JSON entries as built-in without rewriting the file.
2. Initialize the management service and normalized merged config during FastAPI lifespan startup. Startup continues to leave all MCP servers disconnected.
3. Add lifecycle ownership/status support and APIs before exposing frontend controls.
4. Add market/sidebar UI, then structured WebSocket metadata, turn selection, history projection, and message chips.
5. Existing installations start with an empty user catalog and see their current static entries marked `内置`.

Rollback removes the new routes and UI while leaving `CASHCODE_DATA_DIR/mcp/servers.json` untouched. Older code ignores that file and continues to use the original static config, so no destructive data migration is required.

## Open Questions

None. The proposal adopts read-only built-ins, optional masked SSE headers, current-turn selection scope, and a collapsible in-sidebar history group as the implementation contract.
