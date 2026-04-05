# Obsidian Ops — Specification

## 1. Document status

- Status: v1.0
- Product: Obsidian Ops
- Variant: Simplified MVP (v0)
- Scope: Single-user, local-first, agent-driven operations layer over an Obsidian vault rendered as a local website

---

## 2. Executive summary

Obsidian Ops is a local web overlay for an Obsidian vault. The user browses a Kiln-rendered site, clicks a floating action button, types a natural-language instruction in a modal, and a local tool-using agent executes the request against vault markdown files. Jujutsu provides durable history, undo, and recovery.

The MVP centers on four ideas:

1. One interaction surface (FAB + modal)
2. One agent loop (tool-use against vLLM)
3. One local server (FastAPI)
4. One durable history model (Jujutsu)

---

## 3. Locked decisions

These decisions are canonical for v0 and must not be changed without explicit scope revision.

### 3.1 Interaction model

- One floating action button on every rendered page
- One modal for input, progress, results, follow-up, refresh, and undo
- Natural-language instructions only
- No selection toolbar
- No per-command buttons
- No multi-surface command UI

### 3.2 Runtime model

- One FastAPI process
- One in-memory async job queue
- One generic tool-use agent loop
- **Worker concurrency: 1** (required for correct undo semantics)
- Per-file in-process locking
- SSE for progress streaming

### 3.3 Persistence model

- Vault markdown files are the source of truth
- Jujutsu is the only durable history/recovery substrate
- In-memory job state; loss on restart is acceptable
- Rendered site output is derived and disposable

### 3.4 Architecture posture

- No SQLite database
- No durable job database
- No custom snapshot store
- No hybrid history model
- No command registry
- No command-specific public API endpoints

### 3.5 Rendering posture

- Kiln renders the vault into a static site
- The app injects a lightweight overlay into rendered pages
- Successful mutations trigger a coarse full rebuild
- Server binds to `127.0.0.1` by default

---

## 4. Product definition

### 4.1 Core user promise

The user can:

- Browse their vault in a clean web interface
- Open a single modal from any page
- Describe a desired change in natural language
- Watch the system execute that request asynchronously
- Refresh the page and see the result
- Undo the change if needed

### 4.2 Product identity

This product is:

- A local operations layer over markdown files
- An agentic vault maintenance tool
- A small web interface over a file-native system

This product is not:

- A collaborative editor or browser IDE
- A chat app with notes attached
- A general autonomous agent platform
- A replacement for Obsidian itself

---

## 5. Goals and success criteria

### 5.1 Primary goals

1. Provide a local web interface over a rendered vault
2. Let the user issue natural-language instructions from any page
3. Execute instructions through a local agent with file tools
4. Mutate markdown files directly
5. Rebuild the site after successful changes
6. Make recovery simple and trustworthy through Jujutsu
7. Keep the implementation radically small

### 5.2 Success criteria

The MVP is successful when a user can:

1. Open the site locally and browse notes normally
2. Click the FAB from any page
3. Type an instruction like "organize this note" or "create a summary from this page"
4. See streamed job progress in the modal
5. Refresh and observe the resulting changes
6. Undo the most recent change confidently
7. Inspect recent file history when needed

---

## 6. Non-goals

The MVP intentionally excludes:

- Command registry architecture
- Structured selection editing UI
- Block-aware editing protocols
- Background autonomous vault scanning
- Long-lived durable job database
- Multi-user coordination
- Plugin ecosystem
- Advanced permissions model
- Deep graph UI
- Mobile-native UX
- Granular workflow authoring
- Cross-session conversation memory
- Incremental rebuilds

---

## 7. Design principles

1. **One surface, many intents.** The modal is the control surface. No command tree.
2. **File-native truth.** Markdown files are canonical.
3. **Recovery over restraint.** Direct edits are allowed because recovery is strong.
4. **Minimal architecture.** Fewer moving parts, even at the cost of internal elegance.
5. **Natural language over taxonomy.** The agent interprets intent, not pre-baked categories.
6. **Async by default.** The UI assumes jobs take time and shows progress naturally.
7. **Derived state is disposable.** Rendered output, in-memory jobs, and progress events are replaceable.

