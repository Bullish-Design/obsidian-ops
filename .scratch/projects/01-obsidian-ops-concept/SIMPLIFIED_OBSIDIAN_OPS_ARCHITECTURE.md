# ARCHITECTURE.md

## 1. Document Status

- Status: Revised to match canonical simplified direction
- Product: Obsidian Ops Console
- Variant: Simplified MVP
- Audience:
  - implementers of the local app/runtime
  - maintainers of the overlay UI
  - future contributors extending the agent/tool loop
- Primary bias:
  - minimal implementation
  - file-native state
  - direct markdown mutation
  - low concurrency
  - strong recoverability
  - simple mental model

---

## 2. Purpose of This Document

This document defines the architecture for the **canonical simplified** version of Obsidian Ops.

It describes a very small local system that:

- serves a Kiln-rendered Obsidian vault as a site
- injects a lightweight operations overlay into the rendered pages
- accepts a natural-language instruction through one modal
- runs a local tool-using agent against the vault
- records durable change history through Jujutsu
- rebuilds the site after successful writes
- exposes simple progress, history, and undo flows

This architecture is intentionally **not** a structured command platform, not a database-backed job system, and not a hybrid history stack.

The central design rule is:

> The vault files are canonical.  
> The app is a thin local runtime around them.  
> Jujutsu is the durable recovery layer.

---

## 3. Executive Summary

The recommended architecture is a **single-process local app** with six core pieces:

1. **Rendered site**  
   Kiln turns the Obsidian vault into a local static-ish site.

2. **Overlay UI**  
   A floating action button and one modal are injected into rendered pages.

3. **FastAPI server**  
   One process serves the site, overlay assets, and a very small `/api/*` surface.

4. **In-memory async job runtime**  
   Jobs are transient and local. A small worker pool processes them with low concurrency.

5. **Agent + tool loop**  
   A local LLM receives the user instruction plus current page context and uses a small file/tool surface to do the work.

6. **Jujutsu wrapper**  
   All durable history, diff, restore, and undo semantics come from Jujutsu through a thin wrapper.

That is the whole system.

There is no database in v0. No durable queue. No command registry. No selection toolbar. No command-specific public API surface as the main interaction model.

---

## 4. Architectural Drivers

### 4.1 Files are canonical

Markdown files in the vault are the real product state. Generated site output, job state, streamed progress, and indexes are derived runtime state.

### 4.2 The system should mutate files directly

The value of the product is that the user can describe a change in natural language and the agent can safely perform that change against the vault.

### 4.3 Recovery is mandatory

Every successful write must be attributable and reversible. The system should not build its own second durability mechanism when Jujutsu already provides the durable history layer.

### 4.4 Simplicity is a product requirement

The simplified variant should stay small in both implementation and mental model.

### 4.5 The modal is the product surface

The user should not need to learn a command tree, command taxonomy, or dashboard-heavy workflow. The center of the system is one modal.

### 4.6 Async jobs are useful, but do not need to be durable in v0

Queued and running jobs may be lost on restart. That is acceptable. Durable history matters more than durable job state in this version.

---

## 5. Top-Level System Shape

```text
Browser
  ├─ Kiln-rendered vault pages
  └─ injected ops.js + ops.css
         │
         │ POST /api/jobs
         │ GET  /api/jobs/{job_id}/stream
         │ POST /api/undo
         │ GET  /api/history
         ▼
FastAPI (single process)
  ├─ site mount: /
  ├─ ops asset mount: /ops/
  ├─ small API surface: /api/*
  ├─ in-memory queue
  ├─ worker tasks
  ├─ agent loop
  ├─ vault/file helpers
  ├─ Jujutsu wrapper
  └─ Kiln rebuild wrapper
         │
         ├─ Obsidian vault (markdown files)
         ├─ Jujutsu repo / working copy
         └─ generated site output
```

The architecture is intentionally flat. The app owns transport and orchestration. The vault remains the source of truth. Jujutsu remains the durability substrate.

---

## 6. Product Surface and Interaction Model

### 6.1 One modal

The UI surface is:

- one floating action button on every rendered page
- one modal for input
- one progress area in that modal
- one result area in that modal
- refresh and undo affordances in that modal

### 6.2 Current page context is automatic

When the modal opens, the current page path should already be available to the server and the agent as context.

