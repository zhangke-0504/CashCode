## ADDED Requirements

### Requirement: Merge built-in and user MCP catalogs
The system SHALL expose one normalized MCP server catalog formed from the read-only `mcp_servers/mcp_config.json` built-in source and a writable user source under `CASHCODE_DATA_DIR`, without allowing a user record to shadow a built-in name.

#### Scenario: Existing static servers are listed
- **WHEN** the built-in configuration contains valid stdio or SSE entries and the user catalog is empty
- **THEN** `GET /api/mcp/servers` returns those entries with `builtin: true`, `mutable: false`, and their configured display metadata

#### Scenario: User and built-in entries are merged
- **WHEN** valid user MCP entries exist with names distinct from all built-ins
- **THEN** the list endpoint returns both sources with stable names and source-appropriate mutability flags

#### Scenario: User name collides with built-in
- **WHEN** a client attempts to create a user MCP using an existing built-in name
- **THEN** the system rejects the request with a conflict response and leaves both catalog sources unchanged

### Requirement: Manage SSE-only user MCP entries
The system SHALL allow creation, editing, and deletion of user MCP entries with a stable ASCII name, display name, description, SSE URL, and optional request headers, and SHALL persist successful mutations atomically.

#### Scenario: User creates a valid SSE MCP
- **WHEN** a client submits a unique name matching `[a-z0-9][a-z0-9_-]{0,63}`, `type: "sse"`, and a valid HTTP(S) URL
- **THEN** the system persists the user entry, returns it as `builtin: false` and `mutable: true`, and leaves it disconnected until an explicit connect operation

#### Scenario: Unsupported user transport is rejected
- **WHEN** a client submits a user MCP with stdio, streamable HTTP, or another unsupported transport
- **THEN** the system returns a validation error and does not modify the user catalog

#### Scenario: User edits a disconnected entry
- **WHEN** a client updates mutable display metadata, URL, or headers for an existing disconnected user MCP
- **THEN** the system atomically replaces the persisted record and returns the normalized disconnected entry

#### Scenario: User deletes an entry
- **WHEN** a client deletes an existing user MCP after runtime cleanup succeeds
- **THEN** the system removes it from the user catalog and subsequent list requests no longer return it

### Requirement: Protect built-in MCP entries
The server SHALL reject edit and delete operations for built-in MCP entries regardless of client behavior.

#### Scenario: Client attempts to edit a built-in MCP
- **WHEN** a client sends `PUT /api/mcp/servers/{name}` for a built-in entry
- **THEN** the server returns HTTP 403 and does not alter the built-in source or runtime configuration

#### Scenario: Client attempts to delete a built-in MCP
- **WHEN** a client sends `DELETE /api/mcp/servers/{name}` for a built-in entry
- **THEN** the server returns HTTP 403 and keeps the entry available for connection

### Requirement: Keep SSE header values secret in public projections
The system SHALL pass configured headers to the SSE transport while preventing header values from appearing in list responses, tool responses, connection errors, logs, or conversation history.

#### Scenario: Authenticated SSE connection is opened
- **WHEN** a user MCP has an `Authorization` header and the client requests connection
- **THEN** the runtime passes the actual header value to `sse_client` but public MCP DTOs expose only the header name and a masked value

#### Scenario: Masked header is preserved during edit
- **WHEN** an edit request submits the defined masked placeholder for an existing header
- **THEN** the system preserves the stored secret instead of replacing it with the placeholder

#### Scenario: Connection error contains request context
- **WHEN** an SSE connection using secret headers fails
- **THEN** the returned and logged error is bounded and contains no configured header value

### Requirement: Connect and disconnect MCP servers explicitly
The system SHALL provide idempotent explicit connect and disconnect operations and SHALL report `disconnected`, `connecting`, `connected`, or `error` lifecycle status with connection state, bounded error detail, and discovered tool count.

#### Scenario: MCP connects successfully
- **WHEN** a client sends `POST /api/mcp/servers/{name}/connect` and the configured server completes transport setup, MCP initialization, and `list_tools`
- **THEN** the endpoint returns a connected record and the listed tool count matches the registered server-owned tools

#### Scenario: MCP connection fails
- **WHEN** transport setup, initialization, or tool discovery fails
- **THEN** no unusable handle or wrappers remain registered and the endpoint returns an error status with a bounded non-secret failure message

#### Scenario: Connected MCP is connected again
- **WHEN** the connect endpoint is called for an already healthy connected server
- **THEN** the operation succeeds idempotently without creating another owner task or duplicate wrappers

#### Scenario: MCP disconnects
- **WHEN** a client sends `POST /api/mcp/servers/{name}/disconnect` for a connected server
- **THEN** the handle closes, all server-owned wrappers are unregistered, the tool count becomes zero, and status becomes disconnected

### Requirement: Serialize per-server lifecycle mutations
The system SHALL serialize connect, disconnect, edit, and delete operations for the same MCP server while allowing operations for different servers to proceed independently.

#### Scenario: Two clients connect the same server concurrently
- **WHEN** two connect requests arrive before the first handshake completes
- **THEN** they observe one shared connection attempt and at most one live handle and wrapper set is installed

#### Scenario: Different servers connect concurrently
- **WHEN** connect requests target two distinct MCP names
- **THEN** a lock for one name does not globally block the other connection

### Requirement: Clean runtime state when configuration changes
The system SHALL track exact server-owned tool names and remove obsolete handles, wrappers, cache projections, Skill availability, and persisted activation references when a server is disconnected, edited, or deleted.

#### Scenario: Connected user MCP is edited
- **WHEN** a client saves a changed URL or headers for a connected user entry
- **THEN** the old connection and tools are removed, the new configuration is persisted, and the entry remains disconnected until explicitly connected again

#### Scenario: Activated MCP is deleted
- **WHEN** a user MCP whose tools appear in session activation metadata is deleted
- **THEN** its exact owned tool names are removed from loaded and durable session activation metadata and cannot reappear as callable tools

#### Scenario: Skill depends on deleted MCP
- **WHEN** a configured MCP is deleted and a Skill requires that server
- **THEN** the Skill catalog refreshes and reports the dependency as missing

### Requirement: List tools for a managed MCP server
The system SHALL provide `GET /api/mcp/servers/{name}/tools` with normalized tool identity, description, input schema, source, and current lifecycle information, using live data when connected and a valid transport-fingerprint cache when disconnected.

#### Scenario: Connected server tools are requested
- **WHEN** the server is connected and has registered wrappers
- **THEN** the endpoint returns live tool metadata and `source: "live"`

#### Scenario: Disconnected server has valid cache
- **WHEN** the server is disconnected and its cache fingerprint matches the current configuration
- **THEN** the endpoint returns non-callable cached metadata without reporting the server as connected

#### Scenario: Configuration changed after cache was written
- **WHEN** the current transport fingerprint differs from the cached fingerprint
- **THEN** the endpoint ignores the stale cache and returns no cached tools

