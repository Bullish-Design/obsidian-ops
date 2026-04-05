# Refactor obsidian-ops into three repositories

## Context

obsidian-ops is currently a single Python package that tightly couples three concerns: static site serving/UI injection, LLM agent execution with vault tools, and rebuild/versioning orchestration. We want to split it into three repos with enforced boundaries to enable independent development and future flexibility (e.g., swapping agent frameworks). This is an MVP for a single developer on a private tailnet — no auth, no over-engineering.

## Target repositories

| Repo | Language | Purpose |
|------|----------|---------|
| **forge** | Go | Fork of Kiln v0.9.5. Adds response-time HTML injection, `/api/*` reverse proxy to agent, overlay asset serving. Primary `dev` command = build + watch + serve + inject + proxy. |
| **obsidian-agent** | Python | Vault agent service. FastAPI HTTP API for jobs/SSE. Contains agent loop, vault tools, VCS adapter, job queue. Runs as standalone process on its own port. |
| **obsidian-ops** | Python | Thin orchestrator CLI. Starts Forge + agent as subprocesses, manages config, provides demo workflow. |

## Shared API contract

The contract between Forge (proxy) and obsidian-agent (backend):

```
POST   /api/jobs              → { instruction, current_url_path, current_file_path? } → { job_id }
GET    /api/jobs/{id}/stream  → text/event-stream (types: status, tool, result, error, done)
GET    /api/jobs?limit=N      → Job[]
POST   /api/undo              → { job_id }
GET    /api/history            → string[]
GET    /api/health             → { status: "ok" }
```

SSE event payload: `{ type, message, payload }` (unchanged from current `SSEEvent` model).

---

## Phase 1: Create obsidian-agent repo

Extract the agent service into a standalone package with its own HTTP API.

### Files to create (new repo: `obsidian-agent`)

```
obsidian-agent/
├── src/obsidian_agent/
│   ├── __init__.py
│   ├── __main__.py          # uvicorn entry point
│   ├── app.py               # FastAPI app — API routes only, no static mounts
│   ├── config.py            # AgentSettings with AGENT_ env prefix
│   ├── models.py            # ← from obsidian_ops/models.py (verbatim)
│   ├── agent.py             # ← from obsidian_ops/agent.py + AgentRunner protocol
│   ├── tools.py             # ← from obsidian_ops/tools.py
│   ├── queue.py             # ← from obsidian_ops/queue.py (remove rebuild/inject coupling)
│   ├── vcs.py               # ← from obsidian_ops/history_jj.py + VCSAdapter protocol
│   ├── fs_atomic.py         # ← from obsidian_ops/fs_atomic.py (verbatim)
│   ├── locks.py             # ← from obsidian_ops/locks.py (verbatim)
│   └── page_context.py      # ← from obsidian_ops/page_context.py (verbatim)
├── tests/                   # ← migrate relevant tests from obsidian-ops
├── pyproject.toml           # deps: fastapi, uvicorn, openai, httpx, pydantic, pydantic-settings
└── devenv.nix               # Python 3.13, jujutsu
```

### Key changes from current code

1. **`config.py`**: New `AgentSettings` with `AGENT_` prefix. Drops `site_dir`, `kiln_bin`, `kiln_timeout_s` — the agent doesn't know about the static site.

2. **`app.py`**: Slimmed-down FastAPI app. Keeps all `/api/*` routes from current `app.py`. Removes:
   - `rewrite_clean_urls` middleware (Forge handles clean URLs)
   - Static file mounts (`/ops`, `/`)
   - `inject_overlay` call
   - `KilnRebuilder` instantiation

3. **`queue.py`**: Decouple from rebuild/inject. Replace direct `rebuilder.rebuild()` + `injector()` calls with an optional `PostChangeHook` callback. The worker loop becomes: run agent → commit if changed → call hook → done.

4. **`agent.py`**: Add `AgentRunner` protocol (Python `Protocol` class). Current `Agent` class satisfies it structurally. This is the swap point for future framework adoption.

   ```python
   class AgentRunner(Protocol):
       async def run(self, instruction: str, file_path: str | None,
                     on_progress: Callable[[SSEEvent], Awaitable[None]]) -> dict: ...
   ```

