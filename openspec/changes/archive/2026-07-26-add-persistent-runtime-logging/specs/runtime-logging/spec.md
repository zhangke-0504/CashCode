## ADDED Requirements

### Requirement: Persistent runtime log storage
The server SHALL create its runtime log directory before accepting traffic and SHALL append UTF-8 log records to `server/logs/cashcode.log` by default, independent of the process working directory. The server MAY use a different directory only when an explicit logging-directory configuration is provided.

#### Scenario: First startup creates runtime storage
- **WHEN** the server starts and the configured runtime log directory does not exist
- **THEN** it creates the directory and writes startup records to `cashcode.log`

#### Scenario: Restart appends to the active log
- **WHEN** the server restarts during the same calendar day
- **THEN** it appends new records to the existing active `cashcode.log` without truncating earlier records

#### Scenario: Runtime log storage is unavailable
- **WHEN** the configured runtime log directory or active file cannot be created or opened
- **THEN** startup emits a clear diagnostic to standard error and fails instead of silently running without durable logs

### Requirement: Daily rotation and ten-day retention
The server SHALL rotate the active runtime log on the first record after local midnight and SHALL retain no more than the active calendar day plus the preceding nine calendar days. Retention cleanup SHALL run at startup as well as during rotation so that expired archives do not survive indefinitely after downtime.

#### Scenario: Midnight rotation
- **WHEN** a record is emitted after the local calendar date changes
- **THEN** the previous active file is archived with a date suffix and subsequent records are appended to a new active file

#### Scenario: Expired archive cleanup
- **WHEN** logging initializes or rotates and recognized archives older than the ten-day window exist
- **THEN** those expired archives are deleted while unrelated files are left unchanged

### Requirement: Runtime and test log isolation
Application runtime records SHALL be written only beneath `server/logs`. Repository-provided server pytest and AI-tool workflows that persist server test output SHALL write it only beneath `server/pytest_logs`. Frontend development, Vite, E2E, and AI-tool workflows that persist client process output SHALL write it only beneath `client/logs`. Generated files in all three directories SHALL remain excluded from Git tracking, and runtime retention SHALL NOT delete server or client test logs.

#### Scenario: Application emits a runtime record
- **WHEN** any server component emits a configured application or Uvicorn record
- **THEN** the record is eligible for the active file beneath `server/logs` and no file is created beneath `server/pytest_logs`

#### Scenario: Test tooling persists command output
- **WHEN** a repository test workflow or AI tool chooses to save pytest output
- **THEN** it stores that output beneath `server/pytest_logs` rather than the repository root, `client`, or another location under `server`

#### Scenario: Frontend tooling persists process output
- **WHEN** frontend development, Vite, E2E, or an AI tool chooses to save client process output
- **THEN** it stores that output beneath `client/logs` rather than directly beneath `client` or elsewhere in the repository

#### Scenario: Browser emits a console error
- **WHEN** browser-side code emits a console error without a separate client-error reporting capability
- **THEN** the error remains in browser developer tools and is not automatically uploaded into backend runtime logs or `client/logs`

### Requirement: Console and file logging policy
The server SHALL use one centralized logging configuration for application and Uvicorn records. By default the console SHALL receive INFO and higher records, the runtime file SHALL receive DEBUG and higher records, and supported environment settings SHALL allow each threshold to be changed without code edits. Verbose third-party protocol libraries SHALL remain at a safe non-debug default unless explicitly enabled.

#### Scenario: Default logging thresholds
- **WHEN** the server starts without log-level overrides
- **THEN** DEBUG application records are available in the runtime file but are not printed to the console

#### Scenario: Uvicorn lifecycle failure
- **WHEN** Uvicorn emits a startup, shutdown, or server error
- **THEN** that record passes through the centralized console and runtime file handlers

### Requirement: Correlated operation logging
The server SHALL attach stable correlation identifiers to log records where they are meaningful. HTTP summaries SHALL include a request identifier returned in the response, WebSocket activity SHALL include client and chat identifiers, and Agent work SHALL include chat and turn identifiers without changing the existing client stream identifier contract.

#### Scenario: HTTP request completes
- **WHEN** an HTTP request completes successfully or with an HTTP error
- **THEN** one canonical summary records method, route, status, duration, and request ID and the response exposes that request ID

#### Scenario: Agent turn executes
- **WHEN** an inbound chat message starts an Agent turn
- **THEN** turn, LLM, and tool boundary records for that work share the same chat ID and stable turn ID

### Requirement: Major runtime boundary events
The server SHALL emit structured key-value events for service lifecycle, HTTP completion, WebSocket connection and accepted message metadata, Agent turn lifecycle, each LLM call, each tool execution, MCP connection and calls, persistence operations, and Dream, Consolidator, and Skill Evolution background work. Completion events SHALL include safe status, duration, and relevant counts when available, while failures SHALL include an error type.

#### Scenario: Successful LLM and tool sequence
- **WHEN** an Agent turn completes one or more LLM iterations and tool calls
- **THEN** logs identify the provider, model, iteration and tool names, durations, outcomes, token usage when returned by the provider, and final aggregate counts

#### Scenario: Background task fails
- **WHEN** a scheduled background operation raises an unhandled exception
- **THEN** the failure event identifies the operation and retains a diagnostic stack trace without terminating unrelated logging

### Requirement: Sensitive content protection
Runtime logs SHALL omit message bodies, prompts, model response text, tool parameters and results, request bodies, credentials, authorization headers, cookies, and complete sensitive query strings. A final formatting-time redaction layer SHALL mask common credential patterns in both normal messages and rendered exception text while preserving safe event metadata and stack frames.

#### Scenario: LLM and tool calls are logged
- **WHEN** an LLM request or tool execution is recorded
- **THEN** the record contains only approved metadata and counts and does not contain the prompt, response, tool arguments, or tool result body

#### Scenario: Exception contains credential-shaped data
- **WHEN** an exception message contains a recognized API key, authorization token, cookie, or configured-secret pattern
- **THEN** the persisted and console-rendered record replaces the sensitive value with a redaction marker

### Requirement: Stable readable log format
Each runtime record SHALL include a local timestamp with millisecond precision and timezone offset, severity, logger name, event name or message, and correlation fields with explicit empty defaults. Records SHALL be encoded as UTF-8 and remain searchable as line-oriented text.

#### Scenario: Unicode diagnostic is emitted
- **WHEN** a safe diagnostic contains Chinese or other Unicode text
- **THEN** the runtime file preserves the text as valid UTF-8 together with the standard timestamp, level, logger, and correlation fields
