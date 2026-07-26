## Context

CashCode is currently a single-process FastAPI/Uvicorn backend with a separate WebSocket server and asynchronous Agent, Dream, Consolidator, Skill Evolution, LLM, tool, and MCP activity. `server/main.py` calls `logging.basicConfig` with a console-only INFO handler, and only a subset of modules emit records. HTTP middleware is absent, LLM and general tool boundaries are not timed, and Uvicorn can apply its own logging configuration.

The repository currently contains 15 ignored `.log` files scattered across its root, `client`, and `server`, including six frontend process logs directly beneath `client`. `server/requirements.txt` already declares compatible `pytest` and `pytest-asyncio` ranges. The local Miniconda `AuWork` environment runs Python 3.11.15 but currently has pytest 9.1.1, which violates the repository's `pytest>=8.3.0,<9.0.0` constraint. `.gitignore` has existing uncommitted user edits, including `/server/pytest_logs/`; implementation must preserve those edits and reconcile them with the directory-documentation approach.

## Goals / Non-Goals

**Goals:**

- Produce durable, detailed, correlated runtime diagnostics without logging user content or credentials.
- Keep application logs in `server/logs`, persisted server test/AI-tool output in `server/pytest_logs`, and persisted frontend process output in `client/logs`.
- Rotate by local calendar day and enforce a strict ten-calendar-day runtime retention window.
- Use the standard library and the existing single-process architecture.
- Make the repository requirements the source of truth for the AuWork verification environment.

**Non-Goals:**

- Upload browser errors or Vite process output to the backend; locally persisted Vite output belongs in `client/logs`.
- Persist prompts, completions, request bodies, tool arguments, or tool results for replay.
- Add remote aggregation, metrics, tracing backends, or a log-viewing UI.
- Support multiple backend processes writing and rotating the same file.
- Run an unconstrained `conda update --all` against the shared AuWork environment.

## Decisions

### 1. Configure logging once before application modules initialize

Add a small centralized server logging module and invoke it from `server/main.py` after `.env` is loaded but before application modules are imported. Use `logging.config.dictConfig` or equivalent explicit setup rather than extending `basicConfig`. Configuration must be idempotent so imports and tests cannot multiply handlers.

The root logger will accept DEBUG records. A console handler defaults to INFO and a UTF-8 file handler defaults to DEBUG. `uvicorn.error` will use the same handlers. Uvicorn's raw access handler will be disabled in favor of one richer FastAPI middleware summary, avoiding duplicate HTTP records. Noisy dependency loggers such as `httpcore`, `httpx`, `openai`, and `websockets` will default to WARNING.

Alternative considered: leave Uvicorn's default log configuration and add only a root file handler. This is rejected because Uvicorn logger propagation and formatting would remain inconsistent and access records could bypass or duplicate application handlers.

### 2. Use a standard-library timed rotating handler with explicit startup cleanup

Use `TimedRotatingFileHandler` in append mode with `when="midnight"`, local time, UTF-8 encoding, and nine backups. `server/logs/cashcode.log` is the active file; archives use a date suffix. A narrowly scoped cleanup helper runs during configuration and rotation, deleting only recognized CashCode archives outside the active day plus previous nine days. This closes the standard handler's gap where old files can remain after a long period with no rollover.

`CASHCODE_LOG_DIR`, `CASHCODE_FILE_LOG_LEVEL`, `CASHCODE_CONSOLE_LOG_LEVEL`, and `CASHCODE_LOG_RETENTION_DAYS` provide validated overrides. The default log directory is resolved from the server source path, never from the current working directory. Failure to create or open the active file is fatal after a direct standard-error diagnostic; silently losing the feature would defeat its purpose.

Alternative considered: add a third-party concurrent rotating handler. This is unnecessary for the current one-process Uvicorn deployment and would add dependency and upgrade surface. Multi-process deployment must revisit this decision.

### 3. Use readable key-value records and context-local correlation

Keep line-oriented text rather than JSONL because the current use case is local diagnosis with `rg`, editors, and terminal tools. The format includes local timestamp with milliseconds and offset, level, logger, and fixed `request_id`, `chat_id`, and `turn_id` slots, followed by an event name and stable key-value fields.

Use `contextvars` and a handler filter to supply correlation defaults to every record, including dependency records. FastAPI middleware creates a bounded request ID, returns it in `X-Request-ID`, records route templates instead of raw sensitive URLs, and clears context in `finally`. WebSocket and Agent boundaries bind their existing client/chat IDs plus a new UUID turn ID. The existing numeric `stream_id` remains unchanged for protocol compatibility.

Alternative considered: pass `extra` fields manually at every logging call. This is error-prone for nested LLM, tool, and persistence operations and makes missing formatter fields likely.

### 4. Instrument boundaries, not payloads