The user should not need to manually specify the current file in the core flow.

### 6.3 Natural-language instructions only

The user submits intent such as:

- “clean up this note”
- “summarize this page into a new note”
- “find related notes and link them here”
- “save this article into Sources and summarize it”

The app accepts the instruction as a job. The agent decides how to use the tools.

### 6.4 Explicit non-goals for v0

The architecture should not assume:

- a selection toolbar
- per-command buttons
- a structured command palette
- a command registry exposed to the user
- a multi-surface UI with separate activity dashboards as part of the core loop

---

## 7. Runtime Model

### 7.1 One FastAPI process

The simplified system should run as one local process.

That process should:

- serve the generated site
- serve the overlay assets
- accept job submissions
- stream job progress over SSE
- run the in-memory queue and workers
- coordinate agent execution
- call Jujutsu
- trigger Kiln rebuilds

### 7.2 In-memory queue

Jobs are transient runtime objects.

A minimal shape is sufficient:

```python
@dataclass
class Job:
    id: str
    instruction: str
    file_path: str | None
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    messages: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
```

This queue exists to keep the UI responsive and to support bounded concurrency. It is not the durable system of record.

### 7.3 Worker model

Recommended defaults:

- low concurrency
- FIFO job admission is fine for v0
- one active mutation per file at a time
- manual retry only

### 7.4 File locking

Per-file in-process locks are required.

The system only needs to coordinate mutations within this process in v0. That is enough for the intended local-first deployment shape.

---

## 8. Agent Model

### 8.1 Core stance

The agent loop is first-class in the simplified architecture.

This is not a command-registry architecture with an agent facade on top. It is a small tool-using agent runtime with a thin app around it.

### 8.2 Agent inputs

Each job should provide the agent with:

- the user’s natural-language instruction
- current page path
- optionally current page content or summarized context
- tool definitions
- a short system prompt describing editing and preservation rules

### 8.3 System prompt posture

The system prompt should stay small and general.

It should emphasize rules like:

- preserve YAML frontmatter unless explicitly asked to change it
- preserve wikilinks unless explicitly asked to change them
- prefer minimal edits when possible
- do not delete content without clear user intent
- summarize changes after completion

### 8.4 Tool-use loop

The agent should follow a standard loop:

1. receive system prompt + user instruction + page context + tool definitions
2. emit tool calls and reasoning-visible progress summaries
3. execute tools and return tool results
4. repeat until a final response is produced
5. stream meaningful progress updates back to the modal

No command registry is required to make this work.

---

## 9. Tool Surface

The tool surface should stay deliberately small.

Recommended tools:

```text
read_file(path)
write_file(path, content)
list_files(glob="**/*.md")
search_files(query, glob="**/*.md")
fetch_url(url)
undo_last_change(path) or equivalent
get_file_history(path, limit=10)
```

### 9.1 `read_file`

Returns raw markdown, including frontmatter.

### 9.2 `write_file`

Writes markdown atomically and records durable history through the Jujutsu wrapper before the user-visible job is considered complete.

### 9.3 `list_files` and `search_files`

These let the agent discover relevant vault context without needing a heavier indexing subsystem in v0.

### 9.4 `fetch_url`

The architecture should keep URL fetching available as a first-class tool. The simplified product should not artificially remove it in favor of a command-specific `save_url` path.

### 9.5 `undo_last_change` and `get_file_history`

These are app-level wrappers over Jujutsu-backed history behaviors.

The UI can speak in terms like “undo” and “history” even though the implementation is Jujutsu-based.

---

## 10. Jujutsu as the Durable History Layer

### 10.1 Core stance

Jujutsu is the authoritative durable history, diff, restore, and undo substrate for v0.

This replaces:

- Git as the primary durability story
- SQLite-backed history ledgers
- custom snapshot stores as the main durability mechanism
- hybrid history systems that duplicate VCS responsibilities

### 10.2 Architectural implication

The app should depend on a **thin Jujutsu wrapper**, not on an abstract multi-backend history system as the default architecture.

The wrapper should provide a small set of operations such as:

