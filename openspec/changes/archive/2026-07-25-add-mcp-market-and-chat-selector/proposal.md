## Why

CashCode already has lazy stdio/SSE MCP execution and a local Skill catalog, but users cannot configure or manage third-party MCP servers and cannot explicitly select MCP or Skill capabilities from the chat composer. This leaves the MCP runtime accessible only through static files and model-driven discovery instead of a complete user workflow.

## What Changes

- Add a local MCP server management API backed by a read-only built-in catalog plus a writable user catalog.
- Allow users to create SSE MCP entries with identity, display metadata, URL, and optional request headers; user entries can be edited or deleted while built-in entries are marked as built-in and remain read-only.
- Add explicit connect and disconnect operations with observable lifecycle status, tool counts, connection errors, and correct cleanup of server-owned tools.
- Add an `MCP 市场` view and left-sidebar button. Keep `新建对话`, and place conversation rows under a collapsible `历史记录` group.
- Add a two-level `@` picker in the chat composer: first choose `MCP` or `Skill`, then choose from currently usable entries. Selected entries appear as removable chips.
- Send selected Skills and MCP servers as validated WebSocket metadata, apply them only to the current turn, and preserve their display metadata in conversation history.
- Keep the existing leading `@<skill>` text syntax as a backward-compatible input path.

## Capabilities

### New Capabilities

- `mcp-server-management`: Built-in/user MCP catalog merging, SSE-only user CRUD, secret-safe configuration, connection lifecycle, runtime status, tool ownership, and management APIs.
- `mcp-market-view`: MCP market navigation, listing, status presentation, creation, connection, disconnection, editing, and deletion workflows.

### Modified Capabilities

- `sidebar-session-list`: Add MCP market navigation and organize conversations beneath a collapsible history group while retaining new conversation creation.
- `composer-input`: Add the two-level `@` capability picker, filtering, keyboard interaction, and removable Skill/MCP chips.
- `chat-websocket-client`: Transmit bounded structured Skill/MCP selections in message metadata and handle validation errors.
- `agent-turn-runtime`: Validate explicit selections, load selected Skills, prepare selected MCP servers, and expose their capabilities for the current turn only.
- `session-management-api`: Return persisted Skill/MCP selection metadata with user messages so references survive history reload.
- `chat-view`: Render selected Skill/MCP references on optimistic and persisted user messages.

## Impact

- Backend: `server/app/agent`, `server/app/ws`, `server/app/api`, `server/app/paths.py`, MCP cache/config handling, and conversation persistence projections.
- Frontend: application view state, sidebar, composer, message types/rendering, REST API wrappers, and WebSocket message frames.
- Data: existing `mcp_servers/mcp_config.json` becomes the read-only built-in source; user MCP data is stored atomically under `CASHCODE_DATA_DIR`.
- Compatibility: existing built-in stdio/SSE entries and leading `@<skill>` messages continue to work; only user-created MCP entries are restricted to SSE.
- Verification: backend pytest coverage is required for catalog/API/lifecycle/metadata behavior, plus focused frontend tests and build/lint/browser checks for the interaction flow.