---

## 8. Core user flows

### 8.1 Issue an instruction

1. User clicks the FAB.
2. Modal opens with current page path displayed.
3. User enters a natural-language instruction.
4. User submits.
5. API creates a job and returns a job ID.
6. Modal subscribes to the SSE stream.
7. Worker runs the agent loop.
8. Agent reads, writes, searches files and emits progress.
9. Successful writes trigger `jj commit` and `kiln generate`.
10. Modal shows result with refresh and undo actions.

### 8.2 Undo the latest change

1. User clicks undo in the modal.
2. API queues an undo job.
3. Runtime calls `jj undo`.
4. Site rebuild runs.
5. Modal reports success.

### 8.3 Follow-up instruction

1. Job completes, modal remains open.
2. User enters a follow-up instruction.
3. New job is created with the same page context.

Durable cross-session conversation memory is out of scope.

### 8.4 Missing page context

If page context cannot be resolved:

- The modal still works
- The agent is informed no current file is selected
- Vault-wide or general instructions remain allowed

---

## 9. UI specification

### 9.1 Required elements

- One floating action button (persistent, bottom-right, every content page)
- One modal dialog containing:
  - Current page path display
  - Multiline text input
  - Submit button
  - Close/cancel button
  - Progress output area
  - Refresh action (after success)
  - Undo action (when applicable)

### 9.2 FAB requirements

- Appears on every rendered content page
- Visually persistent but unobtrusive
- Opens modal without page navigation
- Survives client-side page swaps (HTMX tolerance)

### 9.3 Modal behavior

- Opens without page reload
- Backdrop click closes when no job is running
- While a job is running, dismissal is discouraged
- After completion, remains open for follow-up

### 9.4 Result presentation

The result must clearly show:

- What changed (summary text)
- What files were touched
- Whether rebuild completed
- Whether undo is available

Must clearly distinguish: success, partial success (write ok / rebuild failed), failure.

### 9.5 Out-of-scope UI

- Dedicated history page
- Activity stream
- Multi-pane job dashboard
- Note-local action menus
- Selection toolbar
- Rich diff viewer

---

## 10. API specification

### 10.1 Required endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/jobs` | Create a new agent job |
| `GET` | `/api/jobs/{job_id}/stream` | SSE progress and result stream |
| `GET` | `/api/jobs` | List recent in-memory jobs |
| `POST` | `/api/undo` | Undo the most recent change |
| `GET` | `/api/history` | Lightweight file history |
| `GET` | `/api/health` | Health check |

### 10.2 Explicitly not canonical

The following endpoint patterns must not be introduced:

- `POST /api/rewrite`
- `POST /api/organize_note`
- `POST /api/save_url`
- `POST /api/edit/selection`
- `POST /api/edit/file`
- Any command-specific public mutation endpoint

### 10.3 Job creation

**Request:**

```json
{
  "instruction": "Organize this note and add a summary at the top.",
  "current_url_path": "/notes/example/",
  "current_file_path": null
}
```

`current_file_path` is optional. If absent, the server infers it from `current_url_path`.

**Response:**

```json
{
  "job_id": "a1b2c3d4"
}
```

### 10.4 SSE event envelope

```json
{
  "type": "status | tool | result | error | done",
  "message": "human-readable text",
  "payload": {}
}
```

Terminal events use SSE named events: `event: done` or `event: error`.

### 10.5 Undo request

Takes no body. Performs a global `jj undo` (reverses the most recent Jujutsu operation). This is correct only at concurrency=1.

### 10.6 History request

```text
GET /api/history?path=notes/example.md&limit=10
```

Returns recent Jujutsu log entries for the file.

### 10.7 Error responses

All non-SSE API errors return structured JSON:

```json
{
  "detail": "human-readable message"
}
```

---

## 11. Job system specification

### 11.1 Storage

Jobs are in-memory only. On restart, all job state is lost.

### 11.2 Lifecycle

```text
queued -> running -> succeeded | failed
```

Every job ends in exactly one terminal state.

