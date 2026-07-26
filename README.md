English | [简体中文](README.zh-CN.md)

# CashCode

CashCode is a locally hosted personal AI agent framework inspired by Codex, Hermes, and OpenClaw. It supports cross-session persistent memory, local Skills, an MCP tool ecosystem, and streaming chat.

---

## Feature Overview

| Module | What it does |
|---|---|
| WebSocket communication | Streaming chat and tool event notifications |
| Memory system | Cross-session persistence, context compression, and long-term memory distillation |
| Tool execution | ReAct loops, built-in tools, and dynamic tools |
| Agent persona | Configurable identity driven by SOUL.md |
| MCP system | Built-in and user catalogs, marketplace management, explicit connections, deferred activation, stdio/SSE transport |
| Skill system | Natural-language search, two-phase lazy loading, session summaries, management APIs, and self-evolution proposals |

---

## Architecture Overview

```
                    User (frontend WebSocket client)
                              │
                    WebSocketChannel
                    (ws://127.0.0.1:8765)
                              │
                         MessageBus
                    (asyncio queue decoupling)
                              │
                    SimpleAgentLoop
              ┌───────────────┴───────────────┐
              │                               │
      ToolRegistry (built-in)     DeferredAwareRegistry
      save_memory, web_fetch      (MCP tools hidden by default)
      skill_search/load/read      ├── tool_search -> discover MCP tools
      tool_search, mcp_prepare    ├── mcp_prepare -> lazy connect
              │                   └── skill_search/load -> lazy load Skills
              │
              ▼
    SimpleAgentRunner (non-streaming ReAct loop)
              │
    ┌─────────┴──────────┐
    │                    │
Built-in tool exec   MCP tool exec
    │                MCPToolWrapper
    │             session.call_tool()
    │                 │
    │             MCP server (stdio/SSE)
    │
    ▼
fake streaming -> frontend
              │
        MemoryStore
  ┌─────────────────────┐
  │  history.jsonl      │  <- conversation history
  │  metadata.json      │  <- cross-turn state such as activation sets (V2)
  │  MEMORY.md          │  <- global long-term memory
  │  SOUL.md            │  <- agent persona config
  └─────────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
 Consolidator          Dream
(context compression) (long-term memory distillation)
```

---

## Directory Layout

```
CashCode/
├── server/
│   ├── main.py                    # FastAPI + WebSocket service entrypoint
│   ├── .env                       # Optional non-LLM environment configuration
│   ├── requirements.txt
│   ├── data/                      # Skills, user MCP, and self-evolution runtime data (not committed)
│   │   ├── mcp/servers.json       # User-created SSE MCP configuration
│   │   └── skills/
│   │       ├── user/              # User-uploaded and user-managed Skills
│   │       └── agent/             # Skills created by chat or the agent
│   ├── memory/                    # Runtime memory data (not committed)
│   │   ├── SOUL.md                # Agent persona file (committed)
│   │   ├── MEMORY.md              # Global long-term memory (generated at runtime)
│   │   ├── .dream_cursor          # Dream cursor (generated at runtime)
│   │   └── <chat_id>/             # Per-session history directories
│   │       ├── history.jsonl
│   │       ├── metadata.json      # Activation sets and other cross-turn state (V2)
│   │       └── .cursor
│   └── app/
│       ├── agent/
│       │   ├── loop.py            # SimpleAgentLoop main loop, including MCP initialization
│       │   ├── runner.py          # SimpleAgentRunner ReAct loop
│       │   └── tools/
│       │       ├── base.py        # Tool abstract base class
│       │       ├── registry.py    # ToolRegistry
│       │       ├── mcp.py         # MCP connection layer (stdio/SSE + MCPToolWrapper)
│       │       ├── mcp_cache.py   # Tool schema disk cache
│       │       ├── tool_search.py # Deferred activation system (DeferredAwareRegistry,
│       │       │                  # ActivatedToolSet, ToolSearchTool,
│       │       │                  # MCPPrepareTool, BM25 index)
│       │       ├── memory.py      # SaveMemoryTool
│       │       ├── web.py         # WebFetchTool, WebSearchTool
│       │       ├── filesystem.py  # ReadFileTool, WriteFileTool...
│       │       ├── search.py      # GlobTool, GrepTool
│       │       ├── shell.py       # ExecTool
│       │       └── result.py      # Tool result projection for model, frontend, and persistence
│       ├── skills/                # Skill storage, loading, management, and self-evolution
│       │   ├── archive.py         # ZIP safety validation and unpacking
│       │   └── builtin/           # Read-only built-in Skills (committed)
│       ├── api/
│       │   ├── skills.py          # Skill management APIs
│       │   ├── mcp.py             # MCP marketplace, CRUD, and connection APIs
│       │   └── skill_evolution.py # Skill self-evolution proposal APIs
│       ├── memory/
│       │   ├── store.py           # MemoryStore, including session metadata
│       │   ├── consolidator.py    # Context compression
│       │   └── dream.py           # Long-term memory distillation
│       ├── ws/
│       │   └── channel.py         # WebSocketChannel
│       └── bus/
│           ├── queue.py           # MessageBus
│           └── events.py          # InboundMessage, OutboundMessage
├── mcp_servers/                   # Built-in MCP config and test servers (allowlisted for commit)
│   ├── mcp_config.json            # MCP server configuration (stdio/SSE)
│   ├── test_stdio_mcp/
│   │   └── server.py              # stdio test server (say_hello)
│   └── test_sse_mcp/
│       └── server.py              # SSE test server (say_hello)
├── mcp_cache/                     # Tool schema disk cache (not committed)
└── openspec/                      # Change management
    ├── specs/                     # Main specification documents
    └── changes/archive/           # Archived change records
```