Add named events around lifecycle and expensive or failure-prone boundaries:

- `http.request.completed` and `http.request.failed`
- WebSocket connect, disconnect, validation rejection, accepted message length, and routing failures
- Agent turn start, cancel, failure, and completion
- LLM call start/completion/failure with provider, model, generation, duration, finish reason, and usage counts when present
- Tool start/completion/failure with tool name, duration, status, and result length only
- MCP connection, discovery, call, timeout, and close
- Persistence write/read failures and safe count/path-category metadata
- Dream, Consolidator, and Skill Evolution start, skip, completion, and failure

INFO describes lifecycle and completed operations, DEBUG adds safe counts and decision detail, WARNING describes recoverable degradation, and ERROR/exception records preserve stack traces. Health-check noise may be filtered or lowered to DEBUG.

### 5. Redact after formatting as defense in depth

Call sites must whitelist safe fields and never pass bodies, prompts, completions, tool payloads, credentials, headers, or full URLs. A redacting formatter then scans the fully rendered record, including exception text, for common credential-bearing labels and token shapes and replaces values with `[redacted]`. This final-stage placement avoids the usual filter limitation where traceback text is appended after message filtering.

Redaction is not treated as permission to log payloads: pattern matching cannot recognize every secret. Tests will use sentinel credentials across normal messages and exceptions to prevent regressions.

### 6. Represent the three log directories as repository conventions

Track a short README in each directory while ignoring generated contents, so fresh clones preserve all three directory purposes. `server/logs` is owned by the application and its retention mechanism. `server/pytest_logs` is owned by server test runners and AI tools. `client/logs` is owned by frontend development, Vite, E2E, and AI-tool processes. Runtime code must not write to or clean either test-output directory. Documentation and test commands will use timestamped or purpose-named files beneath the appropriate directory whenever output needs to persist.

During migration, move the six inventoried `client/*.log` files into `client/logs` without overwriting an existing destination, and remove the remaining nine root and server `.log` files. Cleanup must exclude `.git`, virtual environments, dependency caches, and user data outside the workspace.

### 7. Synchronize, do not globally update, the AuWork environment

Keep the existing `pytest>=8.3.0,<9.0.0` and `pytest-asyncio>=0.25.0,<1.0.0` declarations; do not add duplicate lines. Synchronize the environment with `conda run -n AuWork python -m pip install --upgrade -r server/requirements.txt`, which upgrades or downgrades packages only within project constraints. Verify pytest resolves to the compatible 8.x range and use `conda run -n AuWork python -m pytest` for server validation instead of `server/.venv`.

Alternative considered: `conda update --all`. It is rejected because AuWork may be shared and a global solver update can alter unrelated packages beyond CashCode's declared compatibility surface.

## Risks / Trade-offs

- [Synchronous file writes briefly block the event-loop thread] -> Keep events metadata-only and low-volume; introduce `QueueHandler` only if profiling shows meaningful latency.
- [Two server instances can race during file rotation] -> Document single-process ownership and revisit with OS-managed or concurrent rotation before enabling workers or multiple instances against one directory.
- [Redaction patterns can miss novel secret formats] -> Prevent payload logging at call sites, clamp verbose third-party loggers, and test representative credential sentinels.
- [Strict logging initialization can prevent startup on a read-only packaged directory] -> Support `CASHCODE_LOG_DIR` and require packaging to point it at a writable application-data location.
- [Detailed boundary coverage can create repetitive records] -> Keep one canonical HTTP summary, use stable event names, and avoid duplicating Uvicorn access logs.
- [AuWork dependency synchronization may change packages used by other work] -> Limit changes to `server/requirements.txt` constraints and record before/after versions during implementation.

## Migration Plan

1. Inventory workspace `.log` artifacts, safely move the six direct client logs into `client/logs`, and remove the remaining nine scattered artifacts outside dependency and VCS directories.
2. Establish tracked documentation for all three directories and reconcile `.gitignore` without overwriting the user's existing edits.
3. Add and test centralized logging, rotation, retention, formatting, redaction, and HTTP correlation in isolation.
4. Integrate Uvicorn and add boundary events incrementally across runtime components.
5. Synchronize AuWork from `server/requirements.txt`, verify compatible versions, and run the focused and full server suites from that environment with any persisted output under `server/pytest_logs`.
6. Start the server from AuWork, verify console/file behavior, force a controlled rollover test, and scan all three allowed directories for secret sentinels and misplaced files.

Rollback removes the centralized configuration and instrumentation while restoring console-only logging. Generated runtime and test logs are ignored artifacts and may be retained for diagnosis or deleted independently. The AuWork environment can be resynchronized from a prior environment export if its package changes must be reversed.

## Open Questions

None for the current single-process, server-side scope. Frontend error ingestion and multi-process file ownership require separate design decisions if they are requested later.
