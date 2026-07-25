# LLM Settings View Specification

## Purpose
Define the credential-only LLM settings experience and per-message model selection behavior in the client.

## Requirements

### Requirement: Display a dedicated credential-only LLM settings view
The client SHALL render a dedicated `LLM 设置` view that loads authoritative server settings and separates OpenAI-compatible and Ollama connection fields into clear full-width form sections. The view SHALL NOT select an active provider or model.

#### Scenario: Configured settings load
- **WHEN** the user navigates to `LLM 设置` and the settings request succeeds
- **THEN** the view displays both retained connection profiles, their readiness, and whether an API key is configured without displaying a selected model

#### Scenario: First-run settings load
- **WHEN** the server reports that no provider is ready
- **THEN** the view presents editable connection fields and no fabricated stored key or model selection

#### Scenario: Settings request fails
- **WHEN** the settings request cannot be completed
- **THEN** the view displays an actionable retry state without replacing the form with misleading defaults

### Requirement: Edit separate provider connections
The view SHALL use an editing control for `通用 API` and `Ollama`, SHALL preserve draft edits while switching sections, and SHALL expose only connection fields for the selected section.

#### Scenario: User edits generic API configuration
- **WHEN** the user activates the `通用 API` section
- **THEN** the view exposes API Base URL and password-style API-key controls without a model field

#### Scenario: User edits Ollama configuration
- **WHEN** the user activates the `Ollama` section
- **THEN** the view exposes only the Ollama server URL and does not require an API key or model

### Requirement: Handle stored API keys without exposing them
The API-key input SHALL remain empty when a stored key exists, SHALL indicate that leaving it blank retains the stored value, SHALL allow visibility toggling only for newly typed text, and SHALL provide an explicit clear action with confirmation.

#### Scenario: Existing key is loaded
- **WHEN** the server reports `api_key_configured=true`
- **THEN** the input contains no secret value and communicates that a blank submission retains the current key

#### Scenario: User enters a replacement key
- **WHEN** the user types a new API key and saves valid settings
- **THEN** the new value is sent as write-only input and removed from client state after masked settings reload

#### Scenario: User requests key removal
- **WHEN** the user activates the clear command and confirms it
- **THEN** the next update explicitly requests removal rather than treating an accidentally blank field as deletion

### Requirement: Validate, test, and save connection settings
The view SHALL validate required connection fields before submission, provide separate `测试连接` and `保存设置` commands with stable pending states, and present sanitized errors without discarding unsaved input.

#### Scenario: Required connection field is missing
- **WHEN** the user attempts to test or save the displayed provider without its required URL or effective API key
- **THEN** the view identifies the affected field and does not send an invalid request

#### Scenario: Connection test completes
- **WHEN** the user tests syntactically valid draft connection fields
- **THEN** the view reports success with discovered-model count or a sanitized failure and retains draft values without marking them saved

#### Scenario: Settings save succeeds
- **WHEN** the user saves a valid connection profile
- **THEN** the view reloads masked authoritative settings, clears plaintext key state, and confirms the connection was saved without activating a model

#### Scenario: Settings save fails
- **WHEN** the server rejects or cannot persist the update
- **THEN** the view displays the error, re-enables commands, and preserves the draft for correction

### Requirement: Select the chat model beside the send control
The Composer SHALL render a model dropdown immediately left of the send/stop icon button and SHALL populate it with provider-scoped models returned by discovery.

#### Scenario: Models are available
- **WHEN** at least one configured provider returns models
- **THEN** the dropdown groups models by provider and each option retains a stable `{provider, model}` identity

#### Scenario: User switches model
- **WHEN** the user chooses another model before sending a message
- **THEN** the pending message uses that selection without changing LLM connection settings

#### Scenario: Selected model becomes unavailable
- **WHEN** refreshed discovery no longer contains the selected identity
- **THEN** the Composer clears the invalid selection and requires a new choice instead of silently switching providers or models

#### Scenario: No models are available
- **WHEN** no provider is configured or all configured providers fail discovery
- **THEN** the dropdown shows an unavailable state, message sending is blocked, and the user can navigate to `LLM 设置`

#### Scenario: Composer is displayed on mobile
- **WHEN** the chat view uses a narrow viewport
- **THEN** the model dropdown remains immediately left of the send/stop control without overlapping text, capability chips, or action buttons

### Requirement: Track generation state independently for each chat
The client SHALL associate generation state with the originating `chat_id`. The active Composer SHALL derive its send/stop state from the active chat, and navigation SHALL NOT mark a running chat as complete.

#### Scenario: User switches away from a generating chat
- **WHEN** one chat is generating and the user opens another chat or the LLM settings view
- **THEN** the original chat remains marked as generating and the newly active chat reflects only its own generation state

#### Scenario: User returns before the terminal event
- **WHEN** the user returns to a generating chat before its terminal, error, or explicit cancellation event arrives
- **THEN** the Composer still displays the stop state and does not allow a duplicate turn to be sent

#### Scenario: Inactive chat receives its terminal event
- **WHEN** `_turn_done` arrives for a chat that is not currently active
- **THEN** only that chat's generation state is cleared and another chat's Composer state is unchanged

#### Scenario: Chat generation fails
- **WHEN** an error event identifies a generating chat
- **THEN** only that chat is returned to an input-ready state while its error remains available through the existing error UI