---

## 1. WebSocket Protocol

The service listens on `ws://127.0.0.1:8765`, and the HTTP API is available at `http://127.0.0.1:8000`.

### Client -> Server

```json
{"type": "message", "chat_id": "uuid", "content": "user message"}
{"type": "message", "chat_id": "uuid", "content": "inspect repo", "metadata": {"mentioned_skills": [{"name": "code-review", "label": "Code Review"}], "selected_mcp_connectors": [{"server": "github", "label": "GitHub"}]}}
{"type": "ping"}
{"type": "new_chat"}
{"type": "attach", "chat_id": "uuid"}
{"type": "cancel", "chat_id": "uuid"}
```

### Server -> Client

```json
{"event": "ready",       "chat_id": "...", "client_id": "..."}
{"event": "tool_call",   "chat_id": "...", "tool_name": "web_fetch", "stream_id": 123}
{"event": "tool_result", "chat_id": "...", "tool_name": "web_fetch", "result": "...", "stream_id": 123}
{"event": "delta",       "chat_id": "...", "text": "...", "stream_id": 123}
{"event": "stream_end",  "chat_id": "...", "stream_id": 123}
{"event": "done",        "chat_id": "...", "duration_sec": 2.3}
{"event": "error",       "detail": "..."}
```

### Architecture Notes

`MessageBus` is an asyncio queue that decouples the WebSocket channel from the agent loop. `WebSocketChannel` converts client frames into `InboundMessage` instances and pushes them into the queue. `SimpleAgentLoop` consumes the queue and routes `OutboundMessage` instances back through `WebSocketChannel` to subscribers.

---

## 2. Memory System

The memory system has three layers, from short-term to long-term:

```
InboundMessage
      │
      ▼
 history.jsonl      <- Layer 1: raw conversation stream (append-only)
      │
      ▼
  Consolidator      <- Layer 2: context compression (per turn, triggered by character threshold)
      │
      ▼
  Dream             <- Layer 3: long-term memory distillation (scheduled, every 5 minutes)
      │
      ▼
  MEMORY.md         <- global long-term memory injected into the system prompt
```

### Layer 1: MemoryStore (`store.py`)

Each `chat_id` maps to a subdirectory. `history.jsonl` is an append-only conversation ledger:

```jsonl
{"cursor": 1,  "role": "user",       "content": "hello"}
{"cursor": 2,  "role": "assistant",  "content": "hello!"}
{"cursor": 3,  "role": "tool_calls", "content": "[TOOL_CALLS: web_fetch]", "tool_calls": [...]}
{"cursor": 4,  "role": "tool",       "content": "fetch result...", "tool_call_id": "call_xxx"}
{"cursor": 5,  "role": "assistant",  "content": "based on the page content..."}
{"cursor": 6,  "role": "summary",    "content": "summary...", "keep_from_cursor": 3}
```

**Restart recovery (Smart Load)**: `load_history_smart()` finds the last `summary` record, reads its `keep_from_cursor`, and reloads the summary plus recent messages where `cursor >= keep_from_cursor`. This prevents previously compressed old messages from being fed back into the consolidator after restart.

