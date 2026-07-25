## Context

The first implementation of this change stores one active provider and model in `llm.json`, installs one active runtime client, and exposes provider/model activation in the settings page. The revised product contract makes LLM settings credential-only: users configure how CashCode reaches OpenAI-compatible and Ollama services, then choose a model beside the chat send control for each turn.

The change must preserve the existing local-secret protections, support already-created version 1 settings files, make model discovery resilient when one provider is offline, and avoid changing model or credentials halfway through a multi-call turn.

Ollama exposed two runtime assumptions that are not acceptable for a local-first chat workflow. Consolidation currently runs synchronously before `_turn_done`, so a slow summary call leaves the Composer in a generating state even after the final answer is visible. Periodic Dream failures are isolated from the process, but expected provider timeouts currently emit full tracebacks, and loopback Ollama traffic can inherit ambient proxy settings. The client also stores one global streaming flag and clears it when switching sessions, which fabricates completion instead of reflecting the selected chat's real state.

## Goals / Non-Goals

**Goals:**
- Retain one OpenAI-compatible credential profile and one Ollama endpoint profile without a global active provider or stored settings model.
- Make the backend and settings UI usable before any provider is configured.
- Keep the protected settings file outside the repository, create it only after a valid save or migration, and write it atomically.
- Remove ongoing LLM dependence on `.env` while preserving one-time DeepSeek migration.
- Discover available models from configured providers and select one in the Composer immediately left of send/stop.
- Carry `{provider, model}` on every chat message and pin a consistent client generation for the complete turn.
- Publish a terminal chat event independently of non-critical memory maintenance and keep later turns processable while consolidation runs.
- Bound and isolate Dream and consolidation failures without advancing memory state, leaking secrets, or flooding logs for expected timeouts.
- Keep loopback Ollama requests direct and represent generation state independently for each chat.
- Prevent stored keys from being returned, logged, committed, or mutated by arbitrary browser origins.

**Non-Goals:**
- Managing arbitrary named provider profiles or vendor presets.
- Selecting models from the LLM settings page.
- Configuring temperature, token limits, embeddings, or per-model advanced options.
- Synchronizing credentials or selected models between machines.
- Removing optional environment variables used for ports, workspace paths, or other non-LLM server operations.
- Guaranteeing that Dream or consolidation succeeds while the selected provider is unavailable or too slow.
- Treating navigation between chats or settings views as a request to cancel generation.

## Decisions

### 1. Persist a version 2 credential-only document

Persist `version: 2` with `openai_compatible` and `ollama` objects. The OpenAI-compatible profile stores `base_url` and `api_key`; the Ollama profile stores its user-facing server URL. Neither profile stores a model and the document has no `active_provider`.

A profile is independently ready when its required connection fields are complete. Saving one profile does not require the other to be ready. An existing version 1 document is loaded by preserving its endpoints and API key while ignoring its active-provider and model fields, then is rewritten as version 2 on the next successful save. This avoids losing credentials while removing the obsolete global selection contract.

### 2. Keep secrets in the operating-system user configuration area

The default remains `%LOCALAPPDATA%/CashCode/settings/llm.json` on Windows, `~/Library/Application Support/CashCode/settings/llm.json` on macOS, and `$XDG_CONFIG_HOME/cashcode/settings/llm.json` or `~/.config/cashcode/settings/llm.json` elsewhere. Tests and managed deployments may inject a configuration root. The documented project-local fallback remains explicitly ignored by Git.

An optional environment override does not make `.env` mandatory. After migration, `.env` is not consulted for normal LLM configuration; non-LLM runtime variables remain supported.

### 3. Preserve atomic, write-only secret semantics

`LLMSettingsStore` validates and normalizes a candidate before creating the parent directory, writes a same-directory temporary file, flushes it, applies owner-only permissions where supported, and atomically replaces the destination. Invalid first saves create no file and failed updates preserve the old file.

The API key remains plaintext on the trusted local device because it must be sent to the configured provider. It is mitigated through the out-of-worktree location, restrictive permissions, redacted errors/logging, and an API that reports only `api_key_configured`.

### 4. Keep legacy migration one-time and non-destructive