### 11.3 Queue behavior

- FIFO ordering
- Worker concurrency: 1 (locked for v0)
- Per-file lock prevents concurrent writes to the same file
- Jobs without a file path are admitted for vault-wide work

### 11.4 Failure semantics

A failed job must:

- End in `failed` state
- Emit a final SSE error event
- Leave the vault in a valid, recoverable state
- Not produce partial silent corruption

---

## 12. Agent runtime specification

### 12.1 Agent inputs

Each job provides:

- User's natural-language instruction
- Current page path (or indication that none is available)
- Tool definitions
- System prompt with preservation rules

### 12.2 System prompt

Small and general. Emphasizes:

- Preserve YAML frontmatter unless explicitly asked to change
- Preserve wikilinks unless explicitly asked to change
- Prefer minimal edits
- Do not delete content without clear intent
- Summarize changes after completion

### 12.3 Tool-use loop

1. Construct system prompt + user message + tool definitions
2. Send to vLLM (OpenAI-compatible API)
3. Inspect response for tool calls
4. Execute tools, collect results
5. Append tool results, send back to model
6. Repeat until final response
7. Stream progress to modal throughout

### 12.4 Model requirements

- Must support OpenAI-compatible Chat Completions with tool use
- Context window: 16K+ tokens recommended
- 70B+ parameter model recommended for reliable tool use
- Configurable model timeout (default: 120s)

### 12.5 Safety boundary

The model acts only through approved tools. No arbitrary shell execution. All file operations are constrained to the vault root.

---

## 13. Tool surface specification

### 13.1 Required tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `read_file` | `(path: str) -> str` | Read a markdown file including frontmatter |
| `write_file` | `(path: str, content: str) -> str` | Write content atomically |
| `list_files` | `(glob: str = "**/*.md") -> list[str]` | List vault files |
| `search_files` | `(query: str, glob: str = "**/*.md") -> list[dict]` | Search file contents |
| `fetch_url` | `(url: str) -> str` | Fetch URL content |
| `undo_last_change` | `() -> str` | Undo via Jujutsu |
| `get_file_history` | `(path: str, limit: int = 10) -> list[str]` | File history via Jujutsu |

### 13.2 Tool implementation rules

- All paths must be validated against the vault root (no traversal)
- `write_file` must use atomic write-by-replace
- `write_file` must acquire a per-file lock before writing
- `fetch_url` output must be truncated to a configurable maximum (default: 120KB)
- `read_file` should enforce a content size limit (soft warning at 256KB, hard limit at 1MB)
- `search_files` performs case-insensitive substring search with context snippets

### 13.3 Deferred tools

Not in v0 unless clearly needed:

- `move_file`
- `delete_file`
- `read_directory_tree`
- `read_section`
- `rename_note`

---

## 14. Write protocol

### 14.1 Steps

1. Resolve full path within vault
2. Validate path does not escape vault root
3. Ensure parent directories exist
4. Acquire per-file lock
5. Write to temporary file
6. Flush and fsync
7. Atomic replace (`os.replace`)
8. Release lock
9. Track file as changed/created for post-job commit

### 14.2 Path safety

Must reject:

- Paths outside vault root
- Path traversal attempts (`../`)
- Writes to `.jj/`, `.obsidian/`, or other protected directories

### 14.3 Failure behavior

If write fails after temp-file creation but before replace:

- Original file remains intact
- Temp file is cleaned up best-effort
- Error surfaces to the job

---

## 15. Jujutsu history specification

### 15.1 Core stance

Jujutsu is the authoritative durable history layer. The app does not build a parallel history system.

### 15.2 Commit boundary

One `jj commit -m "<summary>"` per successful mutating job. This runs after all file writes complete and before the rebuild. The summary is derived from the user's instruction.

### 15.3 Undo

`jj undo` reverses the most recent Jujutsu operation. At concurrency=1, this reliably reverses the last user-visible mutation.

**Warning:** At concurrency > 1, undo may reverse the wrong job. Raising concurrency requires switching to `jj restore` with specific change IDs.

### 15.4 History lookup

`jj log <path> --limit N --no-graph` returns recent change entries for a file.