**Global files**:
- `SOUL.md` - agent persona (committed)
- `MEMORY.md` - cross-session long-term memory (generated at runtime)
- `.dream_cursor` - JSON file recording how far Dream has processed each `chat_id`

### Layer 2: SimpleConsolidator (`consolidator.py`)

Triggered after each conversation turn. When the character threshold is exceeded (default `40,000`), it compresses older messages:

```
Strategy: cumulative compression, not incremental
  to_compress = history[:keep_from]  includes existing summary prefix
  to_keep     = history[keep_from:]  keeps the most recent 50% of characters

Compressed in-memory history:
  [cumulative summary] + [to_keep messages]

Appended to history.jsonl:
  {"role": "summary", "keep_from_cursor": N, ...}
```

**Key design points**:
- **Cumulative compression**: every summary includes the previous summary, so after restart only the latest summary is needed to restore the full context.
- **`keep_from_cursor` metadata**: records the cursor of the first retained message so Smart Load can restore the retained tail precisely.
- **Atomic persistence**: write to `history.jsonl` first, then update in-memory history only after success. Failures roll back to maintain consistency.
- **Per-chat-id `asyncio.Lock`**: prevents duplicate compression under concurrent requests for the same session.

### Layer 3: SimpleDream (`dream.py`)

Runs every 5 minutes in the background via `asyncio.create_task`, using a two-phase LLM flow:

```
Phase 1: analysis
  Input: unprocessed history entries from all chat_ids + current MEMORY.md
  Output: analysis report describing which long-term memories to add, update, or remove

Phase 2: generation
  Input: Phase 1 report + current MEMORY.md
  Output: the complete new MEMORY.md
```

After each run it advances the Dream cursor for every `chat_id` in `memory/.dream_cursor`, so the next run only processes newly added entries.

### MEMORY.md Injection

The system prompt is built like this each turn:

```python
soul = store.read_soul() or _DEFAULT_SOUL
memory = store.read_memory()

system_prompt = soul
if memory:
    system_prompt += f"\n\n## Information you already remember\n{memory}"
```

---

## 3. Tool Execution System

### Architecture: Two-Phase Execution

```
User message
    │
    ▼
Phase 1: SimpleAgentRunner (non-streaming ReAct loop)
    │
    ├── LLM call with tools=[...] and stream=False
    │     │
    │     ├── If tool_calls exist -> send `tool_call` WS event
    │     │                       -> execute tool
    │     │                       -> send `tool_result` WS event
    │     │                       -> append result -> call LLM again
    │     │
    │     └── If no tool_calls -> return final_text
    │
    ▼
Phase 2: fake streaming
    Split final_text into 15-character chunks and send `_stream_delta` events
    The frontend experience matches real streaming
```

The full tool chain is persisted into `history.jsonl` (`user -> tool_calls -> tool_result -> assistant`), so tool context can be reconstructed after restart.

### Tool Base Class (`tools/base.py`)

```python
class Tool(ABC):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    def parameters(self) -> dict: ...
    def to_openai_schema(self) -> dict: ...
    async def execute(self, **kwargs) -> str: ...
```

### Built-in Tools

| Tool name | Class | Description |
|---|---|---|
| `save_memory` | SaveMemoryTool | Immediately writes important facts to MEMORY.md |
| `web_fetch` | WebFetchTool | Fetches URL content with `httpx`, up to 3000 characters |
| `web_search` | WebSearchTool | Uses the DuckDuckGo Instant Answer API |
| `read_file` | ReadFileTool | Reads files under `WORKSPACE_DIR`, up to 500 lines |
| `write_file` | WriteFileTool | Creates or overwrites files under `WORKSPACE_DIR` |
| `edit_file` | EditFileTool | Precise unique string replacement (`old -> new`) |
| `list_dir` | ListDirTool | Lists directory contents with type markers |
| `glob` | GlobTool | File pattern search such as `**/*.py`, up to 100 results |
| `grep` | GrepTool | Regex search across files, up to 50 results |
| `exec` | ExecTool | Executes shell commands under `WORKSPACE_DIR`, 30s timeout |

---

## 4. MCP System

CashCode implements a full MCP (Model Context Protocol) integration layer so external MCP server tools can be exposed directly to the agent.

### MCP Marketplace and Configuration Sources

The `MCP Market` sidebar merges two configuration sources:

