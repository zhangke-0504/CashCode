## 1. Backend Title Lifecycle

- [x] 1.1 Add a reusable first-title helper that trims the accepted task, collapses consecutive whitespace, and limits the result to 40 Unicode characters.
- [x] 1.2 Update Agent turn intake to assign and persist a title only when the session has neither a non-empty title nor prior durable user history, before assistant execution begins.
- [x] 1.3 Publish an outbound session metadata update containing `chat_id`, `title`, and `updated_at` immediately after the first title is persisted, and keep that title when downstream turn execution fails.
- [x] 1.4 Add an Agent-owned rename operation that updates loaded metadata and durable metadata together, and adjust turn rollback so a concurrent or earlier manual rename cannot be restored to a stale title.
- [x] 1.5 Route `PATCH /api/sessions/{chat_id}` through the live Agent from FastAPI application state while preserving current validation, not-found behavior, and response shape.

## 2. WebSocket Session Protocol

- [x] 2.1 Map Agent session metadata updates to the additive `session_updated` WebSocket frame with a stable ISO timestamp.
- [x] 2.2 Update the documented frame union and backend protocol comments so `session_updated` is represented consistently without changing existing chat, stream, tool, or error frames.

## 3. Frontend Draft And Session State

- [x] 3.1 Extend frontend WebSocket types and frame handling for `session_updated` payloads.
- [x] 3.2 Change `ready` and `attached` reducer behavior so their chat IDs can become the active empty draft without inserting a placeholder row into session history.
- [x] 3.3 Upsert authoritative session updates into the sidebar list by `chat_id`, update title and timestamp, keep the intended active chat, and prevent duplicate rows across repeated events.
- [x] 3.4 Verify initial REST session loading, explicit `新建对话`, session switching, deletion, and reconnect ordering still leave the composer with a usable active chat ID.

## 4. Verification

- [x] 4.1 Add backend tests for whitespace normalization, 40-character truncation, title publication before turn completion, downstream failure retention, existing-title preservation, and legacy untitled history behavior.
- [x] 4.2 Add session API and Agent-state tests proving a manual rename survives later successful turns, failed turns, and a rename performed while a turn is in flight.
- [x] 4.3 Add frontend state tests proving `ready`, reconnect, and `attached` do not create history rows while first and repeated `session_updated` events produce exactly one correctly titled row.
- [x] 4.4 Run the server pytest suite and the client test, lint, and production-build commands; resolve regressions introduced by the change.
