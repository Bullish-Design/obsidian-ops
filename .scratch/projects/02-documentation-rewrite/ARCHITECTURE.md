# Obsidian Ops — Architecture

## 1. Purpose

This document defines the architecture for Obsidian Ops v0: a local-first, agent-driven operations overlay for an Obsidian vault rendered through Kiln, with Jujutsu-backed durable history.

The central design rule:

> The vault files are canonical.
> The app is a thin local runtime around them.
> Jujutsu is the durable recovery layer.

---

## 2. System overview

```text
Browser
  |-- Kiln-rendered vault pages
  |-- injected ops.js + ops.css
        |
        | POST /api/jobs
        | GET  /api/jobs/{job_id}/stream
        v
FastAPI (single process, bound to 127.0.0.1)
  |-- site mount: /           --> generated site
  |-- ops mount: /ops/        --> FAB + modal assets
  |-- API routes: /api/*      --> jobs, undo, history
  |-- in-memory queue         --> worker task
  |-- agent loop              --> vLLM tool-use
  |-- vault/file helpers      --> atomic writes, locks
  |-- Jujutsu wrapper         --> commit, undo, history
  |-- Kiln wrapper            --> rebuild
        |
        |-- Obsidian vault (markdown files)
        |-- Jujutsu workspace (.jj/)
        |-- Generated site output
```

The architecture is intentionally flat. Six logical layers in one process.

---

## 3. Architectural drivers

### 3.1 Files are canonical

Markdown files in the vault are the real product state. Everything else — generated site output, job state, streamed progress, search results — is derived.

### 3.2 Direct mutation is the value proposition

The user describes a change in natural language. The agent performs it against the vault. This is what the product does.

### 3.3 Recovery is mandatory

Every successful write must be attributable and reversible. Jujutsu provides this without the app building its own durability mechanism.

### 3.4 Simplicity is a product requirement

The system must stay small in both implementation and mental model. Resist architecture growth that adds abstraction without immediate product value.

### 3.5 The modal is the product surface

One interaction point. No command tree, no toolbar ecosystem, no dashboard.

---

## 4. Component boundaries

### 4.1 App layer (`app.py`)

- HTTP route definitions
- SSE streaming
- Static file mounts (site + overlay assets)
- Job admission (creates jobs, wires runners)
- Lifespan management (startup checks, worker lifecycle)

### 4.2 Queue layer (`queue.py`)

- In-memory job storage
- FIFO worker loop
- Job lifecycle transitions (queued -> running -> succeeded/failed)
- SSE subscriber management
- Progress event publishing

### 4.3 Agent layer (`agent.py`)

- System prompt construction
- Tool-use loop against vLLM (OpenAI-compatible API)
- Tool call dispatch
- Final summary extraction
- Progress emission

### 4.4 Tool layer (`tools.py`)

- File read/write/list/search
- URL fetching
- History and undo delegation to Jujutsu wrapper
- Path validation (vault-root enforcement)
- Tracking of changed/created files per job

### 4.5 History wrapper (`history_jj.py`)

- `jj commit` for change boundaries
- `jj undo` for recovery
- `jj log` for file history
- `jj diff` for change inspection
- Workspace existence validation

### 4.6 Rebuild wrapper (`rebuild.py`)

- `kiln generate` execution
- Failure surfacing

### 4.7 Supporting modules

- `config.py` — Settings model, environment variable loading
- `models.py` — Pydantic models for jobs, events, requests
- `locks.py` — Per-file async lock management
- `fs_atomic.py` — Atomic write-by-replace, safe reads
- `page_context.py` — URL-to-markdown-path resolution
- `inject.py` — Post-build overlay injection into HTML pages

### 4.8 Browser overlay (`static/ops.js`, `static/ops.css`)

- FAB rendering
- Modal rendering and lifecycle
- Job submission (`POST /api/jobs`)
- SSE subscription and progress display
- Refresh and undo actions
- HTMX page-swap tolerance

---

## 5. Data flow: successful mutation

```text
1. Browser: POST /api/jobs {instruction, current_url_path}
2. App: resolve URL -> vault-relative markdown path
3. App: create in-memory job, enqueue
4. Queue: worker picks up job
5. Agent: receive system prompt + instruction + page context + tools
6. Agent: [loop] call tools -> read files, search, fetch URLs
7. Agent: [loop] call write_file -> acquire lock, atomic write, release lock
8. Agent: return final summary with changed/created file lists
9. App: jj commit -m "ops: <instruction>"     [via asyncio.to_thread]
10. App: kiln generate --input <vault> --output <site>  [via asyncio.to_thread]
11. App: inject overlay into rebuilt HTML pages
12. Queue: publish "done" event to SSE subscribers
13. Browser: display summary, refresh button, undo button
```

---

## 6. Data flow: undo