- `mcp_servers/mcp_config.json` is the built-in read-only catalog shipped with the project. It supports stdio and SSE. In the marketplace these entries are marked as built-in and can be connected or disconnected, but not edited or deleted.
- `CASHCODE_DATA_DIR/mcp/servers.json` is the user catalog, located by default at `server/data/mcp/servers.json`. Users can create, edit, and delete entries here. At present, only SSE is supported for user-created connectors.

User MCP entries include an internal name, display title, description, an HTTP(S) SSE URL, and optional headers. Header values are stored locally in user data files and are not statically encrypted. APIs and edit forms return only `********`; submitting that placeholder preserves the existing secret. Connection errors, tool metadata, and chat history never echo header values.

Creating or editing a config does not connect automatically. After the user clicks Connect, the backend completes the transport handshake and `list_tools`; only then does the entry show as connected. Disconnect closes the transport and removes the live tools owned by that server. Connection failures are surfaced in the marketplace as redacted, retryable errors.

| API | Description |
|---|---|
| `GET/POST /api/mcp/servers` | Query the merged catalog or create a user SSE MCP entry |
| `PUT/DELETE /api/mcp/servers/{name}` | Edit or delete a user MCP entry; built-ins return `403` |
| `POST /api/mcp/servers/{name}/connect` | Explicitly connect and discover tools |
| `POST /api/mcp/servers/{name}/disconnect` | Explicitly disconnect and clear live tools |
| `GET /api/mcp/servers/{name}/tools` | Query live tools or cached info when the config fingerprint is still valid |

### Selecting MCPs or Skills in Chat

Type `@` at a token boundary in the composer, choose `MCP` or `Skill`, then search the currently available list. The MCP list only includes connected servers with discovered live tools. The Skill list only includes enabled Skills whose dependencies are satisfied. Selected items are shown as removable chips. A single message can contain at most 8 selections in total, and the message body cannot be empty.

Selections are sent as structured WebSocket metadata and are not appended to the task text. Explicitly selected MCP permissions are valid only for the current turn, but marketplace transports stay connected until the user disconnects, edits, deletes, or the service exits. Skill and MCP mentions are persisted with the user message and restored when a session is reopened. The legacy `@<skill>` text syntax is still supported for compatibility.

### Core Design: Deferred Activation

Exposing every tool to the LLM would inflate the context window. CashCode uses **deferred activation**:

```
LLM sees by default:                MCP tools hidden by default:
  tool_search  <- discovery tool     mcp_test_stdio_mcp_say_hello X
  mcp_prepare  <- on-demand connect  mcp_test_sse_mcp_say_hello   X
  save_memory
  web_fetch    ...

User asks to call the stdio test MCP
    ↓
LLM calls tool_search("stdio Hello Cash")
    ↓ BM25 hits the stdio test server stub
LLM calls mcp_prepare("test_stdio_mcp")
    ↓ stdio connection established -> list_tools -> activation
LLM calls mcp_test_stdio_mcp_say_hello()
    ↓
Returns "Hello, Cash" and can be called directly next time
```

### Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│  DeferredAwareRegistry (LLM-facing view)                │
│  - Built-in tools remain visible at all times           │
│  - MCP tools stay hidden until activated                │
│  - Cache key includes activation_revision               │
├──────────────────────────────────────────────────────────┤
│  ActivatedToolSet (session state layer)                 │
│  - LRU dict with capacity 50                            │
│  - ContextVar-bound to the current async task           │
│  - Persisted to memory/<chat_id>/metadata.json          │
├──────────────────────────────────────────────────────────┤
│  ToolSearchTool + ToolSearchIndex (discovery layer)     │
│  - BM25 (k1=1.5, b=0.75) + CJK bigrams + camelCase      │
│  - Merges disk cache and live registry                  │
│  - Emits service-level stubs when no live tools exist   │
├──────────────────────────────────────────────────────────┤
│  mcp_cache.py (offline cache layer)                     │
│  - One JSON file per server                             │
│  - Invalidates on transport fingerprint changes         │
│  - Written after successful mcp_prepare                 │
├──────────────────────────────────────────────────────────┤
│  MCPPrepareTool + lazy_connect (connection layer)       │
│  - Calls lazy_connect -> establish_mcp_sessions         │
│  - stdio spawns a child process; SSE connects to HTTP   │
│  - Handshake -> list_tools -> register wrapper          │
├──────────────────────────────────────────────────────────┤
│  MCPToolWrapper (adapter layer)                         │
│  - Exposes the Tool interface outwardly                 │
│  - Delegates inwardly to session.call_tool()            │
│  - Naming format: mcp_{server_name}_{tool_name}         │
└──────────────────────────────────────────────────────────┘
```

### Two Transport Protocols

| Transport | Configuration | How the server starts | Typical use case |
|---|---|---|---|
| **stdio** | `command + args` | No separate process needed; CashCode launches it during `mcp_prepare` | Local command-line tools |
| **SSE** | `url` | Requires a separately running HTTP service | Public MCP services and third-party APIs |

```json
// mcp_servers/mcp_config.json
{
  "test_stdio_mcp": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp_servers/test_stdio_mcp/server.py"],
    "display_name": "stdio test MCP",
    "description": "Provides a say_hello tool that returns Hello, Cash"
  },
  "test_sse_mcp": {
    "type": "sse",
    "url": "http://127.0.0.1:8090/sse",
    "display_name": "SSE test MCP",
    "description": "Provides a say_hello tool that returns Hello, Cash and requires a separately started service"
  }
}
```

### Local Test MCP Servers

| Server | Transport | Tool | Startup |
|---|---|---|---|
| `test_stdio_mcp` | stdio | `say_hello()` -> `Hello, Cash` | Launched automatically by `mcp_prepare` |
| `test_sse_mcp` | SSE | `say_hello()` -> `Hello, Cash` | Must be started manually |

```bash
# Start before using the SSE server
python mcp_servers/test_sse_mcp/server.py
```

### Full Session Flow

```
1. The agent starts in lazy mode
   -> reads mcp_config.json without connecting
   -> disk cache still allows tool_search to discover tools

2. The user asks to use the stdio test MCP
   -> tool_search("stdio Hello Cash") finds the test_stdio_mcp stub
   -> it indicates that mcp_prepare("test_stdio_mcp") is needed

3. mcp_prepare("test_stdio_mcp")
   -> starts the stdio child process
   -> list_tools -> register MCPToolWrapper -> write mcp_cache
   -> activate mcp_test_stdio_mcp_say_hello

4. mcp_test_stdio_mcp_say_hello()
   -> returns "Hello, Cash"

5. Later turns can call it directly
   -> DeferredAwareRegistry sees the tool in ActivatedToolSet
   -> tool_search is skipped because activation persists across turns
```

---

## 5. Skill System

CashCode provides a local Skill runtime on the server side. The model can always see `skill_search`, `skill_load`, `skill_read_resource`, and the managed `agent_skill_manage`, but the system does not inject every installed Skill's description or body into context up front.

### Storage Directories

`CASHCODE_DATA_DIR` defaults to `server/data`, with this structure:

```text
skills/user/          User-managed Skill packages
skills/agent/         Skill packages owned by the agent after chat creation or approval
skill-snapshots/      Recovery snapshots used for replace, rollback, and invalid deletion
skill-evolution/      Self-evolution evidence and proposals
```

Built-in Skills live in `server/app/skills/builtin` and are read-only at runtime. Effective namespace precedence is `builtin < user < agent`, so higher-priority packages shadow lower-priority ones with the same name. The catalog metadata exposes shadowing sources.

### Skill Package Format

Each Skill is a directory containing `SKILL.md`, and may optionally include `references/`, `templates/`, `scripts/`, and `assets/`. The directory name must match the canonical `name` in the frontmatter. `name` allows only 1-64 lowercase letters, digits, dots, underscores, and hyphens. It is used for directories, API routes, exact search identity, `@` selection, collision checks, hashes, and snapshots. `display_name` is optional, up to 80 characters, and used only for UI labels.

```yaml
---
name: example-workflow
display_name: Example Workflow
description: Describe the capability and when it should be used
version: 1
tags: [example]
triggers: [example request]
requires:
  tools: [read_file]
  mcp_servers: []
  bins: []
  env: []
optional:
  tools: []
  mcp_servers: []
