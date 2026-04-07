# Simplified MVP: obsidian-ops → three repositories

## Context

obsidian-ops is a single Python package (~750 lines) that couples three concerns: static site serving with UI injection, an LLM agent loop with vault tools, and rebuild/versioning orchestration. We are splitting it into three independently-maintained repositories with enforced process boundaries.

This document describes the **simplified MVP** architecture. Key simplifications from the original concept:
- **No SSE, no job queue** — synchronous request/response API. The agent runs inline and returns a final result.
- **No broadcaster, no subscriber lifecycle** — eliminates the most complex Python code.
- **Forge reverse proxy is trivial** — without SSE, it's a plain HTTP forwarder with no flush concerns.
- **Defer `/api/history` endpoint** — not part of the core edit loop.
- **Minimal abstractions** — one protocol (`AgentRunner`) for future swappability; concrete classes everywhere else.

---

## Architecture overview

```
┌───────────────────────────────────────────────────────────┐
│  Browser (tailnet)                                        │
│  ┌─────────────────────┐  ┌────────────────────────────┐  │
│  │ Kiln-rendered page   │  │ Overlay UI (ops.js/ops.css)│  │
│  └─────────────────────┘  └────────────────────────────┘  │
│            │                          │                    │
│        GET /page                POST /api/apply            │
└───────────┬───────────────────────┬───────────────────────┘
            │                       │
            ▼                       ▼
┌───────────────────────────────────────────────────────────┐
│  Forge (Go binary, port 8080)                             │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ kiln dev     │  │ HTML inject  │  │ /api/* reverse  │  │
│  │ (build+watch │  │ middleware   │  │ proxy → :8081   │  │
│  │  +serve)     │  │ (</head>)    │  │                 │  │
│  └──────────────┘  └──────────────┘  └────────┬────────┘  │
│                                                │          │
│  ┌──────────────┐                              │          │
│  │ /ops/* static│                              │          │
│  │ file serving │                              │          │
│  └──────────────┘                              │          │
└────────────────────────────────────────────────┼──────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────┐
│  obsidian-agent (Python, port 8081)                       │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ POST /api/   │  │ Agent loop   │  │ Vault tools     │  │
│  │ apply, undo, │──│ (OpenAI SDK, │──│ (read/write/    │  │
│  │ health       │  │  tool calls) │  │  list/search/   │  │
│  └──────────────┘  └──────────────┘  │  fetch/undo)    │  │
│                                      └────────┬────────┘  │
│                                               │           │
│                    ┌──────────────┐            │          │
│                    │ Jujutsu VCS  │◄───────────┘          │
│                    │ (commit/undo)│                       │
│                    └──────────────┘                       │
└───────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Vault (markdown)│ ◄── Forge file watcher detects changes,
│ Site (html out) │     triggers rebuild automatically
└─────────────────┘

┌───────────────────────────────────────────────────────────┐
│  obsidian-ops (Python CLI)                                │
│  Starts Forge + agent as subprocesses, manages config     │
└───────────────────────────────────────────────────────────┘
```

### Data flow for a user instruction

1. User types instruction in overlay UI, clicks Run.
2. `ops.js` sends `POST /api/apply` to Forge (port 8080).
3. Forge reverse-proxies the request to obsidian-agent (port 8081).
4. Agent runs the LLM tool-calling loop synchronously (reads/writes vault files).
5. If files changed: agent commits via `jj commit`.
6. Agent returns `{ ok, updated, summary, changed_files }`.
7. Forge proxies the response back to the browser.
8. If `updated=true`, UI shows "Updated — refresh to see changes."
9. Forge's file watcher (from `kiln dev`) detects vault changes and rebuilds the site.
10. User refreshes the page.

---

## Shared API contract

This is the interface between Forge (proxy) and obsidian-agent (backend). Both repos must agree on these endpoints.

### `POST /api/apply`

Execute an instruction against the vault.

```
Request:
{
  "instruction": "Add a summary section to this note",
  "current_url_path": "/notes/example"
}

Response (200):
{
  "ok": true,
  "updated": true,
  "summary": "Added a summary section with key points.",
  "changed_files": ["notes/example.md"],
  "warning": null,
  "error": null
}
```

