## ADDED Requirements

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