---
```

The loader validates YAML field types, names, UTF-8 encoding, file sizes, supported directories, and path boundaries. It rejects absolute paths, `..` traversal, and symlinks that escape the package root. Loading a Skill does not auto-run scripts, install binaries, modify environment variables, authenticate, or start undeclared MCP servers.

### Skill Marketplace, Import, and Editing

The `Skill Market` sidebar shows built-in, user-uploaded, and chat-created agent Skills from the current effective catalog, with pagination. The list uses `display_name` as the primary label while preserving the canonical `name` as the stable identifier. Disabled Skills and Skills with missing dependencies remain visible for troubleshooting and re-enabling. Built-ins are marked as built-in and can only be viewed. User and agent Skills can be viewed, edited, enabled, disabled, and deleted with confirmation.

The import entrypoint accepts a single ZIP Skill package. The ZIP can either place `SKILL.md` at the root or wrap it in one top-level directory. The final directory name is derived from the validated `name` in frontmatter. The backend enforces these limits: 10 MiB archive size, 256 members, 20 MiB total extracted size, `SKILL.md` up to 80 KB, and each support file up to 200 KB. Path traversal, drive-letter paths, duplicate paths, encrypted members, symlinks, and special files are rejected.

Uploaded packages always go into `skills/user/`. `_meta.json` inside the archive cannot claim built-in or agent ownership. If the same Skill name already exists in `builtin`, `user`, or `agent`, the API returns `409` rather than overwriting or shadowing it. Unpack and full validation happen in a hidden temporary directory. Only validated packages are published atomically and followed by a catalog refresh.

When the user explicitly asks to create a Skill in chat, the agent first loads the built-in `skill-creator`, then calls `agent_skill_manage(action=create)`. That tool always writes to `skills/agent/` and enables the package. It validates the full contents with the same loader used by the catalog before the directory is created, then uses the shared `SkillStore` to enforce cross-root uniqueness, atomic publish, and catalog refresh. Success requires `success=true` and a visible record with the same name, hash, and `source=agent`. On validation failure, the agent may only fix the contents and retry through that managed tool, or report failure. General `write_file` and `edit_file` refuse writes to user and agent Skill roots, and the creation flow must not bypass the manager with `exec`, `curl`, or ad hoc HTTP requests.

Python tool registration and the built-in `skill-creator` contract are loaded only at service startup. After changing server-side code, CashCode must be restarted. Older processes do not pick up `agent_skill_manage` or write protections automatically, and historical versions may still attempt `write_file` or `exec`, so they cannot validate the newer creation flow.

Invalid directories are excluded from search, `@` selection, and the normal Skill list. The marketplace shows them in a separate diagnostics area with redacted, length-limited source, directory name, and error message. Diagnostic rows cannot be viewed, edited, enabled, disabled, or selected. User and agent invalid entries expose an explicit delete action. On confirmation, the backend revalidates that the target is still invalid, moves the entire directory to `skill-snapshots/invalid/<source>/...`, and refreshes the catalog. Built-in invalid entries cannot be deleted. The system never migrates, rewrites, or deletes legacy packages automatically.

If a legacy package such as `server/data/skills/user/renzhi-niuqu` is invalid because its frontmatter uses `name: 认知扭曲`, the fix is explicit: either stop the service, change `name` to `renzhi-niuqu`, add `display_name: 认知扭曲`, verify that the package root only contains allowed files, then restart; or delete it from the marketplace and rely on the invalid snapshot for recovery. As long as the old directory still exists in an active root, imports and chat-based creation with the same name will return conflicts to avoid silent overwrite.

The first marketplace editor version edits only the full `SKILL.md`. It does not rename Skills or edit individual files under `references/`, `templates/`, `scripts/`, or `assets/`. Save requests carry the hash of the content that was originally read. Concurrent edits return `409` while preserving the current draft. Saves create version snapshots, and unchanged support files are copied through without text re-encoding, so binary assets remain intact.

### Search, Loading, and Context Lifecycle

Natural-language invocation uses a two-phase lazy-loading flow:

```text
User request
  -> skill_search(query)        search canonical name, display name, description, tags, and triggers
  -> skill_load(exact_name)     validate and inject the full SKILL.md into the current turn
  -> skill_read_resource(...)   read individual support files only when needed by the workflow
  -> domain tools
  -> final content
