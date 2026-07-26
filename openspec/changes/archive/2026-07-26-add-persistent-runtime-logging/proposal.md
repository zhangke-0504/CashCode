## Why

CashCode currently emits only partial console logs, so failures across HTTP, WebSocket, Agent, LLM, tool, MCP, and background-task boundaries cannot be reconstructed after the process exits. Ad hoc test and development output has also accumulated as `.log` files throughout the repository, obscuring the distinction between application telemetry and disposable test artifacts.

## What Changes

- Add a unified server logging capability that writes append-only UTF-8 logs to `server/logs`, while retaining concise console output.
- Rotate runtime logs at local midnight and retain at most ten calendar days, including the active day.
- Correlate HTTP requests and Agent activity with stable request, chat, and turn identifiers, and add event logs at the major HTTP, WebSocket, Agent, LLM, tool, MCP, persistence, and background-task boundaries.
- Redact or omit secrets and user-controlled content by default while preserving exception types, safe metadata, durations, counts, and stack traces needed for diagnosis.
- Reserve `server/pytest_logs` exclusively for persisted server pytest and AI-tool test output, and reserve `client/logs` for persisted frontend development, Vite, and E2E process output; runtime application logging must never write to either test-output directory.
- Move the six existing `client/*.log` files into `client/logs`, remove the remaining scattered root and server `.log` artifacts, and ensure future generated logs remain ignored by Git.
- Standardize local Python verification on the existing Miniconda `AuWork` environment, synchronizing it from `server/requirements.txt`; keep the existing compatible pytest declarations rather than adding duplicates.
- Exclude browser-console collection and Vite process-log ingestion into the backend from this change. Persisted Vite and frontend test process output remains local under `client/logs`; browser failures remain visible in developer tools unless a separate client-error reporting capability is proposed later.

## Capabilities

### New Capabilities

- `runtime-logging`: Durable, correlated, privacy-conscious server runtime logging with daily retention and strict separation among backend runtime, server test, and frontend process-log output.

### Modified Capabilities

None.

## Impact

- Server startup and Uvicorn logging configuration in `server/main.py` and a new centralized logging module.
- FastAPI middleware plus logging at WebSocket, Agent runner/loop, tool registry, MCP, memory, LLM, Skill, and background-service boundaries.
- Runtime directories and ignore policy for `server/logs`, `server/pytest_logs`, and `client/logs`, plus migration or removal of legacy scattered `.log` files.
- Server tests, pytest execution conventions, documentation, and the local out-of-repository Miniconda `AuWork` environment.
- No new runtime logging dependency is expected; Python's standard `logging` and `logging.handlers` modules are sufficient for the current single-process backend.