### 15.5 Wrapper interface

```python
class JujutsuHistory:
    def ensure_workspace(self) -> None: ...
    def commit_current_change(self, message: str) -> CommitResult: ...
    def undo_last_change(self) -> str: ...
    def history_for_file(self, path: str, limit: int) -> list[str]: ...
    def diff_for_file(self, path: str) -> str: ...
```

### 15.6 Subprocess execution

All Jujutsu calls must be non-blocking. Use `asyncio.to_thread()` or `asyncio.create_subprocess_exec()` to avoid blocking the event loop.

### 15.7 Product language

User-facing text uses: history, changes, restore, undo. Does not expose Jujutsu-specific terminology.

---

## 16. Undo specification

### 16.1 Scope

v0 undo reverses the single most recent Jujutsu operation. This works correctly only at concurrency=1.

### 16.2 UX

Undo is exposed from the result modal after a successful mutation.

### 16.3 Correctness

Undo must consult durable Jujutsu history, not in-memory state.

### 16.4 Failure

If undo cannot complete safely:

- Report failure clearly
- Do not perform partial recovery silently
- Advise the user to inspect history manually

---

## 17. Rebuild specification

### 17.1 Trigger

Every successful mutating job must trigger a rebuild after `jj commit`.

### 17.2 Strategy

Full `kiln generate --input <vault> --output <site>` followed by overlay re-injection.

### 17.3 Subprocess execution

Kiln calls must be non-blocking. Use `asyncio.to_thread()` or `asyncio.create_subprocess_exec()`.

### 17.4 Failure behavior

If rebuild fails after successful write:

- The file change remains valid and durable
- The job reports partial success
- The user is informed the rendered site may be stale

---

## 18. Current-page context specification

### 18.1 Resolution

1. Browser sends `location.pathname`
2. Server maps URL path to vault-relative markdown path
3. Resolved path is injected into the agent prompt

### 18.2 v0 resolver

Simple heuristic: strip trailing slash, append `.md`, check if file exists. Fall back to `<path>/index.md`.

### 18.3 Known limitation

This assumes Kiln's URL scheme mirrors the vault path structure. If Kiln uses slugification or custom routing, resolution will fail. Replace with a Kiln source manifest when available.

---

## 19. Concurrency and locking

### 19.1 Worker concurrency

**Locked to 1 for v0.** This is required for correct undo semantics and simplifies:

- Jujutsu commit sequencing
- Rebuild ordering
- User mental model
- Debugging

### 19.2 File locking

Per-file async locks within the process. Before any mutating tool executes:

1. Acquire lock for the file path
2. Perform the operation
3. Release the lock

### 19.3 Vault-wide operations

Jobs touching many files should acquire locks file-by-file in a consistent order to avoid deadlock.

---

## 20. Mutation flow (end-to-end)

A successful mutating job follows this order:

1. Browser submits instruction + current URL path
2. Server resolves markdown file path
3. Job is queued
4. Worker starts the job
5. Agent reads/searches/fetches as needed
6. Agent writes one or more markdown files (atomic, locked)
7. App calls `jj commit -m "ops: <instruction>"`
8. App calls `kiln generate`
9. Overlay is re-injected into rebuilt pages
10. Job emits final SSE result
11. User refreshes or undoes

---

## 21. Error handling

### 21.1 Error categories

- `model_error` — LLM call failure or timeout
- `tool_validation_error` — invalid tool arguments
- `path_error` — path traversal or vault escape
- `file_io_error` — read/write failure
- `history_error` — Jujutsu command failure
- `rebuild_error` — Kiln generate failure
- `internal_error` — unexpected runtime error

### 21.2 Error UX

Errors must be:

- Surfaced in the modal
- Concise and attributable
- Not disguised as generic "something went wrong"

### 21.3 Partial success

If write succeeds but rebuild fails, report partial success. If history recording fails after write, treat as severe and surface clearly.

---

## 22. Security and trust model

### 22.1 Environment

Trusted local environment. Single user. No auth required.

### 22.2 Network binding