```text
1. Browser: POST /api/undo
2. App: create undo job, enqueue
3. Queue: worker picks up job
4. Runner: jj undo                            [via asyncio.to_thread]
5. Runner: kiln generate                      [via asyncio.to_thread]
6. Runner: inject overlay
7. Queue: publish "done" event
8. Browser: display success, refresh button
```

---

## 7. State classification

### 7.1 Durable state

| State | Location | Survives restart |
|-------|----------|-----------------|
| Vault markdown files | Filesystem | Yes |
| Jujutsu history | `.jj/` | Yes |
| Generated site output | `site_dir/` | Yes (regenerable) |

### 7.2 Ephemeral state

| State | Location | Survives restart |
|-------|----------|-----------------|
| In-memory jobs | Process memory | No |
| SSE streams | Process memory | No |
| Modal session state | Browser | No |
| Agent conversation | Process memory | No |
| Per-file locks | Process memory | No |

### 7.3 Restart consequence

On server restart: vault intact, Jujutsu history intact, completed work intact. Queued/running jobs lost. SSE streams interrupted. Initial Kiln rebuild + overlay injection runs on startup.

---

## 8. Concurrency model

### 8.1 Worker count

**One worker. Locked for v0.**

Single-worker concurrency ensures:

- 1:1 mapping between jobs and Jujutsu change boundaries
- Correct `jj undo` semantics (always reverses the last user-visible operation)
- Sequential rebuild ordering
- Simple debugging and reasoning

### 8.2 File locking

Per-file async locks (`asyncio.Lock` per resolved path). Even with one worker, locks protect against:

- Future concurrency increases
- Overlapping tool calls within a single agent turn (if the model issues parallel tool calls)

### 8.3 Lock acquisition

```text
1. Resolve path to absolute
2. Acquire lock for that path
3. Perform operation
4. Release lock
```

Vault-wide operations acquire locks file-by-file in sorted path order to prevent deadlock.

---

## 9. Subprocess execution model

Both Jujutsu and Kiln are invoked as subprocesses. These must not block the async event loop.

### 9.1 Required approach

All subprocess calls must use `asyncio.to_thread()` wrapping `subprocess.run()`, or `asyncio.create_subprocess_exec()` for fully async execution.

### 9.2 Timeouts

| Operation | Default timeout |
|-----------|----------------|
| `jj commit` | 120s |
| `jj undo` | 120s |
| `jj log` | 60s |
| `jj diff` | 120s |
| `kiln generate` | 180s |

---

## 10. Rendering model

### 10.1 Kiln

Kiln renders the vault into a static site. The app serves this site and injects an overlay.

### 10.2 Overlay injection

After each `kiln generate`, `inject.py` scans HTML files in `site_dir` and inserts `<link>` and `<script>` tags for `ops.css` and `ops.js` before `</head>`.

Files already containing the injection marker are skipped.

### 10.3 Rebuild lifecycle

```text
kiln generate --input <vault_dir> --output <site_dir>
inject_overlay(site_dir)
```

Runs after every successful mutation and after every undo. Also runs once at server startup.

### 10.4 Known limitation

Post-build file injection is simple but fragile. A middleware-based injection (at serve time) would be more robust and is a candidate for post-v0 improvement.

---

## 11. API surface

### 11.1 Route map

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serve generated site (static mount, HTML mode) |
| `/ops/*` | GET | Serve overlay assets |
| `/api/health` | GET | Health check |
| `/api/jobs` | GET | List recent jobs |
| `/api/jobs` | POST | Create a new job |
| `/api/jobs/{job_id}/stream` | GET | SSE progress stream |
| `/api/undo` | POST | Undo last change |
| `/api/history` | GET | File history |

### 11.2 Mount order

1. `/ops/` — overlay static assets (must be mounted before site)
2. `/api/*` — API routes
3. `/` — generated site (catch-all static mount with `html=True`)

The site mount is last because it is a catch-all.

---

## 12. Page context resolution

### 12.1 Flow

```text
Browser: location.pathname -> POST /api/jobs {current_url_path: "/notes/foo/"}
Server: "/notes/foo/" -> "notes/foo.md" (if exists) or "notes/foo/index.md"
Agent: receives "notes/foo.md" as current_file_path
```

### 12.2 Heuristic

1. Strip trailing slash, append `.md`, check existence
2. Try `<path>/index.md`
3. Root `/` maps to `index.md`
4. Fail with error if no match

### 12.3 Known limitation

Assumes Kiln URL scheme mirrors vault structure. Replace with Kiln source manifest when available.

---

## 13. Failure and recovery model

### 13.1 Fail before write

- Cause: bad instruction, invalid path, model error, lock timeout
- Effect: no file change, no history entry, job fails with explanation

### 13.2 Fail after write, before commit

- Cause: Jujutsu command failure
- Effect: files are changed on disk but not committed. Severe. Surface clearly.
- Recovery: user can manually inspect and `jj` commit or revert

### 13.3 Fail after commit, before rebuild

- Cause: Kiln generate failure
- Effect: file change is durable in Jujutsu. Site view is stale.
- Recovery: job reports partial success. User can refresh after manual rebuild or retry.