```python
class JujutsuHistory:
    async def record_change(self, paths: list[str], summary: str) -> ChangeRef: ...
    async def get_file_history(self, path: str, limit: int = 10) -> list[HistoryEntry]: ...
    async def undo_last_change(self, path: str) -> ChangeRef: ...
    async def restore_change(self, change_id: str) -> ChangeRef: ...
    async def diff_for_change(self, change_id: str, path: str | None = None) -> str: ...
```

The exact command set can evolve, but the architecture should clearly center Jujutsu rather than a pluggable hybrid default.

### 10.3 Product-language rule

The user-facing UI should mostly say:

- changes
- history
- restore
- undo

The product should not require the user to understand Jujutsu-specific terminology.

---

## 11. File I/O and Mutation Safety

### 11.1 Atomic writes

All file writes should be atomic write-by-replace operations.

The simplified system still needs strong write safety even though the rest of the architecture is intentionally minimal.

### 11.2 Mutation flow

A successful mutating job should generally follow this order:

1. receive instruction
2. read current file or related files
3. acquire relevant file lock(s)
4. compute updated content through the agent/tool loop
5. write file(s) atomically
6. record durable history through Jujutsu
7. trigger Kiln rebuild
8. emit final summary and undo/history affordances

### 11.3 Failure model

If failure occurs **before write**, no file should change.

If failure occurs **after write but before rebuild completion**, the write should remain durable and visible in history, while the rebuild failure should be surfaced as a separate failure condition.

That distinction matters. A rebuild failure is not the same thing as a mutation failure.

---

## 12. Rendering and Rebuild Model

### 12.1 Kiln posture

Kiln is the renderer. The app is an overlay and orchestration layer around it.

The runtime should not attempt to absorb rendering logic into its own core domain.

### 12.2 Coarse rebuilds are acceptable

After successful writes, the app may trigger a coarse rebuild if that keeps the implementation simpler.

That is an intentional simplification for v0.

### 12.3 Overlay injection

The app should inject a tiny overlay into rendered pages:

- `ops.js`
- `ops.css`

That overlay is responsible for:

- rendering the floating action button
- rendering the modal
- submitting jobs
- subscribing to SSE progress
- offering refresh and undo actions

### 12.4 HTMX / page-swap tolerance

Because the rendered site may navigate without full browser reloads, the overlay code should tolerate page swaps and rebind itself when necessary.

---

## 13. API Surface

The public API should stay intentionally small.

### 13.1 Required routes

- `POST /api/jobs`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}/stream`
- `POST /api/undo`
- `GET /api/history`

### 13.2 Why the API stays generic

The simplified product accepts **intent**, not a growing family of command-specific operations.

The public architecture should therefore avoid endpoints like:

- `POST /api/rewrite`
- `POST /api/organize_note`
- `POST /api/save_url`
- `POST /api/edit/selection`
- `POST /api/edit/file`

Those may appear in experiments or internal refactors, but they are not the canonical public surface for v0.

### 13.3 SSE for progress

Progress transport should be SSE.

The canonical architecture should not switch the browser flow to polling as the primary approach.

---

## 14. Suggested Package Layout

A good simplified implementation should stay around this scale:

```text
obsidian_ops/
  app.py
  config.py
  queue.py
  agent.py
  tools.py
  history_jj.py
  rebuild.py
  inject.py
  locks.py
  fs_atomic.py
  static/
    ops.js
    ops.css
  tests/
