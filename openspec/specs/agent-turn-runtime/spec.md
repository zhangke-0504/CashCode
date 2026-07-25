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

### Requirement: Keep chat infrastructure available without LLM configuration
The backend SHALL initialize its REST API, WebSocket channel, settings service, and non-LLM management capabilities when no valid LLM connection profile exists. A submitted chat turn SHALL fail with a clear configuration error without terminating the Agent loop or persisting a partial turn.

#### Scenario: Backend starts before first configuration
- **WHEN** neither persisted nor migratable LLM credentials are available
- **THEN** the HTTP and WebSocket services start and the user can reach LLM settings

#### Scenario: User sends a message while unconfigured
- **WHEN** a chat message selects a provider without valid saved connection fields
- **THEN** the client receives a clear `LLM 未配置` error, the user message is not committed as a completed turn, and later messages remain processable after configuration

### Requirement: Validate explicit model selection before a turn
The WebSocket ingress and Agent Loop SHALL treat the message's `llm` metadata as untrusted input, require bounded provider and model strings, and reject a provider that is not currently configured.

#### Scenario: Valid selection reaches the Agent Loop
- **WHEN** a message contains a well-formed `{provider, model}` selection for a configured provider
- **THEN** the sanitized selection is available to the Runner without changing persistent LLM settings

#### Scenario: Selection is missing or malformed
- **WHEN** a message omits the selection or contains an unknown provider, empty model, or oversized value
- **THEN** WebSocket ingress rejects the message and does not enqueue or persist a turn

### Requirement: Pin the selected LLM snapshot for a complete Agent turn
The Agent Runner SHALL acquire the provider client generation and model named by the message before its first model call and SHALL use that snapshot for every ReAct iteration and final fallback call in the turn.

#### Scenario: Credentials change during a tool-calling turn
- **WHEN** the selected provider's credentials change after the first model call but before the final response
- **THEN** every remaining model call in that turn uses the original client and model while a later turn uses the updated provider generation

#### Scenario: User selects another model for the next turn
- **WHEN** a completed turn used one model and the next message selects another
- **THEN** the next turn acquires the newly selected provider and model without mutating connection settings

#### Scenario: Snapshot acquisition fails
- **WHEN** the selected provider becomes unavailable before a turn starts
- **THEN** the turn returns a recoverable configuration error before executing tools or mutating durable session history

### Requirement: Propagate turn model selection to related model work
Turn-triggered consolidation and Skill Evolution work SHALL use the provider and model selected for that turn. Periodic Dream work SHALL use the last successfully acquired selection held in runtime memory and SHALL skip when none is available.

#### Scenario: Consolidation follows a turn
- **WHEN** a turn triggers conversation consolidation
- **THEN** consolidation uses the same provider and model identity as the completed turn

#### Scenario: Evolution is scheduled from a turn
- **WHEN** Skill Evolution schedules model work from completed turn evidence
- **THEN** the scheduled work retains that turn's provider and model identity

#### Scenario: Dream runs before any model selection
- **WHEN** the process starts and periodic Dream runs before a successful chat model acquisition
- **THEN** Dream skips model work without terminating the backend or creating a persistent default model

### Requirement: Complete chat turns independently of auxiliary memory work
The Agent Loop SHALL persist the final assistant response and session metadata and then publish exactly one terminal event without waiting for consolidation or other non-critical memory work. Auxiliary work SHALL be lifecycle-managed and SHALL NOT prevent a later turn for the same chat from starting.

#### Scenario: Consolidation is slow or does not return
- **WHEN** a completed turn triggers consolidation and its model request remains pending
- **THEN** the client receives `_turn_done` after the final response is durably committed and can submit a later turn without waiting for consolidation

#### Scenario: Consolidation finishes after another turn
- **WHEN** a background consolidation was prepared from an earlier history boundary and newer messages have since been appended
- **THEN** its commit preserves every newer message and applies a summary only to the captured prefix

#### Scenario: Agent Loop shuts down with auxiliary work pending
- **WHEN** the backend begins shutdown while consolidation tasks are running
- **THEN** the Agent Loop cancels and awaits its owned tasks without publishing duplicate terminal events or partially committing a summary

### Requirement: Bound and isolate auxiliary memory model failures
Production consolidation SHALL trigger at `40_000` history characters by default. Consolidation summaries and each Dream model phase SHALL have a finite operation timeout, SHALL avoid retries that exceed that budget, and SHALL leave all memory content and cursors unchanged when model work fails before commit.

#### Scenario: Ordinary conversation remains below the production threshold
- **WHEN** a chat history contains fewer than `40_000` characters
- **THEN** the completed turn does not make a consolidation model request

#### Scenario: Dream model request times out
- **WHEN** either Dream phase exceeds its operation timeout
- **THEN** Dream returns without changing `MEMORY.md` or Dream cursors and a later scheduled cycle can retry the same entries

#### Scenario: Auxiliary provider timeout is logged
- **WHEN** Dream or consolidation receives an expected provider timeout or connection failure
- **THEN** the server writes one sanitized warning without a traceback, prompt, response, endpoint credentials, or API key

#### Scenario: Unexpected auxiliary failure occurs
- **WHEN** Dream or consolidation encounters an unexpected programming or persistence exception
- **THEN** the exception remains isolated from chat processing and is logged with diagnostic traceback information