### 13.4 Recovery posture

The product's recovery story:

- Inspect recent history
- Undo the last change
- Restore a prior state if needed

No second snapshot database is needed.

---

## 14. Project structure

```text
obsidian_ops/
  __init__.py
  app.py              # FastAPI app, routes, lifespan
  config.py           # Settings model, env loading
  models.py           # Pydantic models
  queue.py            # In-memory job queue, workers, SSE pub/sub
  agent.py            # Agent loop, system prompt, tool dispatch
  tools.py            # Tool runtime, file ops, path validation
  history_jj.py       # Jujutsu wrapper
  rebuild.py          # Kiln rebuild wrapper
  inject.py           # Post-build overlay injection
  locks.py            # Per-file async locks
  fs_atomic.py        # Atomic file writes
  page_context.py     # URL-to-markdown resolution
  static/
    ops.js            # Browser overlay
    ops.css           # Overlay styles
tests/
  test_atomic.py
  test_page_context.py
  test_queue.py
  test_inject.py
  test_history_jj.py
  test_api.py
```

This is the right scale. Do not introduce command modules, service registries, repository layers, database models, or hybrid persistence adapters.

---

## 15. Dependency map

```text
app.py
  |-- config.py
  |-- models.py
  |-- queue.py
  |-- agent.py
  |   |-- tools.py
  |   |   |-- fs_atomic.py
  |   |   |-- locks.py
  |   |   |-- history_jj.py
  |   |   +-- (httpx for fetch_url)
  |   +-- models.py
  |-- history_jj.py
  |-- rebuild.py
  |-- inject.py
  |-- page_context.py
  +-- (openai SDK for vLLM)
```

No circular dependencies. The agent depends on tools. Tools depend on filesystem and Jujutsu primitives. The app wires everything together.

---

## 16. External dependencies

| Dependency | Purpose | Notes |
|------------|---------|-------|
| Python 3.13+ | Runtime | |
| FastAPI | Web framework | |
| Pydantic | Models, settings, validation | |
| openai (SDK) | vLLM communication | OpenAI-compatible API |
| httpx | Async URL fetching | |
| uvicorn | ASGI server | |
| jj (CLI) | Durable history | Must be installed on system |
| kiln (CLI) | Vault rendering | Must be installed on system |

---

## 17. Non-goals

The following are explicit architectural non-goals for v0:

- SQLite or any database
- Durable queue recovery after restart
- Hybrid history storage
- Git-first history/undo semantics
- Command registries
- Command-specific public API endpoints
- Selection-toolbar UX
- App-owned snapshot systems
- Rich metadata ledgers
- Large service/repository abstractions
- Multi-process deployment
- Background autonomous operations

---

## 18. Architecture decision records

### ADR-01: Jujutsu as sole durable history layer

**Decision:** Use Jujutsu exclusively for durable history, undo, diff, and restore.

**Rationale:** Avoids building a second VCS. Provides clean change boundaries, predictable undo, and file history with minimal wrapper complexity.

**Rejected alternatives:** Git (canonical direction rejects), SQLite history ledger (unnecessary weight), custom snapshot store (duplicates VCS).

### ADR-02: In-memory job queue

**Decision:** Jobs stored in memory only. Loss on restart acceptable.

**Rationale:** v0 is local-first, single-user. Durable content history comes from Jujutsu. Queue durability adds complexity without proportional value.

### ADR-03: Generic job API

**Decision:** One `POST /api/jobs` endpoint. No command-specific endpoints.

**Rationale:** The product accepts intent, not commands. Prevents endpoint proliferation and command taxonomy.

### ADR-04: One commit per job

**Decision:** Each successful mutating job performs one `jj commit`.

**Rationale:** Creates clean history boundaries. Makes `jj undo` reliable. One job = one change = one undo.

### ADR-05: Worker concurrency locked to 1

**Decision:** Single worker for v0.

**Rationale:** Required for correct `jj undo` semantics. Simplifies commit sequencing, rebuild ordering, debugging, and user mental model. Can be revisited with redesigned undo (using `jj restore` with change IDs).

### ADR-06: Coarse full rebuilds

**Decision:** Run `kiln generate` for the entire vault after each mutation.

**Rationale:** Simplest implementation. Acceptable for v0 vault sizes. Incremental rebuilds can be added later if latency becomes a usability problem.

### ADR-07: Non-blocking subprocess calls

**Decision:** All Jujutsu and Kiln subprocess calls must use `asyncio.to_thread()` or async subprocess execution.

**Rationale:** Synchronous `subprocess.run()` blocks the async event loop. Even with one worker, this starves SSE streaming and HTTP handling during long-running subprocess calls.

### ADR-08: Bind to localhost by default

**Decision:** Server binds to `127.0.0.1`, not `0.0.0.0`.

**Rationale:** The system has no authentication. Binding to all interfaces would expose vault read/write capabilities to the network.
