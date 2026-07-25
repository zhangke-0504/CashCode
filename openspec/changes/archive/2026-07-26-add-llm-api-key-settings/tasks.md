## 1. LLM Settings Domain and Storage

- [x] 1.1 Replace active-provider/model settings with version 2 credential-only profiles, preserve version 1 endpoints and API keys on load, and add redacted migration tests.
- [x] 1.2 Implement an injectable cross-platform user configuration path resolver with an out-of-worktree default and a documented project-local fallback.
- [x] 1.3 Implement `LLMSettingsStore` reads and owner-restricted same-directory atomic writes so invalid or failed first saves create no settings file and failed updates preserve the prior file.
- [x] 1.4 Update one-time `DEEPSEEK_*` migration to persist only credentials and endpoint data while leaving `.env` unchanged and non-authoritative after migration.
- [x] 1.5 Cover missing, invalid, corrupted, atomic replacement, and permission behavior without asserting or printing plaintext keys.
- [x] 1.6 Keep the project-local fallback ignored and verify the default settings path remains outside the Git worktree.

## 2. Selected-Model LLM Runtime

- [x] 2.1 Refactor `LLMRuntime` to maintain client generations per configured provider and acquire immutable snapshots with explicit `{provider, model}` selection.
- [x] 2.2 Refactor `SimpleAgentRunner` to use the selected snapshot for the complete ReAct loop and final fallback call.
- [x] 2.3 Pass turn selections into consolidation and Skill Evolution, retain the last successful runtime selection for Dream, and skip background work when no valid selection exists.
- [x] 2.4 Refactor `SimpleAgentLoop` and startup wiring to install credential generations, validate message selections, and remain usable without configured providers.
- [x] 2.5 Add runtime and Agent tests for provider-specific generations, between-turn model switches, in-flight credential replacement, invalid selection recovery, and background selection propagation.

## 3. Settings Service, Discovery API, and Browser Security

- [x] 3.1 Update the settings service to save independent connection profiles, retain or clear write-only keys, and install runtime provider generations only after atomic persistence.
- [x] 3.2 Remove active-provider/model fields from masked settings APIs and add bounded `GET /api/settings/llm/models` responses with provider-scoped models and partial errors.
- [x] 3.3 Change draft connection testing to list models without requiring a model selection while retaining timeout, sanitization, and no-persistence behavior.
- [x] 3.4 Keep Ollama URL normalization to its OpenAI-compatible `/v1` endpoint with a non-secret placeholder key.
- [x] 3.5 Apply the trusted-origin policy to model discovery as well as settings mutation and connection testing.
- [x] 3.6 Update API/service tests for credential-only payloads, version migration, partial discovery, retained/cleared keys, failed writes, non-persisting tests, and origin enforcement.

## 4. Credential-Only LLM Settings Frontend

- [x] 4.1 Update client settings types and API wrappers for credential-only profiles, readiness, connection-test model counts, and model discovery.
- [x] 4.2 Remove active-provider and model controls from `LLM 设置`, keeping `通用 API` and `Ollama` as draft-preserving connection-editing sections.
- [x] 4.3 Preserve API-key UX that never prefills a stored secret, retains blank input, confirms clearing, and removes plaintext from React state after save.
- [x] 4.4 Update validation and independent test/save states so settings require only connection fields and successful tests report discovered models.
- [x] 4.5 Keep the bottom-pinned gear `设置` control and upward `LLM 设置` menu with desktop and mobile dismissal behavior.
- [x] 4.6 Update focused settings tests for credential-only request construction, retained/cleared keys, draft preservation, and view routing.

## 5. Composer Model Selection and Message Routing

- [x] 5.1 Load and group discovered models by provider, retain the last valid client-side selection, and clear it when refreshed results no longer contain it.
- [x] 5.2 Add a stable responsive model dropdown immediately left of the Composer send/stop icon with loading, empty, partial-error, refresh, and accessible states.
- [x] 5.3 Include selected `{provider, model}` metadata in every outgoing chat frame and preserve the draft when no valid model is selected.
- [x] 5.4 Validate selected-model metadata at WebSocket ingress and route it through `InboundMessage` to the complete Agent turn.
- [ ] 5.5 Add client and server tests for dropdown placement/state, switching between API and Ollama models, malformed selections, and turn routing.

## 6. Documentation and Verification

- [x] 6.1 Update README guidance so settings configure credentials/endpoints, models are selected in the Composer, `.env` is optional for non-LLM overrides, and legacy migration/security paths remain documented.
- [x] 6.2 Run the full server pytest suite and client test, lint, and production build; resolve regressions without weakening security assertions.
- [x] 6.3 Exercise first-run API-key and Ollama flows plus model discovery/switching in the running application across desktop and mobile viewports.
- [x] 6.4 Verify settings/model API responses and logs contain no plaintext key, the default file is outside the repository, the fallback is ignored, and no secret file appears in Git state.

## 7. Ollama Turn Completion and Auxiliary Memory Resilience

- [x] 7.1 Restore the `40_000` production consolidation threshold and move captured-boundary consolidation into Agent-owned background tasks so `_turn_done` and later same-chat turns never wait for its model call.
- [x] 7.2 Add bounded Dream/consolidation operation timeouts, atomic failure behavior, concise logging for expected provider failures, diagnostic logging for unexpected failures, and clean auxiliary-task shutdown.
- [x] 7.3 Build loopback Ollama runtime clients without ambient proxy inheritance while preserving standard transport behavior for remote provider endpoints.
- [x] 7.4 Replace the client's global navigation-reset streaming state with per-chat generation tracking and route terminal/error events to their originating chat.
- [x] 7.5 Add backend and frontend regression tests for slow or failed consolidation, Dream timeout/cursor retry, production thresholds, loopback proxy isolation, and session switching during generation.
- [x] 7.6 Run strict OpenSpec validation plus the full server test suite and client test, lint, and production build without weakening secret-safety coverage.
