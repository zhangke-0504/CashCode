# Agent Turn Runtime Specification

## Purpose
Define turn serialization, live tool refresh, complete traces, and safe result persistence for the server agent runtime.

## Requirements

### Requirement: Turns for one chat execute serially
The Agent Loop SHALL serialize complete turn handling per `chat_id` while allowing turns for different chats to execute concurrently.

#### Scenario: Two messages arrive for one chat
- **WHEN** the second message arrives before the first turn has completed persistence
- **THEN** the second waits and then observes the first turn's final history and session metadata

#### Scenario: Messages arrive for different chats
- **WHEN** independent chats have turns ready at the same time
- **THEN** their per-chat locks do not force global serialization

### Requirement: Tool schemas refresh during the ReAct loop
The Runner SHALL obtain the current registry definitions before each model iteration so registry and activation revisions take effect within the same turn.

#### Scenario: Tool is activated in an iteration
- **WHEN** `skill_load`, `tool_search`, or `mcp_prepare` activates or registers a tool in iteration N
- **THEN** the tool schema is available to the model in iteration N+1 of the same turn

### Requirement: Runner returns a complete ordered turn trace
The Runner SHALL return every assistant tool-call message, corresponding tool result, final response, tool identity, and completion status in protocol order.

#### Scenario: Turn performs multiple tool-call iterations
- **WHEN** a turn calls Skill search, Skill load, MCP preparation, and a domain tool across iterations
- **THEN** the trace contains all calls and results in their original order rather than retaining only the last tool-call message

### Requirement: Tool results have separate projections
The runtime SHALL support distinct model, public WebSocket, and durable history representations for a tool result while remaining compatible with existing plain-string tool implementations.

#### Scenario: Existing string tool returns
- **WHEN** a tool returns a plain string
- **THEN** the runtime uses a bounded compatible representation for all projections

#### Scenario: Ephemeral Skill result returns
- **WHEN** `skill_load` returns full instructions marked ephemeral
- **THEN** the model receives the instructions for the active turn, WebSocket clients receive only a bounded public receipt, and durable/in-memory history receives only the durable receipt

### Requirement: Durable history preserves valid tool chains
The persistence layer SHALL store every durable tool call and corresponding result from a completed turn in valid order and SHALL not store ephemeral model-only content.

#### Scenario: Process restarts after a Skill-using turn
- **WHEN** the session history is loaded again
- **THEN** it contains a compact valid record of the complete tool chain and no full `SKILL.md` load result

### Requirement: Sanitize explicit capability selections
The WebSocket ingress and Agent Loop SHALL treat selection metadata as untrusted input, enforce a combined maximum of eight entries, validate canonical identifiers and bounded display labels, and resolve authorization from current server catalogs.

#### Scenario: Valid metadata reaches the Agent Loop
- **WHEN** a message contains well-formed `mentioned_skills` or `selected_mcp_connectors`
- **THEN** `InboundMessage.metadata` contains only the sanitized canonical and display fields

#### Scenario: Malformed metadata is supplied
- **WHEN** either selection field has the wrong type, too many entries, an invalid identifier, or an oversized label
- **THEN** WebSocket ingress rejects the message with a clear error and does not enqueue a turn

### Requirement: Load explicitly selected Skills for the current turn
The Agent Loop SHALL exact-load each selected Skill through existing validation and dependency checks, deduplicate it against the backward-compatible leading `@<skill>` syntax, and expose full instructions only in the active turn.

#### Scenario: Available Skill is selected
- **WHEN** sanitized metadata names an enabled available Skill
- **THEN** its exact instructions enter the current turn and durable history receives only the normal compact Skill receipt

#### Scenario: Structured and legacy selection match
- **WHEN** metadata and a leading `@<skill>` token select the same canonical Skill
- **THEN** the Skill is validated and loaded once and the remaining text is used as task content

#### Scenario: Selected Skill is no longer available
- **WHEN** the Skill was listed by the client but is disabled, deleted, invalid, or missing dependencies before turn execution
- **THEN** the turn returns a clear selection error and does not silently continue without the Skill

### Requirement: Prepare explicitly selected MCP servers for the current turn
The Agent Loop SHALL resolve each selected MCP against the current managed catalog, ensure a live prepared connection, and expose its exact owned tools through a non-persisting turn activation overlay.

#### Scenario: Connected MCP is selected
- **WHEN** metadata names a configured connected MCP with discovered tools
- **THEN** its owned tools are visible to the model for that turn without changing durable session activation metadata

#### Scenario: MCP connection dropped after selection
- **WHEN** a configured selected MCP is no longer healthy at turn start
- **THEN** the runtime performs the normal bounded prepare attempt and proceeds only if initialization and tool discovery succeed

#### Scenario: Selected MCP cannot be prepared
- **WHEN** the selected server is missing or the prepare attempt fails
- **THEN** the turn returns a clear selection error and does not expose stale or cached-only wrappers as callable

### Requirement: Discard explicit MCP exposure after the turn
The runtime SHALL remove the temporary MCP activation overlay after success, error, or cancellation while leaving an intentionally connected MCP transport available for later explicit use.

#### Scenario: Selected MCP turn completes
- **WHEN** a turn using an explicitly selected MCP reaches final persistence
- **THEN** the selection overlay is discarded and subsequent turns do not inherit visibility solely from that chip

#### Scenario: Selected MCP turn fails
- **WHEN** the turn raises an exception after temporary tools were exposed
- **THEN** cleanup still discards the overlay and restores the prior session activation state

### Requirement: Preserve behavior without explicit selections
The Agent Loop SHALL retain existing Skill search/load, tool search, MCP prepare, and persistent activation behavior when a message contains no structured selection metadata.

#### Scenario: Ordinary message is processed
- **WHEN** a message has no explicit selection metadata and no leading Skill token
- **THEN** the existing model-driven discovery and activation workflow executes without a new capability restriction