When no settings file exists, a non-empty `DEEPSEEK_API_KEY` migrates with `DEEPSEEK_API_BASE` or its legacy default into the OpenAI-compatible profile. `DEEPSEEK_MODEL` is not persisted because model choice now belongs to the Composer. Migration never deletes or edits `.env`; once `llm.json` exists, legacy variables no longer override it.

### 5. Discover models independently for each configured provider

Add `GET /api/settings/llm/models`. The service queries each ready provider with a bounded timeout and returns provider-scoped model records using stable `{provider, id}` identities. A failure from one provider is represented as a sanitized provider error and does not hide models returned by the other provider. No credential or reversible secret hint is included.

Both providers use their OpenAI-compatible `/v1/models` surface through the existing OpenAI client. Ollama server origins continue to normalize internally to `/v1` while responses and settings retain the user-entered server URL.

The draft connection test no longer asks for a model. It performs a bounded model-list request with the submitted endpoint and submitted-or-retained key. A successful response confirms connectivity and may report the number of discovered models without persisting the draft.

### 6. Maintain provider client generations and acquire by selection

`LLMRuntime` owns immutable client generations per ready provider. Saving credentials installs a new generation for each changed ready provider and retires replaced clients only after their outstanding leases release. Removing or making a profile incomplete prevents new leases for that provider without interrupting existing leases.

Callers acquire a snapshot explicitly:

```text
async with runtime.acquire(provider, model) as snapshot:
    # every call in this operation uses snapshot.client and snapshot.model
```

The model is supplied by the incoming selection, while the client comes from the selected provider generation. The Agent Runner holds one lease for the full ReAct loop and final fallback. Consolidation and Skill Evolution triggered by that turn receive the same selection. The runtime remembers the last successfully acquired selection in memory for periodic Dream; Dream skips until a valid selection has been used after startup and never creates a persistent global model setting.

### 7. Send model identity with every chat message

The Composer loads the model catalog after connection and after settings changes. Options are grouped by provider and carry both provider and model id, so identical model names on different endpoints remain distinct. The last valid selection may be retained in client-local preference state; when it disappears, the Composer clears it and requires the user to choose again rather than silently routing to another provider.

Outgoing message metadata includes `llm: {provider, model}`. WebSocket ingress treats both fields as untrusted bounded strings and rejects missing, malformed, or unconfigured provider selections before the user turn is persisted or tools execute. Provider errors such as a model removed after discovery remain sanitized and recoverable.

### 8. Keep settings and model selection in separate UI surfaces

The sidebar's bottom gear and upward `LLM 设置` menu continue to navigate to a dedicated settings view. Its `通用 API` and `Ollama` segments are editing tabs only, not an active-provider selector. Generic API fields are Base URL and API Key; Ollama exposes only Server URL. Test and save retain independent pending/result states, and successful save refetches masked state and clears plaintext input.

The Composer renders a compact model dropdown immediately left of the send/stop icon button. It has loading, empty, partial-provider-error, and refresh behavior, remains usable on mobile, and does not resize the Composer when labels change.

### 9. Retain browser-origin protection

CashCode keeps a configurable browser-origin allowlist containing the documented localhost and `127.0.0.1` Vite origins. Settings PUT/test and model discovery reject a present untrusted `Origin`; requests without `Origin` remain available to local CLI clients.

### 10. End the foreground turn before auxiliary consolidation

The foreground turn boundary is the successful persistence of the final assistant response and session metadata followed by publication of exactly one `_turn_done` event. Consolidation is scheduled only after that durable commit and is not awaited before the terminal event. Skill Evolution remains independently scheduled and follows the same failure-isolation rule.

`SimpleAgentLoop` owns the auxiliary tasks it creates and cancels and awaits them during shutdown. A consolidation job captures an immutable history snapshot and its persistence boundary before leaving the completed turn. The expensive model request runs outside the per-chat turn lock. Its short commit phase coordinates with the chat, validates the captured boundary, and preserves messages appended by later turns. At most one consolidation job runs per chat; an already-running job causes another trigger to be skipped rather than queued without bound.

Publishing `_turn_done` before a synchronous summarization call was considered but rejected: it would make the Composer look available while the same chat lock still prevents the next turn from starting. Running the whole consolidation without a captured boundary was also rejected because a late summary could overwrite newer in-memory history.