Semantics:
- `ok=true` means the operation completed without fatal error.
- `updated=true` means vault content was modified (the user should refresh).
- `updated=false` means the agent ran but made no file changes.
- `ok=false` means a fatal error occurred; `error` contains the message.
- `warning` is optional and non-fatal (e.g., "changes saved but rebuild failed").

### `POST /api/undo`

Undo the last Jujutsu change.

```
Request: (empty body)

Response (200):
{
  "ok": true,
  "updated": true,
  "summary": "Last change undone.",
  "changed_files": [],
  "warning": null,
  "error": null
}
```

### `GET /api/health`

Health check for process orchestration.

```
Response (200):
{ "status": "ok" }
```

### Timeout contract

The agent enforces a hard timeout on the entire operation (LLM calls + tool execution). Default: 120 seconds. If exceeded, the agent returns `ok=false` with an appropriate error. Forge's reverse proxy should use a longer timeout (e.g., 180s) so the agent always responds before the proxy gives up.

---

## Repository 1: Forge (Go)

### Purpose

Forge is a fork of [Kiln](https://github.com/otaleghani/kiln) v0.9.5 that adds three capabilities to the existing `dev` command: response-time HTML injection, API reverse proxying, and overlay static asset serving. It is the single entry point for the browser.

### What Forge owns

| Concern | How |
|---------|-----|
| Static site generation | Kiln's existing `generate` pipeline |
| File watching + incremental rebuild | Kiln's existing `dev` command watcher |
| HTTP serving of generated site | Kiln's existing dev server |
| Clean URL handling | Kiln's existing URL rewriting |
| HTML overlay injection | **New**: response-time middleware |
| API proxying to agent | **New**: reverse proxy for `/api/*` |
| Overlay asset serving | **New**: static file serving for `/ops/*` |

### What Forge does NOT own

- LLM interaction, tool execution, vault safety policies — that's obsidian-agent.
- Process orchestration, configuration management — that's obsidian-ops.
- Vault content decisions — the agent writes files; Forge just detects changes and rebuilds.

### Architectural boundary

Forge communicates with obsidian-agent exclusively via HTTP. It has zero knowledge of Python, the agent loop, or vault tools. From Forge's perspective, the agent is an opaque HTTP backend at a configurable URL.

Forge communicates with obsidian-ops via CLI arguments and process lifecycle (stdin/stdout/stderr/exit code). The orchestrator starts Forge as a subprocess.

### New CLI interface

```
forge dev \
  --input /path/to/vault \
  --output /path/to/site \
  --port 8080 \
  --proxy-backend http://127.0.0.1:8081 \
  --overlay-dir /path/to/overlay/static \
  --inject-overlay
```

All new flags are optional. Without `--proxy-backend`, Forge behaves identically to `kiln dev`. This means the fork remains usable as a standalone Kiln replacement.

| Flag | Default | Purpose |
|------|---------|---------|
| `--proxy-backend` | (none) | URL to forward `/api/*` requests to |
| `--overlay-dir` | (none) | Directory containing `ops.css`, `ops.js` served at `/ops/*` |
| `--inject-overlay` | `false` | Enable response-time HTML injection |

### New Go code

#### 1. Response-time HTML injection middleware

Location: `internal/overlay/inject.go`

An `http.Handler` wrapper that intercepts HTML responses and injects overlay tags before `</head>`:

```html
<!-- ops-overlay -->
<link rel="stylesheet" href="/ops/ops.css">
<script src="/ops/ops.js" defer></script>
```

This replaces the current Python `inject.py` (29 lines) which rewrites files on disk after each `kiln generate`. The response-time approach is necessary because `kiln dev` regenerates output files continuously, which would overwrite disk-based injection.

Implementation notes:
- Buffer HTML responses, find `</head>`, insert tags. Non-HTML responses pass through unmodified.
- Strip `Content-Length` from upstream and let Go's HTTP server handle chunked encoding (simplest approach for an MVP).
- Check `Content-Type` header for `text/html` before buffering.

#### 2. API reverse proxy

Location: `internal/proxy/reverse.go`

A standard `net/http/httputil.ReverseProxy` that forwards any request with path prefix `/api/` to the `--proxy-backend` URL.

Without SSE, this is trivially simple — just forward request, get response, return it. No flush handling needed.

Implementation notes:
- Preserve all headers, query parameters, and request body.
- Forward the `Host` header as-is (or strip it — the agent doesn't care for MVP).
- Set a response timeout matching or exceeding the agent's operation timeout (180s).

#### 3. Overlay static file serving

Serve files from `--overlay-dir` at the `/ops/` URL prefix using Go's `http.FileServer`.

The overlay assets (`ops.css`, `ops.js`) live in the Forge repository under `static/`. In development, `--overlay-dir` points to this directory. In production, they could be embedded via `//go:embed` (future enhancement).

#### 4. Handler chain in the `dev` command

The enhanced dev server composes handlers in this order:

```
Request → /api/* prefix? → Yes → Reverse Proxy → Agent backend
                          → No  → /ops/* prefix? → Yes → Static file server (overlay dir)
                                                  → No  → HTML injection middleware → Kiln dev server
```

### What Python code Forge replaces

| Current Python | Forge replacement |
|----------------|-------------------|
| `inject.py` — `inject_overlay()` walks HTML files on disk, inserts marker + tags before `</head>` | `internal/overlay/inject.go` — same logic but on HTTP responses |
| `rebuild.py` — `KilnRebuilder` shells out to `kiln generate` per job | Kiln's built-in `dev` mode watches + rebuilds automatically |
| `app.py` — `rewrite_clean_urls` middleware rewrites extensionless paths to `.html`/`index.html` | Kiln's existing clean URL handling in its dev server |
| `app.py` — `StaticFiles(directory=site_dir, html=True)` mount at `/` | Kiln's existing static file serving |
| `app.py` — `StaticFiles(directory=static_dir)` mount at `/ops` | `http.FileServer` at `/ops/` |

### Testing strategy

- **inject.go**: Unit test with synthetic HTML response bodies. Verify tag insertion, non-HTML passthrough, missing `</head>` handling.
- **reverse.go**: Unit test with `httptest.Server` as mock backend. Verify request forwarding, response passthrough, timeout behavior.
- **Integration**: Run `forge dev` against the demo vault, curl endpoints, verify injection in HTML responses and proxy forwarding to a mock backend.

---

## Repository 2: obsidian-agent (Python)

### Purpose

A standalone Python HTTP service that executes LLM-driven vault operations. It receives instructions via synchronous HTTP endpoints, runs the agent loop, commits changes via Jujutsu, and returns the result.

### What obsidian-agent owns

| Concern | How |
|---------|-----|
| LLM agent loop | OpenAI-compatible tool-calling via `openai` SDK |
| Vault tool definitions + execution | `ToolRuntime` with read/write/list/search/fetch/undo tools |
| Vault filesystem safety | Path validation, atomic writes, per-file locks, protected dirs |
| VCS operations | `JujutsuHistory` wrapper (commit, undo, log, diff) |
| HTTP API | FastAPI app with `/api/apply`, `/api/undo`, `/api/health` |
| URL-to-file resolution | `resolve_page_path()` maps URL paths to vault markdown files |

### What obsidian-agent does NOT own

- HTML generation, site serving, overlay injection — that's Forge.
- Process supervision, unified configuration, demo workflows — that's obsidian-ops.
- Anything related to Kiln, static sites, or the browser UI.

### Architectural boundary

obsidian-agent is a standalone process. It exposes HTTP endpoints and operates on the vault directory it's configured to use. It has no knowledge of Forge, Kiln, or the static site.

The agent's only external communication is:
- **Inbound**: HTTP requests on its configured port.
- **Outbound**: LLM API calls to the configured vLLM/OpenAI-compatible endpoint.
- **Local**: Filesystem operations on the vault, `jj` subprocess calls.

obsidian-ops starts it as a subprocess and passes configuration via `AGENT_*` environment variables.

### File structure

```
obsidian-agent/
├── src/obsidian_agent/
│   ├── __init__.py
│   ├── __main__.py           # uvicorn entry point
│   ├── app.py                # FastAPI app with /api/apply, /api/undo, /api/health
│   ├── config.py             # AgentSettings (AGENT_ env prefix)
│   ├── models.py             # Request/response Pydantic models
│   ├── agent.py              # Agent class + AgentRunner protocol
│   ├── tools.py              # ToolRuntime + tool definitions
│   ├── vcs.py                # JujutsuHistory (renamed from history_jj.py)
│   ├── fs_atomic.py          # Atomic writes, path validation, protected dirs
│   ├── locks.py              # Per-file asyncio lock manager
│   └── page_context.py       # URL path → vault file resolution
├── tests/
│   ├── test_app.py           # Endpoint tests
│   ├── test_agent.py         # Agent loop tests (mocked LLM)
│   ├── test_tools.py         # Tool execution tests
│   ├── test_vcs.py           # Jujutsu wrapper tests
│   ├── test_fs_atomic.py     # File safety tests
│   ├── test_locks.py         # Lock manager tests
│   ├── test_page_context.py  # URL resolution tests
│   └── test_config.py        # Settings validation tests
├── pyproject.toml
└── devenv.nix
```

### Module details

#### `config.py` — Agent settings

```python
class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", extra="ignore")

    vault_dir: Path               # Required. Must exist.
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_model: str = "local-model"
    vllm_api_key: str = ""
    jj_bin: str = "jj"
    host: str = "127.0.0.1"
    port: int = 8081
    max_tool_iterations: int = 12
    max_search_results: int = 12
    page_url_prefix: str = "/"
    operation_timeout_s: int = 120  # Hard timeout for entire apply operation
```

Notably absent vs. current `Settings`: `site_dir`, `kiln_bin`, `kiln_timeout_s`, `workers`. The agent does not know about Kiln or the static site.

#### `models.py` — Simplified data models

The SSE-oriented models (`Job`, `JobStatus`, `SSEEvent`, `JobRequest`, `JobResponse`) are replaced with a simpler request/response contract:

```python
class ApplyRequest(BaseModel):
    instruction: str
    current_url_path: str
    current_file_path: str | None = None

class OperationResult(BaseModel):
    ok: bool
    updated: bool
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    warning: str | None = None
    error: str | None = None
```

`OperationResult` is used for both `/api/apply` and `/api/undo` responses. No `Job`, `JobStatus`, `JobQueue`, `SSEBroadcaster`, or `SSEEvent` models.

#### `app.py` — FastAPI application

Dramatically simpler than the current `app.py`. No background worker, no SSE streaming, no static file mounts, no clean URL middleware.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_agent_settings()
    jj = JujutsuHistory(settings.vault_dir, settings.jj_bin)
    await jj.ensure_workspace()
    lock_manager = FileLockManager()
    tool_runtime = ToolRuntime(settings, lock_manager, jj)
    agent = Agent(settings, tool_runtime)

    app.state.settings = settings
    app.state.agent = agent
    app.state.jj = jj
    app.state.tool_runtime = tool_runtime
    yield


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/apply", response_model=OperationResult)
async def apply_instruction(request: ApplyRequest):
    # Resolve file path from URL
    # Reset tool runtime
    # Run agent.run() inline (with timeout)
    # If changed_files: jj.commit()
    # Return OperationResult


@app.post("/api/undo", response_model=OperationResult)
async def undo():
    # jj.undo() (with timeout)
    # Return OperationResult with updated=true
```

The `/api/apply` handler runs the entire operation synchronously within the request:

1. Resolve `current_url_path` → vault file path via `resolve_page_path()`.
2. Call `agent.run(instruction, file_path, on_progress)` where `on_progress` is a no-op (or a simple logger).
3. If `changed_files` is non-empty, call `jj.commit(f"ops: {instruction[:80]}")`.
4. Return `OperationResult(ok=True, updated=len(changed_files) > 0, ...)`.
5. Wrap the entire operation in `asyncio.wait_for()` with `operation_timeout_s`.

Error handling:
- LLM call failure → `ok=false, error="LLM call failed: ..."`
- Tool execution failure → `ok=false, error="Tool 'X' failed: ..."`
- Commit failure after changes → `ok=false, error="Files changed but commit failed..."`
- Timeout → `ok=false, error="Operation timed out after 120s"`

#### `agent.py` — Agent loop with protocol

The `Agent` class is carried over from the current codebase with minimal changes:

1. **Add `AgentRunner` protocol** — a single-method interface that documents the swap point:

```python
class AgentRunner(Protocol):
    async def run(
        self,
        instruction: str,
        file_path: str | None,
        on_progress: Callable[[str], Awaitable[None]],
    ) -> dict: ...
```

Note: `on_progress` takes a plain `str` message instead of `SSEEvent`. The agent doesn't need to know about event types — it just logs progress text. The `app.py` handler ignores these for MVP (or logs them server-side).

2. **The `Agent` class satisfies `AgentRunner` structurally.** No inheritance needed.

3. **Remove SSEEvent import** — progress callback takes `str`, not `SSEEvent`.

The rest of the agent loop (system prompt, tool-calling iteration, iteration cap) is unchanged from the current implementation.

#### `tools.py` — Tool runtime (unchanged)

Carried over verbatim from current `tools.py`. The `ToolRuntime` class and `get_tool_definitions()` function remain the same. This includes all seven tools:

- `read_file` — read vault-relative path (validates path, checks size via `fs_atomic`)
- `write_file` — atomic write with per-file lock (tracks `changed_files`)
- `list_files` — glob vault for file paths
- `search_files` — case-insensitive substring search with context snippets
- `fetch_url` — HTTP fetch with 120KB limit
- `undo_last_change` — delegates to `jj undo`
- `get_file_history` — delegates to `jj log`

Import paths change from `obsidian_ops.*` to `obsidian_agent.*`.

#### `vcs.py` — Jujutsu wrapper (renamed)

Carried over from current `history_jj.py` with only the file rename and import path change. The `JujutsuHistory` class is used directly — no `VCSAdapter` protocol for MVP.

Methods: `ensure_workspace()`, `commit()`, `undo()`, `log_for_file()`, `diff_for_file()`.

#### `fs_atomic.py`, `locks.py`, `page_context.py` — Foundation modules (verbatim)

These three modules have zero internal dependencies and are copied unchanged:

- `fs_atomic.py`: `read_file_safe()`, `write_file_atomic()`, `validate_vault_path()`, constants (`MAX_FILE_SIZE_BYTES`, `PROTECTED_DIRS`)
- `locks.py`: `FileLockManager` with per-file `asyncio.Lock` keyed by resolved path
- `page_context.py`: `resolve_page_path()` mapping URL paths to `.md` file candidates

### What gets deleted (not migrated)

These exist in the current monolith but are not carried into obsidian-agent:

| Current code | Why it's gone |
|--------------|---------------|
| `queue.py` — `JobQueue`, `SSEBroadcaster`, `run_worker()` | Replaced by synchronous inline execution |
| `models.py` — `Job`, `JobStatus`, `SSEEvent`, `JobRequest`, `JobResponse` | Replaced by `ApplyRequest` + `OperationResult` |
| `inject.py` — `inject_overlay()` | Moved to Forge (Go) |
| `rebuild.py` — `KilnRebuilder` | Replaced by Forge's `kiln dev` |
| `app.py` — `rewrite_clean_urls`, static mounts, SSE streaming route | Forge handles serving; SSE eliminated |

### Dependencies

```toml
[project]
name = "obsidian-agent"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.12.5",
    "pydantic-settings>=2.0.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
    "openai>=1.60.0",
    "httpx>=0.28.0",
]
```

No `typer` (CLI is in obsidian-ops). No Kiln-related dependencies.

### Testing strategy

- **test_app.py**: Test `/api/apply`, `/api/undo`, `/api/health` with mocked agent and VCS. Verify `OperationResult` shape for success, no-op, failure, and timeout cases.
- **test_agent.py**: Test agent loop with mocked `openai.AsyncOpenAI`. Verify tool dispatch, iteration cap, progress callback.
- **test_tools.py**: Test each tool against a temporary vault directory.
- **test_vcs.py**: Test `JujutsuHistory` with mocked subprocess calls.
- **test_fs_atomic.py**, **test_locks.py**, **test_page_context.py**: Carried over from current test suite with import path changes.

---

## Repository 3: obsidian-ops (Python)

### Purpose

A thin CLI that starts Forge and obsidian-agent as subprocesses, passes configuration to each, and provides demo workflows. This is the user-facing entry point.

### What obsidian-ops owns

| Concern | How |
|---------|-----|
| Unified configuration | Single `OpsSettings` model, split into Forge flags + agent env vars |
| Process supervision | Start Forge + agent, wait for health, handle exit |
| CLI interface | Typer commands: `dev`, `demo run`, `demo cleanup` |
| Demo workflow | Prepare runtime vault, validate vLLM, start everything |

### What obsidian-ops does NOT own

- Agent execution, vault tools, LLM interaction — that's obsidian-agent.
- Site generation, serving, overlay injection — that's Forge.
- Vault content or VCS operations — those are agent-side concerns.

### Architectural boundary

obsidian-ops never imports obsidian-agent at the Python level. The agent is a subprocess — a separate Python process started with `python -m obsidian_agent`. Communication is exclusively via:

- **To agent**: `AGENT_*` environment variables (configuration) and HTTP (health checks).
- **To Forge**: CLI arguments (configuration) and process lifecycle (start/stop/exit code).

This is the strongest possible boundary: no shared Python imports, no shared memory, no in-process coupling.

### File structure

```
obsidian-ops/
├── src/obsidian_ops/
│   ├── __init__.py
│   ├── __main__.py            # Typer CLI entry point
│   ├── config.py              # OpsSettings (OPS_ env prefix)
│   ├── supervisor.py          # Process management for Forge + agent
│   └── demo_cli.py            # Demo workflow (adapted from current)
├── tests/
│   ├── test_config.py         # Settings validation + split logic
│   ├── test_supervisor.py     # Process management tests (mocked subprocesses)
│   └── test_demo_cli.py       # Demo workflow tests (adapted from current)
├── demo/
│   └── obsidian-ops/
│       ├── vault/             # Demo Obsidian vault (existing)
│       └── README.md
├── pyproject.toml
└── devenv.nix
```

### Module details

#### `config.py` — Unified settings

```python
class OpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPS_", extra="ignore")

    # Shared
    vault_dir: Path                              # Required. Passed to both Forge and agent.
    site_dir: Path                               # Required. Passed to Forge only.

    # Forge
    forge_bin: str = "forge"
    forge_port: int = 8080

    # Agent
    agent_host: str = "127.0.0.1"
    agent_port: int = 8081
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_model: str = "local-model"
    vllm_api_key: str = ""
    jj_bin: str = "jj"
    max_tool_iterations: int = 12
    max_search_results: int = 12
    page_url_prefix: str = "/"

    # Server
    host: str = "127.0.0.1"
    port: int = 8080                             # Alias for forge_port (user-facing)
```

The orchestrator splits this into:

- **Forge CLI args**: `--input {vault_dir} --output {site_dir} --port {forge_port} --proxy-backend http://{agent_host}:{agent_port} --overlay-dir {overlay_path} --inject-overlay`
- **Agent env vars**: `AGENT_VAULT_DIR={vault_dir}`, `AGENT_VLLM_BASE_URL=...`, `AGENT_VLLM_MODEL=...`, etc.

#### `supervisor.py` — Process management

```python
class ProcessSupervisor:
    """Start, monitor, and stop Forge and obsidian-agent."""

    async def start_agent(self, settings: OpsSettings) -> asyncio.subprocess.Process:
        """Spawn `python -m obsidian_agent` with AGENT_* env vars."""

    async def start_forge(self, settings: OpsSettings) -> asyncio.subprocess.Process:
        """Spawn `forge dev ...` with CLI args derived from settings."""

    async def wait_for_health(self, url: str, timeout: float = 30.0) -> None:
        """Poll GET /api/health until 200 OK or timeout."""

    async def run(self, settings: OpsSettings) -> None:
        """
        1. Start agent subprocess.
        2. Wait for agent health check to pass.
        3. Start Forge subprocess.
        4. Wait for either process to exit.
        5. If either exits, kill the other and propagate exit code.
        """
```

Startup sequence matters: the agent must be healthy before Forge starts, because Forge will immediately begin proxying `/api/*` requests.

For MVP, crash handling is simple: if either process exits, the supervisor kills the other and exits with an error. No restart logic.

#### `__main__.py` — CLI entry point

```python
app = typer.Typer()

@app.command()
def dev(vault_dir: Path, site_dir: Path, ...):
    """Start Forge + agent for development."""
    settings = OpsSettings(vault_dir=vault_dir, site_dir=site_dir, ...)
    supervisor = ProcessSupervisor()
    asyncio.run(supervisor.run(settings))
```

#### `demo_cli.py` — Demo workflow

Adapted from the current `demo_cli.py`. Key changes:

- `_run_server()` calls `ProcessSupervisor.run()` instead of `uvicorn.run()`.
- `_prepare_runtime_vault()` unchanged (copy vault, `jj git init`).
- `_resolve_vllm_model()` unchanged (query `/v1/models`, select model).
- Environment variable prefix changes from `OPS_` to the appropriate splits.

### Dependencies

```toml
[project]
name = "obsidian-ops"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "typer>=0.12.0",
    "httpx>=0.28.0",
    "pydantic>=2.12.5",
    "pydantic-settings>=2.0.0",
]

[project.scripts]
ops = "obsidian_ops.__main__:app"
ops-demo = "obsidian_ops.demo_cli:main"
```

No `fastapi`, `uvicorn`, or `openai` — those are agent dependencies. No Go — Forge binary is expected in PATH.

### `devenv.nix` updates

```nix
# Replace kiln input with forge
inputs.forge.url = "github:YOUR_ORG/forge/v0.1.0";

# Packages
packages = [
    pkgs.git
    pkgs.jujutsu
    inputs.forge.packages.${pkgs.system}.default
    # obsidian-agent expected to be installed in the Python venv
];
```

### Testing strategy

- **test_config.py**: Verify `OpsSettings` validation, Forge arg generation, agent env var generation.
- **test_supervisor.py**: Test process start/stop lifecycle with mocked `asyncio.create_subprocess_exec`. Test health check polling with a mock HTTP server.
- **test_demo_cli.py**: Adapted from current tests. Verify vault preparation, vLLM preflight, environment variable propagation.

---

## Migration from current code

### Module mapping

| Current monolith file | Destination | Changes |
|-----------------------|-------------|---------|
| `agent.py` | obsidian-agent `agent.py` | Add `AgentRunner` protocol. Change `on_progress` from `SSEEvent` to `str`. Update imports. |
| `tools.py` | obsidian-agent `tools.py` | Update imports only. |
| `fs_atomic.py` | obsidian-agent `fs_atomic.py` | Verbatim copy. |
| `locks.py` | obsidian-agent `locks.py` | Verbatim copy. |
| `page_context.py` | obsidian-agent `page_context.py` | Verbatim copy. |
| `history_jj.py` | obsidian-agent `vcs.py` | Rename file. Update imports. |
| `config.py` | obsidian-agent `config.py` + obsidian-ops `config.py` | Split into `AgentSettings` (AGENT_ prefix) and `OpsSettings` (OPS_ prefix). |
| `models.py` | obsidian-agent `models.py` | Replace with `ApplyRequest` + `OperationResult`. Delete `Job`, `JobStatus`, `SSEEvent`, etc. |
| `app.py` | obsidian-agent `app.py` | Rewrite: keep only `/api/apply`, `/api/undo`, `/api/health`. Remove all static mounts, middleware, SSE. |
| `queue.py` | **Deleted** | Entire file eliminated. Inline execution replaces queue+worker+broadcaster. |
| `inject.py` | Forge `internal/overlay/inject.go` | Rewritten in Go as HTTP middleware. |
| `rebuild.py` | **Deleted** | Replaced by Forge's `kiln dev` file watcher. |
| `static/ops.js` | Forge `static/ops.js` | Simplify: remove `EventSource`/SSE handling. Replace with synchronous `fetch` + result display. |
| `static/ops.css` | Forge `static/ops.css` | Copy verbatim. |
| `demo_cli.py` | obsidian-ops `demo_cli.py` | Adapt to use `ProcessSupervisor`. |
| `__main__.py` | obsidian-ops `__main__.py` + obsidian-agent `__main__.py` | Split into orchestrator CLI and agent uvicorn entry. |

### Test mapping

| Current test | Destination | Changes |
|--------------|-------------|---------|
| `test_api.py` | obsidian-agent `test_app.py` | Rewrite for new endpoints. No SSE, no static mounts. |
| `test_queue.py` | **Deleted** | Queue eliminated. |
| `test_inject.py` | Forge Go tests | Logic reimplemented in Go. |
| `test_fs_atomic.py` | obsidian-agent `test_fs_atomic.py` | Update imports only. |
| `test_history_jj.py` | obsidian-agent `test_vcs.py` | Rename, update imports. |
| `test_locks.py` | obsidian-agent `test_locks.py` | Update imports only. |
| `test_page_context.py` | obsidian-agent `test_page_context.py` | Update imports only. |
| `test_config.py` | Both repos | Split for `AgentSettings` and `OpsSettings`. |
| `test_demo_cli.py` | obsidian-ops `test_demo_cli.py` | Adapt for new architecture. |

### Overlay JS simplification

The current `ops.js` (270 lines) uses `EventSource` for SSE streaming. The simplified version replaces the stream listener with a single `fetch`:

```javascript
// Current (SSE):
const response = await fetch("/api/jobs", { method: "POST", body: ... });
const { job_id } = await response.json();
const source = new EventSource(`/api/jobs/${job_id}/stream`);
source.addEventListener("status", ...);
source.addEventListener("tool", ...);
source.addEventListener("done", ...);

// Simplified (synchronous):
const response = await fetch("/api/apply", { method: "POST", body: ... });
const result = await response.json();
if (result.ok && result.updated) { showSuccess("Updated — refresh to see changes."); }
if (result.ok && !result.updated) { showSuccess("No changes made."); }
if (!result.ok) { showError(result.error); }
```

This eliminates: `openSse()`, `closeSource()`, `parseEventData()`, all `EventSource` event listeners, the `state.source` tracking, and stream interruption handling.

---

## Implementation phases

### Phase 1: obsidian-agent (Python)

**Can start immediately. No dependencies on Forge.**

1. Create new repo with `pyproject.toml`, `devenv.nix`.
2. Copy foundation modules verbatim: `fs_atomic.py`, `locks.py`, `page_context.py`.
3. Rename + copy `history_jj.py` → `vcs.py`.
4. Copy `tools.py`, update imports.
5. Adapt `agent.py`: add `AgentRunner` protocol, change progress callback to `str`.
6. Write new `models.py` with `ApplyRequest` + `OperationResult`.
7. Write new `config.py` with `AgentSettings`.
8. Write new `app.py` with synchronous `/api/apply`, `/api/undo`, `/api/health`.
9. Write `__main__.py` (uvicorn entry).
10. Migrate and adapt tests.

**Testable independently**: Run `python -m obsidian_agent` with a test vault. Curl `/api/health`, `/api/apply`, `/api/undo` directly.

### Phase 2: Forge (Go fork) — parallel with Phase 1

**Can start immediately. No dependencies on obsidian-agent.**

1. Fork Kiln v0.9.5 into new `forge` repo.
2. Implement HTML injection middleware.
3. Implement reverse proxy handler.
4. Implement overlay static file serving.
5. Wire new handlers into the `dev` command with new CLI flags.
6. Copy `ops.css` + simplified `ops.js` into `static/`.
7. Write Go tests.

**Testable independently**: Run `forge dev` against the demo vault. Verify injection in browser. Verify proxy forwarding to a mock HTTP server.

### Phase 3: obsidian-ops orchestrator

**Requires Phase 1 + 2 to be functional.**

1. Gut current `src/obsidian_ops/` — delete all agent/tool/queue/inject/rebuild code.
2. Write new `config.py` with `OpsSettings`.
3. Write `supervisor.py` with process management.
4. Write new `__main__.py` with Typer CLI.
5. Adapt `demo_cli.py` for new architecture.
6. Update `devenv.nix` to reference Forge instead of Kiln.
7. Write tests.

### Phase 4: Integration verification

1. `ops dev --vault-dir ./demo/obsidian-ops/vault --site-dir ./gen/site` starts everything.
2. Open browser → see Kiln-rendered site with injected overlay.
3. Submit instruction → synchronous response → "Updated — refresh."
4. Refresh → see changes.
5. Click Undo → synchronous response → "Undone — refresh."
6. `ops-demo run` works end-to-end with vLLM backend.

---

## Known risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Rebuild timing**: Forge's watcher hasn't rebuilt when user refreshes | User sees stale page | Acceptable for MVP. User refreshes again. Kiln rebuild is typically sub-second for small vaults. |
| **Long-running requests**: Agent loop takes >30s, browser or proxy times out | User sees generic timeout error | Agent enforces 120s hard timeout. Forge proxy uses 180s timeout. Both return clear error messages. |
| **Two processes to manage**: Either Forge or agent crashes | System partially down | Supervisor kills both on any exit. User restarts `ops dev`. No auto-restart for MVP. |
| **Agent port exposed on network**: Agent listens on 8081 | Unintended access | Bind to 127.0.0.1 by default. On tailnet, all ports are effectively trusted. |
| **Forge fork maintenance**: Upstream Kiln updates | Fork diverges | Forge additions are isolated in `internal/overlay/` and `internal/proxy/`. Kiln core code untouched. Clean merge path. |
