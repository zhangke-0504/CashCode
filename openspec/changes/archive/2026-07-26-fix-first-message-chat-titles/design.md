## Context

The Agent already derives a title from the first user message, but it keeps that value only in its in-memory session metadata until a successful turn is fully persisted. The WebSocket protocol has no session metadata event, so the client-created `新对话` row remains stale until a later REST reload. Separately, `ready` and `attached` frames are treated as persisted sessions by the client even though the server has only allocated and subscribed a chat ID.

Session renames currently bypass the Agent and write metadata through a separate `MemoryStore` instance. Because the Agent retains a mutable metadata snapshot across turns, a later whole-file write can restore the pre-rename title. The change crosses the Agent, REST API, WebSocket protocol, and React state reducer, so the lifecycle and ownership rules need to be explicit.

## Goals / Non-Goals

**Goals:**

- Give every new session an authoritative, human-readable title as soon as its first valid question is accepted.
- Keep connection-only and explicitly created empty chats as drafts rather than history rows.
- Deliver title changes to the active client without polling or reloading all sessions.
- Guarantee that any existing title, including a user rename, takes precedence over automatic naming.
- Keep the change deterministic, local, and covered by focused backend and frontend tests.

**Non-Goals:**

- Generating or refining titles with an LLM.
- Automatically rewriting existing non-empty titles.
- Bulk-renaming legacy persisted sessions that have history but no title.
- Changing message durability or preserving failed assistant turns.
- Adding multi-process file locking or multi-user synchronization.

## Decisions

### 1. Connection IDs are drafts until the first accepted message

`ready` and `attached` continue to provide usable chat IDs, but the frontend does not insert those IDs into the persisted session list. The active chat may therefore reference a draft ID that is absent from `sessions`. Clicking `新建对话` switches to that empty draft, while reconnecting does not append another `新对话` row.

The draft is promoted into session history only after the backend publishes authoritative session metadata. This keeps the existing wire handshake and avoids introducing a separate create-session REST endpoint.

Alternative considered: continue inserting placeholder rows and remove unused ones later. This retains ambiguous transient state, complicates reconnect cleanup, and still exposes duplicate `新对话` entries.

### 2. The backend assigns one deterministic title

For a session with no title and no prior durable user history, the Agent normalizes the first accepted task by trimming it, collapsing consecutive whitespace to one space, and taking the first 40 Unicode characters. Structured Skill and MCP selections are not included because they are carried outside message content. No title is generated for a legacy session that already has durable history.

Title assignment happens after envelope, selection, and selected LLM validation but before potentially long assistant or tool execution. The Agent persists the title immediately, then publishes the session update. Once a non-empty title exists, automatic naming does nothing. A downstream assistant failure therefore does not retract an already accepted session title.

Alternative considered: generate a semantic title with the selected LLM. That adds cost, latency, and another failure path, and it can make titles change unexpectedly. Alternative considered: derive the title only in React. That makes persistence and truncation rules depend on client behavior and cannot protect other clients.

### 3. WebSocket publishes an authoritative session update

The Agent emits an outbound message tagged as a session metadata update after the title write succeeds. `WebSocketChannel` maps it to:

```json
{
  "event": "session_updated",
  "chat_id": "...",
  "title": "...",
  "updated_at": "..."
}
```

The React reducer upserts the matching session, moves it to the recent position, and preserves it as the active chat when appropriate. This event is intentionally broader than `title_updated` so the same payload keeps the displayed timestamp coherent.

Alternative considered: call `GET /api/sessions` after every `done` event. That delays the title until the whole response completes, performs unnecessary list reads on every turn, and leaves the first-turn failure case unnamed.

### 4. Agent-owned title mutation is the consistency boundary

The session API resolves the live Agent from `request.app.state` and delegates title changes to an Agent method that updates the currently cached metadata object, when loaded, and persists the same value. Turn failure rollback must preserve the current title rather than replacing the entire metadata object with a stale pre-turn copy.

All title creation and rename writes therefore pass through the same in-process owner. Existing per-chat turn serialization remains responsible for turn history; title mutation stays small and synchronous so a rename does not wait for a complete LLM response.

Alternative considered: add `title_source` or a separate title file. Neither prevents stale whole-metadata writes by itself, and a new persisted field is unnecessary when the rule is simply "never auto-replace a non-empty title."

### 5. `新对话` remains a presentation fallback

The session list API continues returning `新对话` when persisted metadata truly has no title, preserving compatibility for legacy data. The client does not use that display string to decide whether a title is assigned; draft state and authoritative server events make that decision instead. This avoids accidentally replacing a title that a user intentionally set to `新对话`.

## Risks / Trade-offs

- [A first accepted message can create a named session even if assistant execution later fails] -> This matches the requested title timing and preserves the accepted conversation identity; message durability remains explicitly out of scope.
- [Older clients ignore `session_updated`] -> The event is additive, and persisted titles remain available through `GET /api/sessions` after reload.
- [An active draft is absent from the sidebar list] -> The composer and chat view continue to use `activeSessionId`; reducer tests will cover startup, explicit new chat, and reconnect ordering.
- [Legacy history without a title remains `新对话`] -> Avoid guessing from a later message; users can rename it manually, and a separate migration can be proposed if needed.
- [Metadata writes are still single-process] -> CashCode remains a local single-user application; multi-process locking is outside this change.

## Migration Plan

1. Add backend title assignment, shared rename mutation, and the additive `session_updated` frame.
2. Update frontend frame types and reducer behavior to keep drafts out of history and upsert authoritative sessions.
3. Deploy backend and frontend together. Existing non-empty titles require no migration and remain unchanged.
4. Rollback is compatible: an older frontend ignores the new frame and retrieves the persisted title on its next session-list load.

## Open Questions

None. The first title is deterministic and stable; semantic LLM-generated refinement is deferred.
