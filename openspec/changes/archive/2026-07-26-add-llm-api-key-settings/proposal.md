## Why

CashCode currently requires DeepSeek credentials from `server/.env` while constructing the Agent, so a missing key prevents the backend from starting and there is no in-app path for first-time configuration. CashCode needs a local-first LLM settings flow that safely stores OpenAI-compatible API credentials and Ollama endpoints, while model choice remains part of the chat workflow rather than a global setting.

## What Changes

- Add persistent credential-only profiles for an OpenAI-compatible API and Ollama; settings do not select an active provider or model.
- Store the API key in a user-local settings file outside the Git worktree by default, create that file atomically on the first successful configuration, and never return the plaintext key through the API.
- Start the backend in an unconfigured state when no LLM settings exist so the settings API and frontend remain available.
- Migrate legacy `DEEPSEEK_*` credentials once when the new settings file is absent; after migration, the settings file is authoritative and normal LLM operation no longer depends on `.env`.
- Discover models from every configured and reachable provider and expose them to a model dropdown immediately left of the Composer send/stop button.
- Send the selected `{provider, model}` with each chat message and pin that selection for the complete Agent turn and its turn-triggered background work.
- Publish each chat turn's terminal state as soon as its final response is persisted, then run consolidation as managed auxiliary work so slow or failed memory maintenance cannot leave the Composer stuck; keep generation state scoped to its chat when users switch views.
- Restore the production consolidation threshold, bound Dream and consolidation model calls, preserve memory and cursors on auxiliary failures, and log expected provider timeouts without full tracebacks.
- Keep loopback Ollama traffic independent of ambient HTTP proxy settings so local inference cannot be delayed or broken by a system proxy.
- Add a bottom-pinned `设置` gear control in the sidebar with an upward menu containing `LLM 设置`, and render a dedicated settings view for editing, testing, clearing, and saving connection configuration.
- Restrict browser origins allowed to mutate local settings and ensure default or redirected local secret paths are excluded from Git tracking.

## Capabilities

### New Capabilities
- `llm-configuration`: Credential-only provider profiles, secure local persistence, legacy migration, masked management APIs, connection testing, model discovery, and selected-model runtime snapshots.
- `llm-settings-view`: The LLM connection settings page and chat Composer model selector, including validation, loading, unavailable, and recovery states.

### Modified Capabilities
- `sidebar-session-list`: Add the bottom settings trigger and upward `LLM 设置` navigation menu while preserving session behavior.
- `agent-turn-runtime`: Permit an unconfigured backend, accept a model selection with each chat message, and pin that selection for a complete Agent turn.

## Impact

- Server startup, WebSocket message validation, and Agent dependency wiring in `server/main.py` and `server/app/agent/`.
- Dream, consolidation, and Skill Evolution model selection and LLM client ownership.
- Turn completion ordering, per-chat generation state, auxiliary task lifecycle, timeout/error handling, and local Ollama transport behavior.
- Settings domain/store/service and `/api/settings/llm` plus model-discovery endpoints.
- Cross-platform user configuration path resolution, atomic secret persistence, and Git ignore documentation.
- CORS/origin policy for the local REST API.
- Client settings view, Composer controls, WebSocket payloads, API wrappers, and types.
- Backend and frontend tests for persistence, migration, masking, model discovery, per-turn routing, first-run behavior, UI/API state handling, slow consolidation, Dream timeouts, session switching, and proxy isolation.
