## ADDED Requirements

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
