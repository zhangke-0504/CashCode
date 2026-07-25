# LLM Configuration Specification

## Purpose
Define secure, provider-specific LLM connection configuration, model discovery, and runtime client lifecycle behavior.

## Requirements

### Requirement: Maintain separate credential-only provider profiles
The system SHALL maintain independent `openai_compatible` and `ollama` connection profiles without storing an active provider or selected model. The OpenAI-compatible profile SHALL contain an API base URL and API key; the Ollama profile SHALL contain an Ollama server URL without requiring an API key.

#### Scenario: User configures both providers
- **WHEN** the user saves valid OpenAI-compatible and Ollama connection fields
- **THEN** both profiles are retained and neither is designated as the globally active provider

#### Scenario: User configures only one provider
- **WHEN** one profile is complete and the other is incomplete
- **THEN** the complete profile is available for model discovery without requiring fabricated values for the incomplete profile

### Requirement: Persist LLM settings outside source control
The system SHALL resolve the default LLM settings file to a user-local configuration directory outside the CashCode Git worktree, SHALL allow tests or deployments to inject an explicit configuration directory, and SHALL keep any documented project-local fallback path excluded from Git tracking.

#### Scenario: Default configuration path is resolved
- **WHEN** CashCode starts without an explicit configuration-directory override
- **THEN** the LLM settings path resolves under the current operating-system user's configuration area rather than under the repository

#### Scenario: Project-local fallback is used
- **WHEN** a developer explicitly redirects the configuration directory to the documented `server/data` fallback
- **THEN** the resulting LLM settings file matches an explicit repository ignore rule and is not selected by a normal Git add operation

### Requirement: Create and update the settings file safely
The system SHALL create the parent directory and versioned settings file only after the first valid connection profile is saved or migrated, SHALL write updates atomically in the destination directory, and SHALL restrict file access to the current user where the operating system supports it.

#### Scenario: First valid configuration is saved
- **WHEN** no settings file exists and at least one valid connection profile is submitted
- **THEN** the system creates the directory and settings file atomically without storing an active provider or model

#### Scenario: First configuration is invalid
- **WHEN** no settings file exists and validation fails
- **THEN** the system returns a validation error without creating an empty or partial settings file

#### Scenario: Updating an existing file fails
- **WHEN** writing or replacing an updated settings file fails
- **THEN** the previous file and runtime provider generations remain unchanged

### Requirement: Migrate legacy LLM configuration without retaining model selection
When the new settings file is absent, the system SHALL migrate a non-empty legacy `DEEPSEEK_API_KEY` and its configured or default base URL into the OpenAI-compatible profile. The system SHALL also load an existing version 1 settings file by preserving connection fields while discarding obsolete active-provider and model fields. Once a settings file exists, it SHALL be authoritative over legacy `DEEPSEEK_*` values.

#### Scenario: Legacy DeepSeek configuration exists on first upgraded start
- **WHEN** the settings file is absent and `DEEPSEEK_API_KEY` is non-empty
- **THEN** the system creates a credential-only settings file and continues startup without persisting `DEEPSEEK_MODEL`

#### Scenario: Version 1 settings exist
- **WHEN** CashCode loads a version 1 file containing active-provider and model fields
- **THEN** it preserves endpoints and the API key, ignores the obsolete selection fields, and rewrites version 2 on the next successful save

#### Scenario: Environment changes after migration
- **WHEN** a settings file exists and any `DEEPSEEK_*` value later changes
- **THEN** the persisted credentials remain authoritative and the runtime does not adopt the environment change

### Requirement: Expose masked credential management APIs
The system SHALL expose APIs to read and replace connection profiles and SHALL never return or log a stored plaintext API key. A read response SHALL report provider readiness and whether an API key is configured; an omitted or blank key on update SHALL retain the stored key, while an explicit clear operation SHALL remove it.

#### Scenario: Settings are read after an API key is stored
- **WHEN** a client requests current LLM settings
- **THEN** the response includes profile endpoints, readiness, and `api_key_configured=true` without an API key, active provider, or model