```

Messages may begin with `@name` to select a Skill exactly. `@name` only skips search; it does not bypass enabled-state checks, format validation, safety checks, or dependency validation. Full Skill bodies and support files only exist in the current turn. History stores receipts such as `[Skill loaded: ...]` and `[Skill resource read: ...]` instead.

`activated_skills` in session metadata is a bounded LRU summary that stores only the name, short description, version, content hash, and last-used time. Later turns can see those recent hints, but they must call `skill_load` again to regain the full instructions. If a Skill is deleted, disabled, or changes hash, an old summary is never treated as loaded content.

### MCP Dependency Coordination

Required MCP servers declared in `requires.mcp_servers` are prepared through the existing lazy-connect mechanism only after `skill_load`, and their tools become available in the next ReAct iteration of the same turn. `optional.mcp_servers` only reports status and does not connect during load. `mcp_*` names that appear in a Skill body without being declared in frontmatter do not trigger connections or activation permissions.

### Management APIs

The service exposes these REST APIs:

| API | Description |
|---|---|
| `GET/POST /api/skills` | Paginated query or creation of Skills |
| `GET/PUT/DELETE /api/skills/{name}` | View, replace, or delete a Skill |
| `POST /api/skills/import` | Securely import a single user Skill ZIP |
| `GET /api/skills/{name}/content` | Read the full `SKILL.md`, hash, source, and mutable state |
| `DELETE /api/skills/invalid/{source}/{directory}` | Revalidate and snapshot-delete an invalid user or agent package |
| `POST /api/skills/{name}/validate` | Revalidate a Skill package |
| `PATCH /api/skills/{name}/enabled` | Enable or disable a mutable Skill |
| `GET /api/skills/{name}/versions` | Query version snapshots |
| `POST /api/skills/{name}/rollback/{version}` | Atomically roll back to a specific version |

Built-in Skills cannot be modified. User and agent Skill writes go through consistent validation for name, content, path, precondition hashes, and atomic replacement. Snapshots are preserved before replacement or rollback. Default user and agent Skills and user MCP configs live under `server/data/` and are not tracked in Git. Built-in resources under `server/app/skills/builtin/` and allowlisted test resources under `mcp_servers/` are tracked.

### Skill Self-Evolution Preview

Self-evolution is off by default. It can be enabled by adding environment variables to `server/.env`:

```ini
SKILL_EVOLUTION_ENABLED=true

# Defaults
SKILL_EVOLUTION_MIN_TOOL_CALLS=2
SKILL_EVOLUTION_RECURRENCE=2
```

A turn contributes self-evolution evidence only when all of the following are true:

- Evolution is enabled.
- The turn completed successfully and was persisted.
- The turn called tools at least `SKILL_EVOLUTION_MIN_TOOL_CALLS` times, which defaults to 2.
- No tool call in the turn failed.
- The runner did not hit its maximum iteration limit.

Evidence becomes eligible for proposal generation only after a recurrence threshold is met: the same workflow fingerprint must appear at least `SKILL_EVOLUTION_RECURRENCE` times, which defaults to 2. The workflow fingerprint is generated from normalized user input plus the set of tool names used in that turn.

Only truncated and redacted evidence is retained. Once the recurrence threshold is met, the restricted Evolver can read only bounded Skill summaries and the `skill-creator` contract to generate a proposal. It cannot access the general filesystem, shell, web, MCP, or direct Skill mutation paths.

Proposals are listed, approved, or rejected through `/api/skill-evolution/proposals` and are never auto-applied. Approval rechecks ownership, base hash, and full package validation. Only `agent` Skills can be created or modified through this path; built-in and user Skills cannot. Version snapshots are created before apply, and rollback remains available through the version APIs afterward.

---

## 6. SOUL.md: Agent Persona Configuration

`server/memory/SOUL.md` defines the agent's identity and behavioral rules. Edit this file directly to adjust the agent's style. No code changes are required, and the change takes effect after restart.

If the file does not exist, the system falls back automatically to the built-in `_DEFAULT_SOUL` string in code.

---

## 7. Quick Start

### Environment Setup

```bash
cd server
pip install -r requirements.txt
```

### LLM Configuration

The backend does not require a pre-created `.env`, and it can still start before any model service is configured. After starting the backend and frontend, open `Settings` -> `LLM Settings` at the bottom of the left sidebar and save your connection info:

- `Generic API`: API base URL and API key for an OpenAI-compatible interface.
- `Ollama`: the Ollama service address, for example `http://127.0.0.1:11434`.

Models are not activated or saved in the settings panel. Return to the chat view and choose the model for the current turn from the model picker to the left of the send arrow. The list discovers configured Generic API models and Ollama models separately. Each message carries its own provider and model selection, so switching models does not rewrite stored credentials.

On the first valid save, CashCode creates a user-private `settings/llm.json`. By default, that file is stored outside the Git workspace:

- Windows: `%LOCALAPPDATA%\CashCode\settings\llm.json`
- macOS: `~/Library/Application Support/CashCode/settings/llm.json`
- Linux: `$XDG_CONFIG_HOME/cashcode/settings/llm.json`, or `~/.config/cashcode/settings/llm.json` when XDG is unset

