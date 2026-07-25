## 1. MCP Catalog Storage

- [x] 1.1 Extend `DataPaths` with the user MCP catalog directory/file and ensure it is created under `CASHCODE_DATA_DIR`.
- [x] 1.2 Add normalized MCP record/request models with stable-name, SSE URL, transport, display metadata, and bounded header validation.
- [x] 1.3 Implement a catalog store that reads built-ins from `mcp_servers/mcp_config.json`, reads user entries from the data directory, rejects source collisions, and atomically persists user mutations.
- [x] 1.4 Implement secret-safe public projections and masked-header preserve/replace semantics without logging or returning header values.
- [x] 1.5 Add pytest coverage for catalog merging, collision rejection, validation, atomic CRUD, built-in immutability primitives, and header masking.

## 2. MCP Runtime Lifecycle

- [x] 2.1 Pass optional configured headers into the SSE client and return bounded sanitized connection failure details from the connection layer.
- [x] 2.2 Add per-server lifecycle status, exact tool ownership, and per-server operation locking to `SimpleAgentLoop`.
- [x] 2.3 Implement idempotent connect that completes initialization and tool discovery before installing one handle/wrapper generation and writing a valid cache.
- [x] 2.4 Implement idempotent disconnect that closes the handle and unregisters exact server-owned tools even when transport shutdown reports an error.
- [x] 2.5 Implement runtime configuration replacement/removal hooks that refresh Skill availability, invalidate stale projections, and purge affected activated-tool references from loaded and persisted sessions.
- [x] 2.6 Add pytest coverage for successful/failed connection, same-server coalescing, cross-server concurrency, disconnect cleanup, edit cleanup, delete cleanup, and Skill dependency refresh.

## 3. MCP Management API

- [x] 3.1 Add an MCP management service that serializes catalog mutations with runtime cleanup and exposes normalized list/create/update/delete/connect/disconnect/tools operations.
- [x] 3.2 Add FastAPI request/response models and `/api/mcp/servers` CRUD routes with authoritative HTTP 403 protection for built-ins.
- [x] 3.3 Add connect, disconnect, and tools routes with lifecycle status, bounded errors, live tool metadata, and fingerprint-valid cache fallback.
- [x] 3.4 Initialize the catalog/service in the FastAPI lifespan, publish it through `app.state`, and load the merged configuration without connecting servers at startup.
- [x] 3.5 Add API tests for DTO shape, SSE-only enforcement, collision and not-found responses, built-in protection, mutation failure behavior, status transitions, and tools source selection.

## 4. Structured Chat Selection Runtime

- [x] 4.1 Add shared selection bounds/identifier validation and sanitize `mentioned_skills` plus `selected_mcp_connectors` from WebSocket message metadata before enqueueing `InboundMessage`.
- [x] 4.2 Add a non-persisting current-turn MCP activation overlay that composes with the existing `ActivatedToolSet` and always restores prior visibility on success, error, or cancellation.
- [x] 4.3 Resolve and exact-load structured Skill selections, deduplicate the legacy leading `@<skill>` selection, and fail clearly when a selected Skill becomes unavailable.
- [x] 4.4 Resolve and prepare selected MCP servers at turn start, expose only live owned wrappers through the turn overlay, and fail clearly when preparation cannot succeed.
- [x] 4.5 Persist bounded Skill/MCP selection receipts on user history entries and return them from the session-messages API without transport configuration or secrets.
- [x] 4.6 Add pytest coverage for metadata sanitization/rejection, selection limits, Skill deduplication, stale selections, turn-only MCP visibility, cleanup on failure, legacy no-selection behavior, and history projection.

## 5. Frontend MCP Data Layer

- [x] 5.1 Add frontend MCP DTOs, lifecycle types, CRUD/connect/disconnect/tools API wrappers, and normalized API error handling.
- [x] 5.2 Add Skill-list and MCP-picker query helpers that return only enabled/available Skills and connected MCP servers with discovered tools.
- [x] 5.3 Extend message, persisted-message, and outbound-frame types with canonical Skill/MCP selection receipts.
- [x] 5.4 Add pure TypeScript helpers for selection validation, deduplication, the combined limit, trigger parsing/replacement, and WebSocket metadata construction with focused tests.

## 6. Sidebar And MCP Market

- [x] 6.1 Add root `chat | mcp-market` view state and ensure new-chat/session selection returns to chat without losing the active session.
- [x] 6.2 Rework the sidebar to retain `新建对话`, add `MCP 市场`, and place session rows beneath an accessible collapsible `历史记录` control.
- [x] 6.3 Build the MCP market list with stable loading/error/empty states, source/status/tool-count presentation, an `内置` badge, retry, and responsive layout.
- [x] 6.4 Build the SSE-only create/edit form with internal name, display title, description, URL, dynamic header rows, field-level validation, masked-header editing, and Save/Cancel states.
- [x] 6.5 Implement connect/disconnect controls, retryable failure display, and authoritative refresh after each operation.
- [x] 6.6 Implement mutable-entry edit/delete menus and confirmed deletion while keeping built-in edit/delete controls absent.

## 7. Composer Picker And Message References

- [x] 7.1 Build the first-level `@` category menu and second-level searchable MCP/Skill panels with loading, empty, error, retry, and back states.
- [x] 7.2 Implement caret-boundary triggering, query replacement, ArrowUp/ArrowDown/Enter/Escape/back keyboard behavior, outside-click dismissal, and focus restoration.
- [x] 7.3 Add typed removable Skill/MCP chips, canonical deduplication, the combined eight-selection limit, and reset behavior on successful send/session change.
- [x] 7.4 Send plain task content plus structured metadata and attach the same receipts to optimistic user messages without allowing chip-only empty submissions.
- [x] 7.5 Normalize persisted selection receipts in session loading and render typed references in user bubbles with canonical fallback and responsive overflow behavior.
- [x] 7.6 Add frontend tests for picker state transitions, filtering, keyboard selection, duplicate/limit behavior, metadata frames, optimistic state, and history normalization.

## 8. Documentation And Verification

- [x] 8.1 Update README documentation for built-in versus user MCP storage, SSE/header configuration, explicit connect/disconnect, and the `@` selection workflow.
- [x] 8.2 Run the complete backend pytest suite and resolve lifecycle-task, transport, persistence, and API resource leaks or failures.
- [x] 8.3 Run frontend tests, `npm run lint`, and `npm run build`, resolving type, accessibility, and bundle errors.
- [x] 8.4 Start backend, the test SSE MCP, and frontend; verify built-in protection, user CRUD, authenticated-header masking, connect/disconnect, `@` Skill/MCP selection, tool execution, and history reload end to end.
- [x] 8.5 Use browser screenshots at desktop and mobile viewports to verify the sidebar, market, forms, picker, chips, errors, long labels, and all loading states without overlap or clipped text.
