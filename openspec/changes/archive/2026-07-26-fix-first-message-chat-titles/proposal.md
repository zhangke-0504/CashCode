## Why

New and reconnected chats remain labeled `新对话` because the backend's existing first-message title is persisted without notifying the active frontend, while every WebSocket `ready` or `attached` frame creates another placeholder history row. Manual renames can also be overwritten by the Agent's cached session metadata on a later turn, so title ownership is not reliable.

## What Changes

- Assign a deterministic first title when the backend accepts the first valid user question: collapse whitespace and use at most the first 40 characters, without an additional LLM request.
- Persist and publish the assigned title immediately instead of waiting for the assistant turn to finish, allowing the active sidebar to update during the first question.
- Treat connection-assigned and newly attached chat IDs as empty drafts and keep them out of session history until the first valid user message creates the session.
- Add a WebSocket session-update event so the frontend can insert or update the authoritative title and timestamp without reloading the session list.
- Make user renames update both durable metadata and the Agent's live metadata state; once a title exists, automatic naming never replaces it.
- Preserve existing manual rename and deletion interactions and keep `新对话` only as the presentation fallback for metadata that truly has no title.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `session-metadata`: Define normalized, one-time title assignment at the first accepted user question and permanent precedence for existing or user-provided titles.
- `chat-websocket-client`: Add authoritative session-update delivery and distinguish connection readiness from persisted session creation.
- `sidebar-session-list`: Keep empty draft chats out of history and update or insert the session row when the first title arrives.
- `session-management-api`: Require rename operations to remain authoritative across later Agent turns.

## Impact

- Backend Agent turn handling and live session metadata cache in `server/app/agent/loop.py`.
- WebSocket event routing in `server/app/ws/channel.py`.
- Session rename integration in `server/app/api/sessions.py` and application state wiring in `server/main.py`.
- Frontend WebSocket types and reducer behavior in `client/src/types.ts` and `client/src/context/ChatContext.tsx`.
- Focused backend and frontend tests for first-message naming, reconnect drafts, event-driven updates, and rename precedence.
- No new dependency, database, or LLM request is introduced.