API reads never return stored secrets. Tests or managed deployments can override the configuration root with `CASHCODE_CONFIG_DIR`. If that is pointed at the project-local `server/data`, the directory and the LLM secret fallback are already ignored by Git.

For older users, when the new config file does not yet exist, existing `DEEPSEEK_API_KEY` and `DEEPSEEK_API_BASE` values are migrated once into the new file. `DEEPSEEK_MODEL` is not migrated because the model is now selected from the chat composer. Migration does not rewrite `.env`; once the new file exists, LLM configuration no longer reads those legacy variables.

### Optional Runtime Configuration

These non-LLM settings can be overridden by process environment variables or an optional `server/.env`. Defaults are used when omitted:

```ini
WS_HOST=127.0.0.1
WS_PORT=8765
CASHCODE_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

# Working directory for filesystem tools and exec tools
# WORKSPACE_DIR=/your/workspace/path
# CASHCODE_DATA_DIR=/your/runtime/data/path
# CASHCODE_CONFIG_DIR=/your/private/config/path

# Persistent runtime logging (defaults shown)
# CASHCODE_LOG_DIR=logs
CASHCODE_FILE_LOG_LEVEL=DEBUG
CASHCODE_CONSOLE_LOG_LEVEL=INFO
CASHCODE_LOG_RETENTION_DAYS=10
```

### Runtime Logs and Test Output

The backend appends UTF-8 runtime records to `server/logs/cashcode.log` by default. It rotates on the first record after local midnight and retains the active calendar day plus the previous nine days. A relative `CASHCODE_LOG_DIR` is resolved from `server/`, independent of the process working directory. Startup fails if the runtime log cannot be created; generated runtime files remain ignored by Git.

Use the existing Miniconda `AuWork` environment as the local server verification environment. From the repository root, synchronize it only from the project requirements and persist test output under `server/pytest_logs` when needed:

```powershell
conda run -n AuWork python -m pip install --upgrade -r server/requirements.txt
conda run -n AuWork python -m pytest server/tests *>> server/pytest_logs/pytest.log
```

Frontend development and test process output belongs under `client/logs`. These PowerShell examples append rather than truncate:

```powershell
npm --prefix client run dev *>> client/logs/vite.log
npm --prefix client test *>> client/logs/test.log
```

`server/pytest_logs` and `client/logs` are not application runtime log destinations. Browser console errors remain in developer tools and are not uploaded automatically.

### Start the Service

```bash
cd server
python main.py
```

After startup:
- HTTP API: `http://127.0.0.1:8000`
- WebSocket: `ws://127.0.0.1:8765`
- MCP servers connect lazily and are activated on first use
- The frontend `MCP Market` can also connect or disconnect explicitly
- The Dream background task runs every 5 minutes

### Use the SSE MCP Server (Optional)

The SSE server must be started separately. The stdio server does not:

```bash
# Start in another terminal
python mcp_servers/test_sse_mcp/server.py
# After startup: SSE test MCP is available at http://127.0.0.1:8090/sse
```

### Test the Connection

```python
import asyncio, json, websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        ready = json.loads(await ws.recv())
        chat_id = ready["chat_id"]
        await ws.send(json.dumps({
            "type": "message",
            "chat_id": chat_id,
            "content": "Hello, please remember that my name is Cash"
        }))
        async for msg in ws:
            data = json.loads(msg)
            print(data)
            if data.get("event") == "done":
                break

asyncio.run(test())
```

---

## 8. Frontend

The frontend lives in `client/` and is built with Vite, React 19, TypeScript, and Tailwind v4.

### Start the Frontend Alongside the Backend

```bash
# Terminal 1: start backend
cd server && python main.py

# Terminal 2: start frontend
cd client && npm install && npm run dev
# Open: http://localhost:5173
```

### Frontend Features

- Sidebar navigation for new chat, MCP Market, Skill Market, and collapsible history
- MCP Market with built-in badges, user SSE configs, headers, connect, disconnect, edit, and delete
- Skill Market with source and status, paginated search, ZIP upload, full-content editing, enable, disable, and delete
- Two-level `@` picker and Skill or MCP selection chips in the composer
- Streaming chat messages with Markdown rendering, code highlighting, and tables
- Tool call progress display with spinner and result preview
- Automatic WebSocket reconnection
- Dark theme