5. **`vcs.py`**: Add `VCSAdapter` protocol. `JujutsuHistory` implements it. Rename file from `history_jj.py`.

   ```python
   class VCSAdapter(Protocol):
       async def ensure_workspace(self) -> None: ...
       async def commit(self, message: str) -> str: ...
       async def undo(self) -> str: ...
       async def log_for_file(self, path: str, limit: int = 10) -> list[str]: ...
   ```

6. **All imports**: Change from `obsidian_ops.*` to `obsidian_agent.*`.

### Tests to migrate
- `test_queue.py`, `test_fs_atomic.py`, `test_locks.py`, `test_page_context.py`, `test_config.py` → copy, update imports
- `test_history_jj.py` → `test_vcs.py`, update imports
- `test_api.py` → simplify (no static mounts, no rebuild mocking)
- `test_inject.py` → **delete** (injection moves to Forge)

### Dependencies
- `pydantic>=2.12.5`, `pydantic-settings>=2.0.0`, `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `openai>=1.60.0`, `httpx>=0.28.0`
- NOT `typer` (that stays in obsidian-ops)

---

## Phase 2: Fork Kiln into Forge (parallel with Phase 1)

Fork `github:otaleghani/kiln` at v0.9.5 into a new `forge` repo. Add three capabilities on top of Kiln's existing `dev` command.

### New Go code to add

1. **Response-time HTML injection middleware** (`internal/overlay/inject.go`)
   - `http.Handler` wrapper that buffers HTML responses and injects `<link>` + `<script>` tags before `</head>`
   - Replaces current Python `inject.py` (disk-based rewriting)
   - Must handle Content-Length adjustment and streaming
   - Reference: current injection inserts `<!-- ops-overlay -->` marker + CSS/JS refs before `</head>`

2. **API reverse proxy** (`internal/proxy/reverse.go`)
   - `httputil.ReverseProxy` forwarding `/api/*` to `--proxy-backend` URL
   - Must flush SSE events immediately (use `http.Flusher` interface)
   - Preserves headers, query params, request body

3. **Overlay static file serving**
   - Serves `/ops/*` from `static/` directory in the Forge repo
   - `ops.css` and `ops.js` copied from current `src/obsidian_ops/static/`

4. **Enhanced `dev` command** — wire the above into Kiln's existing dev server:
   ```
   forge dev \
     --input /path/to/vault \
     --output /path/to/site \
     --proxy-backend http://127.0.0.1:8081 \
     --overlay-dir /path/to/static \
     --inject-overlay \
     --port 8080
   ```

### What current Python code becomes unnecessary
| Python file | Replaced by |
|-------------|-------------|
| `inject.py` | Forge injection middleware |
| `rebuild.py` | Forge's built-in `dev` mode (watch + rebuild) |
| `app.py` `rewrite_clean_urls` | Kiln's existing clean URL handling |
| `app.py` static mount for `/ops` | Forge overlay serving |
| `app.py` static mount for `/` | Forge's built-in site serving |

### Testing
- Go unit tests for injection middleware (synthetic HTML responses)
- Go unit tests for reverse proxy (httptest)
- Integration test: run `forge dev` against a small test vault

---

## Phase 3: Slim down obsidian-ops to orchestrator

Replace the current monolith code with a thin CLI that starts Forge + agent as subprocesses.

### New file structure for obsidian-ops

```
obsidian-ops/
├── src/obsidian_ops/
│   ├── __init__.py
│   ├── __main__.py          # Typer CLI entry point
│   ├── config.py            # OpsSettings with OPS_ prefix (unified config)
│   ├── supervisor.py        # Process management for Forge + agent
│   └── demo_cli.py          # Adapted demo workflow
├── tests/
│   ├── test_config.py
│   ├── test_supervisor.py
│   └── test_demo_cli.py     # Adapted from current
├── pyproject.toml            # deps: typer, httpx, pydantic, pydantic-settings
└── devenv.nix                # Python 3.13, jujutsu, forge binary
```

### Files deleted from obsidian-ops
Everything that moved to obsidian-agent or forge: `app.py`, `agent.py`, `tools.py`, `queue.py`, `models.py`, `fs_atomic.py`, `locks.py`, `history_jj.py`, `rebuild.py`, `inject.py`, `page_context.py`, `static/ops.css`, `static/ops.js`.

### Key new components

1. **`config.py`** — `OpsSettings` with `OPS_` prefix. Contains all settings, split at runtime into Forge CLI flags and agent env vars:
   - Forge: `vault_dir`, `site_dir`, `forge_bin`, `forge_port`, `overlay_dir`
   - Agent: `vault_dir`, `vllm_base_url`, `vllm_model`, `vllm_api_key`, `jj_bin`, `agent_host`, `agent_port`, `max_tool_iterations`, `max_search_results`

2. **`supervisor.py`** — `ProcessSupervisor` class:
   - `start_agent()` → spawns `python -m obsidian_agent` with `AGENT_*` env vars
   - `start_forge()` → spawns `forge dev --input ... --output ... --proxy-backend http://{agent_host}:{agent_port} ...`
   - `wait_for_health(url)` → polls `/api/health` until agent is ready
   - `run()` → start agent, wait for health, start Forge, wait for either to exit

3. **`__main__.py`** — Typer CLI with `dev` command (and adapted demo commands)

4. **`demo_cli.py`** — Adapted from current. `_run_server()` calls supervisor instead of uvicorn directly. vLLM preflight logic stays.

### Dependencies
- `typer>=0.12.0`, `httpx>=0.28.0`, `pydantic>=2.12.5`, `pydantic-settings>=2.0.0`
- obsidian-agent is NOT a Python import dependency — it's a subprocess
- Forge binary expected in PATH (provided by devenv.nix)

---

## Phase 4: Integration testing and cutover

1. **End-to-end smoke test**: `obsidian-ops dev --vault-dir ./test-vault` starts both processes. Forge serves site with injected overlay. Submitting a job via the FAB routes through Forge's proxy to the agent, SSE streams back, vault files change, Forge's watcher triggers rebuild.

2. **Specific checks**:
   - Forge proxy correctly forwards POST/GET/SSE to agent
   - Forge injection adds overlay tags to every HTML response
   - Agent commits via jj after changes → Forge file watcher picks up changes → rebuild
   - Undo flow works end-to-end
   - Demo workflow (`ops-demo run`) works

3. **Tag the old monolith commit** for reference before removing code.

---

## Sequencing

```
Phase 1 (agent library)  ──┐
                            ├── Phase 3 (orchestrator) ── Phase 4 (integration)
Phase 2 (Forge/Go fork)  ──┘
```

Phases 1 and 2 are independent and can be developed in parallel. Phase 3 requires both to be functional. Phase 4 is the final verification.

---

## Known risks and mitigations

| Risk | Mitigation |
|------|-----------|
| **Rebuild timing**: Agent commits, but Forge's file watcher hasn't rebuilt yet when "done" SSE fires | MVP: user clicks Refresh. Later: agent could signal Forge via webhook. |
| **SSE through reverse proxy**: Go's ReverseProxy may buffer SSE events | Use `http.Flusher` interface to flush per-event. Well-documented pattern. |
| **Process crash handling**: Either subprocess dies | MVP: supervisor exits with error if either dies. No restart logic needed yet. |
| **Two ports during dev**: Agent on 8081, Forge on 8080 | Browser only talks to Forge (8080). Agent port is internal. Supervisor manages both. |

## Verification plan

1. **obsidian-agent**: `pytest` with mocked VCS/LLM against a test vault. Can also `python -m obsidian_agent` and curl the API directly.
2. **forge**: `go test ./...` for unit tests. Manual `forge dev` against demo vault to verify injection + proxy.
3. **obsidian-ops**: `pytest` for config/supervisor. `ops-demo run` for full end-to-end.