Server must bind to `127.0.0.1` by default. Not `0.0.0.0`.

### 22.3 Tool boundary

The model only accesses narrowly defined vault tools. No arbitrary shell execution.

### 22.4 Path safety

All file tools enforce vault-root constraints. Path traversal is rejected.

---

## 23. Observability

### 23.1 User-facing

SSE progress events for:

- Job queued / started
- Tool calls (reading, searching, writing, fetching)
- History recording
- Rebuild started / completed / failed
- Job succeeded / failed

### 23.2 Server-side

Structured logs with:

- Timestamp, severity, job ID
- Job lifecycle events (created, started, completed/failed)
- Tool calls and file operations
- Rebuild outcomes
- Error details

---

## 24. Configuration

### 24.1 Required

| Variable | Description | Default |
|----------|-------------|---------|
| `OPS_VAULT_DIR` | Path to vault root | (required) |
| `OPS_SITE_DIR` | Path to Kiln output | (required) |
| `OPS_VLLM_BASE_URL` | vLLM endpoint | `http://127.0.0.1:8000/v1` |
| `OPS_VLLM_MODEL` | Model name | `local-model` |

### 24.2 Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `OPS_VLLM_API_KEY` | API key for vLLM | `EMPTY` |
| `OPS_JJ_BIN` | Path to jj binary | `jj` |
| `OPS_KILN_BIN` | Path to kiln binary | `kiln` |
| `OPS_KILN_TIMEOUT_S` | Kiln rebuild timeout | `180` |
| `OPS_WORKERS` | Worker count | `1` |
| `OPS_MAX_TOOL_ITERATIONS` | Agent loop limit | `12` |
| `OPS_MAX_SEARCH_RESULTS` | Search result cap | `12` |
| `OPS_PAGE_URL_PREFIX` | URL prefix for page resolution | `/` |
| `OPS_HOST` | Server bind address | `127.0.0.1` |
| `OPS_PORT` | Server port | `8080` |

---

## 25. Testing requirements

### 25.1 Unit tests

- Atomic write round-trips
- Page path inference (URL to markdown path)
- Jujutsu workspace detection
- Queue state transitions (queued -> running -> succeeded/failed)
- Overlay injection (HTML modification)
- File lock behavior
- Path validation (traversal rejection)

### 25.2 Integration tests

- `POST /api/jobs` creates a job and returns ID
- SSE stream emits progress events then terminal event
- `POST /api/undo` schedules and executes undo
- `GET /api/history` returns entries
- Full mutation flow: submit -> agent -> write -> commit -> rebuild
- Failure before write: no file change, no history entry
- Failure after write: partial success reported

### 25.3 Jujutsu integration tests

Use a temp directory with a pre-initialized `.jj` workspace:

- Edit a file, commit, verify history is non-empty
- Undo, verify file is restored
- Multiple commits, verify history ordering

### 25.4 Manual acceptance

1. App starts, initial Kiln build completes, overlay appears
2. FAB visible on rendered pages
3. Submit a cleanup instruction, see SSE progress, refresh, content changed
4. Submit a search/create instruction, verify new note created
5. Submit a URL fetch instruction, verify source note created
6. Click undo, verify previous state restored
7. Query `/api/history`, verify entries returned

---

## 26. Performance targets

All targets measured on reference environment: 8-core desktop, 32GB RAM, NVMe SSD, local vLLM.

### 26.1 UI latency

| Metric | p50 | p95 |
|--------|-----|-----|
| Modal open | ≤ 100ms | ≤ 200ms |
| Job submission acknowledgement | ≤ 150ms | ≤ 400ms |
| First progress event (jobs > 1s) | ≤ 1.0s | ≤ 2.0s |
| Post-success affordance visibility | ≤ 250ms | — |

### 26.2 API latency

| Metric | p50 | p95 |
|--------|-----|-----|
| `POST /api/jobs` | ≤ 100ms | ≤ 300ms |
| SSE stream setup | ≤ 200ms | ≤ 500ms |
| `POST /api/undo` (excluding rebuild) | ≤ 500ms | ≤ 1.5s |

### 26.3 Write path

