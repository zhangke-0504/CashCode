## 1. Repository Log Hygiene

- [x] 1.1 Re-inventory workspace `.log` files, move the six known direct `client/*.log` files into `client/logs` without overwriting collisions, and delete the remaining nine root and server artifacts without traversing `.git`, virtual environments, dependency directories, or paths outside the repository.
- [x] 1.2 Reconcile the user's existing `.gitignore` edits so generated contents of `server/logs`, `server/pytest_logs`, and `client/logs` stay ignored while a short tracked README in each directory preserves and documents its ownership.
- [x] 1.3 Confirm `server/requirements.txt` contains one compatible declaration each for pytest and pytest-asyncio, without adding duplicate requirements or a third-party logging dependency.

## 2. Central Logging Infrastructure

- [x] 2.1 Add an idempotent centralized logging module that resolves and creates the configured runtime directory, validates log levels and retention settings, and configures DEBUG file plus INFO console defaults.
- [x] 2.2 Implement the local-time, millisecond key-value formatter, context-local request/chat/turn fields with empty defaults, and formatting-time credential redaction for normal messages and exception text.
- [x] 2.3 Implement append-mode UTF-8 midnight rotation and narrowly scoped startup/rollover cleanup that retains the active day plus the preceding nine days by default.
- [x] 2.4 Replace `main.py` console-only `basicConfig` setup with the centralized configuration, route Uvicorn lifecycle/error records through it, disable duplicate raw access records, and emit safe resolved logging configuration at startup.

## 3. Request And Turn Correlation

- [x] 3.1 Add FastAPI middleware that binds a bounded request ID, returns `X-Request-ID`, and emits one safe method/route/status/duration summary for successful, HTTP-error, and unhandled-error responses.
- [x] 3.2 Bind and clear WebSocket client/chat context around connections and accepted frames, logging lifecycle, validation rejection, message type, and content length without logging frame content.
- [x] 3.3 Generate and bind a stable UUID turn ID for each Agent turn, preserve the existing stream ID protocol, and add safe start, cancellation, failure, and completion events.

## 4. Runtime Boundary Coverage

- [x] 4.1 Instrument every Agent LLM request with provider, model, generation, iteration, duration, outcome, finish reason, and available token counts without logging messages or response text.
- [x] 4.2 Instrument the shared tool registry so every built-in and deferred tool execution records tool name, duration, outcome, error type, and result length without arguments or result bodies.
- [x] 4.3 Complete MCP lifecycle and call logging with connection/discovery/call/timeout/close durations and sanitized error metadata, including stdio child-process failure handling where the MCP transport exposes it.
- [x] 4.4 Add safe lifecycle and failure events to LLM settings/runtime, session persistence, Skill catalog/store/management, and other currently silent service boundaries without duplicating lower-level events.
- [x] 4.5 Add consistent start, skip, completion, duration, and exception events for Dream, Consolidator, and Skill Evolution background work.

## 5. Automated Verification

- [x] 5.1 Add focused tests for first-start directory creation, same-day append behavior, handler idempotency, default/overridden levels, UTF-8 output, and fatal initialization when the target is unwritable.
- [x] 5.2 Add deterministic tests for midnight archive naming, startup cleanup, rollover cleanup, exact ten-calendar-day retention, and preservation of unrelated files, `server/pytest_logs`, and `client/logs`.
- [x] 5.3 Add formatter tests proving correlation defaults/binding and redaction of credential sentinels in both normal records and rendered exception traces.
- [x] 5.4 Add HTTP middleware and Uvicorn integration tests for request IDs, route-based summaries, status/duration fields, exception handling, and absence of duplicate access records.
- [x] 5.5 Add Agent/LLM/tool/MCP/background instrumentation tests that assert required safe metadata and verify prompts, messages, request bodies, tool arguments, and tool results never appear in captured logs.

## 6. AuWork Environment And Operational Validation

- [x] 6.1 Record relevant package versions, then synchronize the Miniconda `AuWork` environment with `conda run -n AuWork python -m pip install --upgrade -r server/requirements.txt` rather than running `conda update --all`.
- [x] 6.2 Verify AuWork uses Python 3.11 and a pytest version satisfying `>=8.3.0,<9.0.0`, and confirm the server's direct runtime and test dependencies import from that environment.
- [x] 6.3 Run focused logging tests and the complete server suite with `conda run -n AuWork python -m pytest`, placing any persisted command output only beneath `server/pytest_logs`.
- [x] 6.4 Start the backend through AuWork and smoke-test HTTP, WebSocket, Agent failure/success where locally available, shutdown, restart append, and controlled retention behavior in `server/logs`.
- [x] 6.5 Scan generated runtime logs for credential sentinels and user payloads, confirm no new `.log` files exist outside the three designated directories, and document logging settings plus AuWork and frontend log-output commands in the Chinese and English READMEs.