```

This is the right order of magnitude.

The implementation should not expand into a large hierarchy of:

- command modules
- service registries
- repository layers
- database models
- hybrid persistence adapters

unless a later version explicitly changes scope.

---

## 15. Boundaries Between Components

### 15.1 App layer

Responsible for:

- HTTP routes
- SSE streaming
- static mounts
- job admission
- wiring dependencies together

### 15.2 Queue/runtime layer

Responsible for:

- holding in-memory jobs
- starting worker tasks
- lifecycle transitions
- attaching progress messages to jobs

### 15.3 Agent layer

Responsible for:

- handling natural-language instructions
- deciding which tools to call
- returning a final user-facing summary

### 15.4 Tool layer

Responsible for:

- reading files
- writing files
- listing and searching files
- fetching URLs
- calling history and undo helpers

### 15.5 History wrapper

Responsible for:

- recording durable changes through Jujutsu
- returning file history
- computing or retrieving change diffs
- implementing undo/restore helpers

### 15.6 Rebuild wrapper

Responsible for:

- triggering Kiln builds
- surfacing build failures
- ensuring the overlay remains injected after rebuild when necessary

These boundaries are enough for a clean implementation without reintroducing unnecessary architecture weight.

---

## 16. Non-Goals for the Simplified Architecture

The following should be treated as explicit non-goals for v0:

- SQLite job databases
- durable queue recovery after restart
- hybrid history storage
- Git-first history/undo semantics
- command registries
- public command-specific API surfaces
- selection-toolbar UX
- app-owned snapshot systems as the primary durability layer
- rich metadata ledgers for every operation
- large service/repository abstractions with little immediate payoff

---

## 17. Failure and Recovery Model

### 17.1 Fail-before-write

Examples:

- ambiguous or impossible target resolution
- fetch failure before any mutation is made
- invalid model/tool result
- path policy violation
- lock acquisition timeout or refusal

Result:

- no file change
- no durable history entry
- job fails with user-visible explanation

### 17.2 Fail-after-write

Examples:

- Jujutsu recording failure after file mutation
- rebuild failure after successful write
- overlay reinjection failure after rebuild

Result:

- job is marked failed or partially failed
- durable state should remain inspectable
- user should be able to use history/undo affordances where possible

### 17.3 Recovery posture

The product’s recovery story is:

- inspect recent history
- undo the last change
- restore a prior change if needed

The architecture should not require a second snapshot database to make this possible.

---

## 18. Observability

Even with a tiny UI, the runtime should still expose useful operational signals.

Recommended events/messages:

- job queued
- worker started
- reading current file
- searching related notes
- fetching URL
- writing file
- recording history
- rebuild started
- rebuild failed
- undo completed
- job completed

These can be streamed as human-readable progress lines through SSE without requiring a heavy structured event system in v0.

---

## 19. Testing Strategy

### 19.1 Unit tests

Test:

- atomic write behavior
- lock behavior
- queue state transitions
- Jujutsu wrapper parsing/handling
- file search helpers
- overlay injection behavior

### 19.2 Integration tests

Test full flows such as:

- submit job → mutate file → record history → rebuild
- submit job → no-op or failure before write
- undo flow
- history retrieval flow
- rebuild failure after successful mutation

### 19.3 Manual acceptance tests

Verify that a user can:

1. browse the rendered vault
2. open the modal from any page
3. submit a natural-language request
4. watch streamed progress
5. refresh and see the updated result
6. undo the change confidently
7. inspect recent file history when needed

That is the real product loop.

---

## 20. Metrics

The simplified runtime should expose lightweight technical metrics where helpful.

Recommended metrics:

- `jobs_queued_total`
- `jobs_running`
- `jobs_succeeded_total`
- `jobs_failed_total`
- `job_latency_ms`
- `llm_call_latency_ms`
- `file_lock_wait_ms`
- `atomic_write_latency_ms`
- `history_record_latency_ms`
- `rebuild_latency_ms`
- `undo_latency_ms`

Helpful success indicators:

- write success rate
- undo success rate
- rebuild success rate
- median end-to-end job latency

Metrics should remain lightweight and local. They should not force a database architecture.

---

## 21. Recommended MVP Decisions

### 21.1 Treat the agent loop as canonical

Do not make structured commands the core abstraction for v0.

### 21.2 Keep the public API generic

Center the architecture on generic job submission and streamed progress.

### 21.3 Use Jujutsu as the only durable history model

Do not default to Git, hybrid history, or SQLite-backed history metadata.

### 21.4 Keep the queue in memory

Loss of queued/running jobs on restart is acceptable.

### 21.5 Prefer coarse rebuilds

If coarse rebuilds keep the implementation smaller and clearer, use them.

### 21.6 Keep the codebase small

Resist architecture growth that adds abstraction without immediate product value.

---

## 22. Final Recommendation

Build Obsidian Ops as a **thin local app around a tool-using agent, a vault, Kiln, and Jujutsu**.

Concretely:

- keep one modal as the core product surface
- accept natural-language instructions only
- use a tiny in-memory async runtime
- use a small file/tool surface
- record durable history with Jujutsu
- rebuild after successful writes
- expose refresh, undo, and history affordances

The governing loop is:

**render vault → open modal → describe intent → run agent → mutate files → record history with Jujutsu → rebuild → refresh or undo**

That is the canonical simplified architecture.