| Metric | p50 | p95 |
|--------|-----|-----|
| Atomic write + history record (≤ 512KB) | ≤ 200ms | ≤ 500ms |

### 26.4 Rebuild

| Vault size | p50 | p95 |
|------------|-----|-----|
| ≤ 1,000 notes | ≤ 2s | ≤ 5s |
| ≤ 10,000 notes | ≤ 8s | ≤ 20s |

### 26.5 History and undo

| Metric | p50 | p95 |
|--------|-----|-----|
| History lookup (single file) | ≤ 300ms | ≤ 1.0s |
| Undo including rebuild | ≤ 3s | ≤ 10s |

### 26.6 Resource usage (idle)

| Metric | Target |
|--------|--------|
| Server RSS (excluding vLLM) | ≤ 250MB p50, ≤ 500MB p95 |
| CPU at idle | < 2% average |
| Simultaneous SSE streams | ≥ 10 without instability |

---

## 27. Reliability targets

| Metric | Target |
|--------|--------|
| 24-hour soak test uptime | ≥ 99.5% |
| Vault file corruption rate (fault injection) | 0 |
| History inconsistencies (fault injection) | 0 |
| File lock violations (concurrent test) | 0 |
| Path traversal rejection rate | 100% |
| Duplicate terminal SSE events | < 0.1% |
| FIFO queue adherence | ≥ 99% |

---

## 28. Functional requirements

### 28.1 UI

- FR-UI-001: FAB on every content page
- FR-UI-002: Modal opens without page reload
- FR-UI-003: Page context displayed when available
- FR-UI-004: Live progress during job execution
- FR-UI-005: Clear success/partial-success/failure distinction
- FR-UI-006: Undo affordance after successful mutation

### 28.2 API

- FR-API-001: Job submission via `POST /api/jobs`
- FR-API-002: SSE streaming via `GET /api/jobs/{job_id}/stream`
- FR-API-003: Job listing via `GET /api/jobs`
- FR-API-004: Undo via `POST /api/undo`
- FR-API-005: History via `GET /api/history`

### 28.3 Jobs

- FR-JOB-001: In-memory queue only
- FR-JOB-002: Every job ends in exactly one terminal state
- FR-JOB-003: FIFO dequeue order
- FR-JOB-004: No concurrent writes to the same file
- FR-JOB-005: Each job has a unique ID with traceable lifecycle

### 28.4 Tools

- FR-TOOL-001: Agent can read vault files
- FR-TOOL-002: Agent can create and replace vault files
- FR-TOOL-003: Agent can search vault contents
- FR-TOOL-004: System exposes file history
- FR-TOOL-005: System exposes undo capability

### 28.5 Safety

- FR-SAFE-001: All file operations constrained to vault root
- FR-SAFE-002: No arbitrary shell execution by the model
- FR-SAFE-003: Every successful mutation recoverable via Jujutsu

### 28.6 Rebuild

- FR-REBUILD-001: Every successful mutation triggers rebuild
- FR-REBUILD-002: Rebuild result included in job outcome
- FR-REBUILD-003: Stale-view warning on rebuild failure

---

## 29. Milestones

### Phase 0: Agent and tool proof of concept

- File tools, Jujutsu wrapper, vLLM tool loop
- Manual terminal testing against a sample vault

### Phase 1: Web shell

- FastAPI app, static mounts, injected FAB + modal
- Job submission and SSE stream endpoints

### Phase 2: Queue and mutation loop

- In-memory queue, worker tasks, per-file locking
- Tool progress events, rebuild trigger

### Phase 3: Recovery and polish

- Undo endpoint and UI action
- History endpoint
- Improved error messaging
- Non-blocking subprocess calls

---

## 30. Deferred enhancements

Likely post-v0 additions:

1. Diff preview / dry-run mode before committing changes
2. Optional selection-aware mode within the same modal UX
3. Simple recent-jobs page
4. Richer history inspection UI
5. Search index to replace linear scan
6. File move/rename tools
7. Protected path configuration
8. Incremental rebuild optimization
9. Non-blocking background rebuilds
10. Durable recent-job cache on disk