The production character threshold is `40_000`. Tests inject a smaller threshold through the consolidator constructor instead of changing the production constant.

### 11. Bound and classify auxiliary LLM failures

Dream phases and consolidation summaries use a dedicated, configurable operation timeout with a finite default and no retry sequence that can extend work beyond that operation budget. A timeout, connection failure, or cancellation before commit leaves the current summary, `MEMORY.md`, consolidation marker, and Dream cursors unchanged so a later turn or Dream cycle can retry.

Provider timeouts and ordinary connection failures are expected operational outcomes. They produce one concise warning containing the operation and exception category, without credentials, prompt content, response content, or a traceback. Unexpected programming and persistence failures retain traceback logging for diagnosis. This keeps the terminal useful while preserving evidence for real defects.

### 12. Bypass ambient proxies for loopback Ollama

Runtime clients are transport-aware. When the configured provider is Ollama and its normalized hostname is loopback (`localhost`, an IPv4 loopback address, or an IPv6 loopback address), its HTTP client disables environment proxy inheritance. Remote Ollama and generic OpenAI-compatible endpoints retain the standard transport behavior so intentional deployment proxies are not silently ignored.

Disabling environment proxies for every provider was rejected because remote OpenAI-compatible services may legitimately require them. Relying only on the machine's `NO_PROXY` value was rejected because CashCode's default local Ollama path must work without external shell configuration.

### 13. Track generation state by chat

The client stores generation state keyed by `chat_id`; the active Composer derives its disabled/send-stop state from the active chat entry. Sending marks only that chat active, and terminal, error, or explicit cancellation events clear only the matching chat. Navigating to another chat or the settings view does not mutate generation state.

This preserves inactive-chat events: a terminal frame received while viewing another chat updates that chat, and returning to it shows the true final state. A single global boolean was rejected because navigation currently clears it and makes a still-running turn appear complete.

## Risks / Trade-offs

- [The settings file contains a plaintext reusable key] -> Keep it outside the worktree, restrict permissions, never return it, and document local-device trust.
- [One provider is offline during discovery] -> Return provider-scoped errors alongside models from healthy providers.
- [A model disappears after discovery] -> Surface a sanitized turn error and refresh the dropdown; never silently substitute a model.
- [A credentials save occurs during a turn] -> Hold a provider-generation lease until the complete turn releases it.
- [Periodic Dream has no Composer event after restart] -> Skip it until a valid model has been selected by a chat turn.
- [Generic OpenAI-compatible servers vary in tool support] -> Discovery tests only model listing; normal turn errors continue to report unsupported behavior.
- [A background consolidation finishes after newer turns] -> Capture its history boundary before scheduling, serialize only its commit, and preserve newer persisted and in-memory messages.
- [Auxiliary work accumulates or survives shutdown] -> Allow at most one consolidation task per chat and keep all auxiliary tasks in an owned lifecycle set that is cancelled and awaited.
- [A slow local model exceeds the auxiliary timeout] -> Leave memory state unchanged, log a concise warning, and retry from the same cursor on a later trigger.
- [A user intentionally proxies a loopback endpoint] -> Prefer deterministic direct loopback behavior; remote endpoints continue to honor ambient proxies.

## Migration Plan

1. Update settings models/store/service to version 2 credential-only profiles and add version 1 compatibility tests.
2. Change runtime acquisition to explicit provider/model selection and thread selections through Agent, consolidation, Evolution, and Dream behavior.
3. Add the model-discovery API and remove model requirements from settings/test payloads.
4. Remove model and active-provider controls from LLM settings; add the Composer dropdown and WebSocket metadata.
5. Move consolidation behind the terminal turn event with captured-boundary commits, restore the production threshold, and add bounded auxiliary failure handling.
6. Add loopback-aware Ollama transport creation and per-chat client generation state.
7. Update tests and README, then verify first-run, API-key, Ollama, provider failure, model switching, reload, slow consolidation, Dream timeout, session switching, desktop, and mobile flows.

Rollback can restore the prior server version because migration leaves `.env` untouched. A version 2 settings file contains the same connection secrets but not the former active/model fields; rollback may require reselecting those values in the prior UI.

## Open Questions

None.