#### Scenario: User edits a non-secret API field
- **WHEN** an update changes the base URL and leaves the API-key input blank without requesting a clear
- **THEN** the system retains the stored key and saves the endpoint change

#### Scenario: User explicitly clears the key
- **WHEN** an update requests API-key removal
- **THEN** the system removes the key, reports the OpenAI-compatible profile as not ready, and leaves an independently valid Ollama profile available

### Requirement: Discover models from every ready provider
The system SHALL provide a bounded model-discovery API that returns provider-scoped model identities from every configured provider and SHALL isolate provider failures.

#### Scenario: Both providers return models
- **WHEN** both configured providers respond successfully
- **THEN** the response contains grouped `{provider, id}` model records for both providers without credential data

#### Scenario: One provider is unavailable
- **WHEN** one provider fails authentication, is unreachable, or times out while the other succeeds
- **THEN** the response contains models from the healthy provider plus a sanitized error for the failed provider

#### Scenario: No provider is ready
- **WHEN** neither provider has complete saved connection fields
- **THEN** the response contains no models and identifies that LLM connection settings are required

### Requirement: Test draft provider configuration without saving it
The system SHALL provide a bounded connection-test operation that lists models using submitted draft connection fields and a submitted or retained key, and SHALL NOT persist, activate, or log the draft configuration.

#### Scenario: Draft connection succeeds
- **WHEN** the provider endpoint authenticates and returns its model list
- **THEN** the API returns a success result and model count while leaving persisted settings and runtime generations unchanged

#### Scenario: Draft connection fails
- **WHEN** the endpoint is unreachable, authentication fails, or the request times out
- **THEN** the API returns a sanitized actionable failure and leaves persisted settings and runtime generations unchanged

### Requirement: Apply an explicitly selected model through operation snapshots
The system SHALL acquire the provider client and model named by a chat message for newly starting Agent turns. Each operation SHALL retain one immutable snapshot for all model calls, and retired clients SHALL remain usable until operations holding their snapshots release them.

#### Scenario: User switches models between turns
- **WHEN** one turn completes and the next message selects a different provider or model
- **THEN** the next turn uses the newly selected identity without changing credential settings

#### Scenario: Credentials change during an operation
- **WHEN** settings are saved while an Agent turn or multi-phase turn-triggered operation is in progress
- **THEN** that operation completes with its original client and model while later operations use the updated provider generation

#### Scenario: Selected provider is not configured
- **WHEN** a message selects a provider whose required connection fields are incomplete
- **THEN** the turn fails before tool execution or durable user-message persistence with a clear configuration error

### Requirement: Protect local LLM APIs from untrusted browser origins
The server SHALL restrict CORS and origin validation for settings mutation, connection testing, and model discovery to configured CashCode frontend origins, while allowing non-browser local clients that do not send an `Origin` header.

#### Scenario: CashCode frontend uses an LLM API
- **WHEN** a request carries an allowed CashCode frontend origin
- **THEN** the server processes it subject to normal validation

#### Scenario: Untrusted website attempts to use an LLM API
- **WHEN** a protected request carries an origin outside the allowed set
- **THEN** the server rejects it before reading secrets, persisting settings, or making a provider request

### Requirement: Connect directly to loopback Ollama endpoints
The runtime SHALL disable ambient HTTP proxy inheritance for Ollama endpoints whose normalized hostname resolves to loopback, while retaining standard proxy behavior for remote Ollama and OpenAI-compatible endpoints.

#### Scenario: System proxy is configured for a local Ollama server
- **WHEN** the Ollama profile uses `localhost`, an IPv4 loopback address, or an IPv6 loopback address and proxy environment variables are present
- **THEN** model discovery, chat, consolidation, and Dream requests connect directly to the configured Ollama endpoint

#### Scenario: Provider endpoint is remote
- **WHEN** an Ollama or OpenAI-compatible profile uses a non-loopback hostname
- **THEN** the runtime does not unconditionally disable the environment's standard proxy behavior
