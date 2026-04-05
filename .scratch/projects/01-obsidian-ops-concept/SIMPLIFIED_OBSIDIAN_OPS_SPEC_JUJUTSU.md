# Obsidian Ops Console — Simplified MVP Specification

## 1. Document status

- Status: Draft v0.2
- Product: Obsidian Ops Console
- Variant: Simplified MVP
- Source basis: Simplified Obsidian Ops concept, adapted to a Jujutsu-backed history model
- Scope: Single-user, local-first, agent-driven operations layer over an Obsidian vault rendered as a local web site
- Primary goal: Define the smallest shippable product that is powerful, trustworthy, measurable, and easy to reason about

---

## 2. Executive summary

Obsidian Ops Console is a **local web overlay for an Obsidian vault**.

The user browses a Kiln-rendered site for their vault. A floating action button opens a modal. The user types a natural-language instruction. A local agent receives that instruction plus page context, uses a small set of file tools, mutates markdown files in the vault, triggers a rebuild, and reports what it did.

This MVP intentionally rejects a large amount of structure:

- no command registry
- no per-command endpoint proliferation
- no SQLite metadata database
- no custom snapshot store
- no separate durable activity-event subsystem
- no structured page toolbar ecosystem
- no selection-edit-specific UX in v0

Instead, the MVP centers on four simple ideas:

1. one interaction surface
2. one agent loop
3. one local server
4. one Jujutsu-backed durable history model

The product promise is:

> Open the vault in the browser, describe what you want, let the agent do it, then inspect or undo the result with confidence.

---

## 3. Product definition

### 3.1 One-sentence definition

A locally hosted markdown operations console that lets a user issue natural-language instructions against their vault through a single modal, with an agent executing file operations and Jujutsu providing durable history and recovery.

### 3.2 Product identity

This product is best understood as:

- a local operations layer over markdown files
- an agentic vault maintenance tool
- a very small web interface over a file-native system

This product is not:

- a collaborative editor
- a browser IDE
- a chat app with notes attached
- a general autonomous agent platform
- a structured workflow engine
- a replacement for Obsidian itself

### 3.3 Core user promise

The user should be able to:

- browse their vault in a clean web interface
- open a single modal from any page
- describe a desired change in natural language
- watch the system execute that request asynchronously
- refresh the page and see the result
- undo the change if needed

---

## 4. Final MVP decisions

The following decisions are locked for this MVP.

### 4.1 Deployment model

- local-only deployment
- single-user system
- no application auth
- trusted environment assumption
- no cloud dependency required for core use

### 4.2 Rendering model

- Kiln-generated static-ish site
- FastAPI serves both the generated site and the operations overlay
- post-build injection adds the floating action button and modal assets to pages
- rebuild occurs after successful mutations

### 4.3 Interaction model

- one floating action button on every rendered page
- one modal for input, progress, results, undo, and follow-up
- no dedicated page action buttons in v0
- no selection toolbar in v0
- no multi-surface command UX

### 4.4 Agent model

- one general-purpose system prompt
- one generic tool-use loop
- one natural-language instruction input
- no structured command registry
- no command-specific endpoint contracts beyond job submission

### 4.5 Persistence model

- vault files are durable source-of-truth content
- Jujutsu is the durable history and recovery layer
- in-memory job state is acceptable for v0
- loss of queued/running jobs on restart is acceptable
- rebuild output is derived state

### 4.6 Version-control stance

- Jujutsu is the primary VCS interface
- Git compatibility may exist underneath via Jujutsu’s Git-backed mode, but the product should speak in Jujutsu terms
- app UX should talk about changes, history, restore, and undo rather than VCS jargon whenever possible

### 4.7 Editing scope

- whole-file and file-creation operations are first-class
- the agent may read, write, create, move, and inspect files through tools
- selection-based editing is deferred from v0 unless it can be layered later without changing the main UX model

### 4.8 Job model

- async jobs are queued in memory
- progress is streamed with SSE
- low concurrency is preferred
- per-file locking is required for safety

---

## 5. Goals

### 5.1 Primary goals

1. Provide a local web interface over a rendered vault.
2. Let the user issue natural-language instructions from any page.
3. Execute those instructions through a local agent with simple file tools.
4. Mutate markdown files directly.
5. Rebuild the site after successful changes.
6. Make recovery simple and trustworthy through Jujutsu.
7. Keep the implementation radically smaller than the heavier structured alternative.

### 5.2 Success criteria

The MVP is successful if a user can:

1. open the site locally and browse notes normally
2. click the floating action button from any page
3. type an instruction like “organize this note” or “create a summary note from this page”
4. see streamed job progress in the modal
5. refresh and observe the resulting file changes in the rendered site
6. undo the most recent change confidently
7. inspect the recent history of a file when needed

---

## 6. Non-goals

The MVP intentionally excludes:

- command registry architecture
- structured selection editing UI
- block-aware editing protocols
- background autonomous scanning of the vault
- long-lived durable job database
- multi-user coordination
- plugin ecosystem
- advanced permissions model
- deep graph UI
- mobile-native UX
- granular workflow authoring
- full conversational workspace memory across browser sessions

---

## 7. Design principles

### 7.1 One surface, many intents
The user should not need to learn a command tree. The modal is the control surface.

### 7.2 File-native truth
Markdown files remain canonical.

### 7.3 Recovery over restraint
The system is allowed to make direct edits because the recovery story is strong.

### 7.4 Minimal architecture over perfect architecture
A smaller system with fewer moving parts is preferred, even if some internal behavior is less elegant.

### 7.5 Natural language over workflow taxonomy
The agent should interpret intent from user language rather than require pre-baked command categories.

### 7.6 Async by default
The UI should assume jobs may take time and should expose progress naturally.

### 7.7 Derived state stays disposable
Rendered output, in-memory jobs, and transient progress events are all replaceable.

---

## 8. High-level architecture

```text
Browser
  │
  ├── Kiln-rendered vault pages
  ├── injected FAB + modal JS/CSS
  └── SSE listener for job progress
  │
  ▼
FastAPI server
  │
  ├── static site hosting
  ├── overlay asset hosting
  ├── job submission API
  ├── job progress streaming API
  ├── undo/history helpers
  └── in-memory queue + worker tasks
  │
  ▼
Agent runtime
  │
  ├── system prompt
  ├── tool loop
  ├── vLLM adapter
  ├── file tools
  └── rebuild trigger
  │
  ▼
Vault workspace
  │
  ├── markdown files
  ├── rendered site output
  └── Jujutsu repo/history
```

### 8.1 Top-level mental model

The cleanest mental model is:

- the vault is content
- the site is a view of that content
- the agent is an operator on that content
- Jujutsu is the durable history substrate
- the queue is just a temporary execution mechanism

---

## 9. System boundaries

### 9.1 What is durable

Durable state includes:

- vault markdown files
- any created directories/files in the vault
- Jujutsu repo state and history
- generated site output if retained on disk

### 9.2 What is ephemeral

Ephemeral state includes:

- in-memory jobs
- live SSE progress streams
- open modal session state
- in-flight agent conversation state

### 9.3 Consequence of this split

If the server restarts:

- the vault remains intact
- Jujutsu history remains intact
- completed work remains intact
- queued/running jobs may be lost
- modal progress streams will be interrupted

This is acceptable for v0.

---

## 10. Core user flows

### 10.1 Browse the vault

1. User opens the local site.
2. User navigates through rendered notes.
3. Floating action button is visible on every content page.

### 10.2 Issue an instruction on the current page

1. User clicks the floating action button.
2. Modal opens.
3. Modal displays current page path.
4. User enters a natural-language instruction.
5. User submits.
6. API creates a job and returns a job id.
7. Modal subscribes to the SSE stream for that job.
8. Worker runs the agent loop.
9. Agent reads files, writes files, and emits progress summaries.
10. Successful writes trigger Jujutsu history updates and a site rebuild.
11. Modal shows final result with refresh and undo actions.

### 10.3 Undo the latest change

1. User clicks undo in the modal result.
2. API queues or executes an undo action for the affected file or change.
3. Runtime restores the previous state using Jujutsu-backed history semantics.
4. Site rebuild runs.
5. Modal reports success.

### 10.4 Follow-up instruction in the same modal

1. Job completes.
2. Modal remains open.
3. User enters a follow-up instruction.
4. New job is created, optionally seeded with the same current page context.

This is supported as a UX pattern, but durable cross-session conversation memory is out of scope.

---

## 11. UI specification

### 11.1 Required client elements

The injected overlay must provide:

- one floating action button
- one modal dialog
- one multiline text input
- one submit button
- one cancel/close button
- one output area for progress and results
- one refresh-page action after success
- one undo action when applicable

### 11.2 Floating action button requirements

The floating action button must:

- appear on every rendered content page
- be visually persistent but unobtrusive
- open the modal quickly with no page navigation
- remain functional across client-side page swaps if the rendered site uses them

### 11.3 Modal requirements

The modal must show:

- current page path or “none” when unavailable
- free-text instruction input
- job submission state
- streamed progress lines
- final success or failure result
- optional undo action
- optional refresh link/button

### 11.4 Modal behavior

- modal opens without reloading the page
- backdrop click may close the modal when no job is running
- while a job is running, accidental dismissal should be discouraged
- after job completion, modal may remain open for follow-up

### 11.5 Result presentation

The modal result should prioritize clarity over verbosity:

- what changed
- what files were touched
- whether rebuild completed
- whether undo is available

### 11.6 Out-of-scope UI

Not included in v0:

- dedicated history page
- activity stream page
- multi-pane job dashboard
- note-local action menus
- selection-specific toolbar
- rich diff UI

---

## 12. API specification

The API should remain extremely small.

### 12.1 Required endpoints

#### `POST /api/jobs`
Create a new agent job.

#### `GET /api/jobs/{job_id}/stream`
Stream progress and final results for a job via SSE.

#### `GET /api/jobs`
List recent in-memory jobs for lightweight diagnostics.

#### `POST /api/undo`
Undo the most recent relevant change.

#### `GET /api/history`
Return a lightweight recent history view backed by Jujutsu commands for a file or path.

#### `POST /api/rebuild`
Optional endpoint for manual rebuild, mainly for diagnostics or future use.

### 12.2 Job creation request

```json
{
  "instruction": "Organize this note and add a short summary at the top.",
  "file_path": "Notes/example.md"
}
```

### 12.3 Job creation response

```json
{
  "job_id": "a1b2c3d4",
  "status": "queued"
}
```

### 12.4 Undo request

```json
{
  "file_path": "Notes/example.md"
}
```

Alternative future form:

```json
{
  "change_id": "xyz123"
}
```

### 12.5 History request

History may be parameterized by:

- `file_path`
- `limit`

Example:

```text
GET /api/history?file_path=Notes/example.md&limit=10
```

### 12.6 SSE event schema

Progress stream events should use a small typed envelope.

#### Tool progress event

```json
{
  "type": "tool_call",
  "tool": "read_file",
  "summary": "Read Notes/example.md"
}
```

#### Status event

```json
{
  "type": "status",
  "message": "Running agent step 2 of 4"
}
```

#### Result event

```json
{
  "type": "result",
  "message": "Reorganized Notes/example.md and added a summary.",
  "files_changed": ["Notes/example.md"],
  "rebuild": "succeeded",
  "undo_available": true
}
```

#### Error event

```json
{
  "type": "error",
  "message": "Model response was invalid for write_file"
}
```

---

## 13. Job system specification

### 13.1 Job purpose

Jobs exist to decouple UI responsiveness from model and file latency.

### 13.2 Job storage

Jobs are stored in memory only.

### 13.3 Job schema

```python
class Job(BaseModel):
    id: str
    instruction: str
    file_path: str | None = None
    status: Literal["queued", "running", "succeeded", "failed"]
    agent_messages: list[dict] = []
    result: str | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    changed_files: list[str] = []
```

### 13.4 Queue behavior

- FIFO by default
- max concurrency set low, recommended default `2` or `3`
- per-file lock prevents conflicting writes to the same file
- jobs without a file path may still be admitted if the instruction requires vault-wide work

### 13.5 Restart semantics

On process restart:

- queued jobs are lost
- running jobs are lost
- completed job list is lost unless optionally serialized later

This is acceptable because durable content history is not stored here.

### 13.6 Failure semantics

A failed job must:

- end in `failed`
- emit a final SSE error event
- avoid partial silent corruption when possible
- leave the vault in a valid recoverable state

---

## 14. Concurrency and locking

### 14.1 Concurrency stance

The system should prefer simplicity and correctness over throughput.

### 14.2 Recommended concurrency defaults

- 2 worker tasks by default
- 3 maximum unless tested otherwise
- per-file locking required

### 14.3 File lock behavior

Before any mutating tool executes against a file:

1. acquire the lock for that file path
2. perform the read/write/rename operation
3. run any history bookkeeping required for that operation
4. release the lock

### 14.4 Vault-wide operations

Jobs that may touch many files should either:

- acquire locks file-by-file in a consistent order, or
- run under a coarser vault-level lock if simpler

The MVP should prefer the simplest correct strategy, even if it reduces parallelism.

---

## 15. Agent runtime specification

### 15.1 Core loop

The agent runtime follows a standard tool-use loop:

1. construct system prompt and input context
2. send request to the model
3. inspect response for tool calls
4. execute tools
5. append tool results
6. continue until the model returns a final answer
7. surface final summary to the modal

### 15.2 Agent context

Every job should provide at minimum:

- current page path if present
- user instruction
- system rules
- tool definitions

Optional future context:

- selected text
- recent tool outputs from the same modal session
- recent job summary from the same page

### 15.3 System prompt goals

The system prompt should:

- establish that the agent operates on an Obsidian vault
- preserve frontmatter unless instructed otherwise
- preserve links unless instructed otherwise
- discourage destructive deletion without explicit instruction
- require concise summary of actions taken

### 15.4 Output discipline

The model is not trusted to mutate files directly.

The model must act through tools.

### 15.5 Safety boundary

The tools, not the model text, form the real execution boundary.

---

## 16. Tool contract specification

The MVP tool set must remain tiny and legible.

### 16.1 Required tools

#### `read_file(path: str) -> str`
Read one file from the vault.

#### `write_file(path: str, content: str, summary: str | None = None) -> ToolResult`
Write or replace a file atomically, then record the change in Jujutsu-backed history.

#### `list_files(glob: str = "**/*.md") -> list[str]`
List markdown files.

#### `search_files(query: str, glob: str = "**/*.md") -> list[SearchMatch]`
Search file contents.

#### `fetch_url(url: str) -> str`
Fetch a URL for source-note creation or summarization workflows.

#### `undo_last_change(path: str) -> ToolResult`
Undo the most recent relevant change for a file using the chosen Jujutsu-backed recovery strategy.

#### `get_file_history(path: str, limit: int = 10) -> list[HistoryEntry]`
Return recent history entries for a file.

### 16.2 Optional tools for later

Deferred until post-MVP unless clearly needed:

- `move_file`
- `delete_file`
- `read_directory_tree`
- `read_section`
- `rename_note`

### 16.3 Tool result rules

Mutating tools should return:

- success/failure
- affected file paths
- a concise change summary
- history metadata useful for undo or inspection

### 16.4 Tool implementation rule

Each tool should be a thin, explicit wrapper over filesystem and Jujutsu operations.

---

## 17. Write protocol

Every write must follow a disciplined protocol.

### 17.1 Steps for `write_file`

1. resolve full path within the vault
2. validate the path is allowed
3. ensure parent directories exist
4. acquire file lock
5. read current content if file already exists
6. write new content to a temporary file
7. flush and atomically replace the target file
8. trigger the Jujutsu-backed history recording step
9. release lock
10. emit progress/result event

### 17.2 Path safety rules

The write tool must reject:

- paths outside the vault root
- path traversal attempts
- writes into protected runtime directories unless explicitly allowed

### 17.3 Content safety rules

The write tool should not attempt to be overly smart.

It should not:

- silently reformat content unless the model chose to do so
- invent frontmatter values unless instructed or required by the product
- merge conflicting concurrent writes automatically in v0

### 17.4 Failure behavior

If the write fails after temp-file creation but before replacement:

- original file must remain intact
- temp file may be cleaned up best-effort
- error must surface to the job

---

## 18. Jujutsu-backed history specification

### 18.1 Product stance

Jujutsu is the durable recovery and inspection mechanism.

The app should rely on it rather than building a second heavy custom history system.

### 18.2 Required product capabilities

The system must support:

- durable history for changed files
- user-facing “undo” behavior
- recent history listing for a file
- diff-oriented inspection as an implementation capability

### 18.3 App-facing abstraction

The app should define a small internal history service with methods such as:

- `record_change(paths, summary)`
- `undo_file(path)`
- `get_history(path, limit)`
- `diff_latest(path)`

The rest of the app should not depend directly on raw CLI calls.

### 18.4 Jujutsu usage principles

The spec intentionally defines outcomes, not every CLI detail.

Required outcomes:

- successful mutations become durable in Jujutsu-backed history
- history can be queried later
- recent operations can be reversed
- recovery remains local-first

### 18.5 UI wording guidance

User-facing text should prefer:

- change
- version
- restore
- undo
- history

Avoid forcing the user to think about:

- revisions
- operation log
- working-copy commit
- rebases

unless the UI is explicitly in an advanced diagnostics mode.

### 18.6 Implementation note

The implementation should treat Jujutsu as the authoritative durable ledger rather than recreating a second commit-tracking system in-app. The app should still wrap Jujutsu behavior behind a stable history service boundary so the rest of the system only depends on app-level operations.

---

## 19. Undo specification

### 19.1 Product goal

Undo should feel like a simple reversal of the last relevant change.

### 19.2 MVP undo scope

The MVP only promises:

- undo the most recent change affecting a given file, or
- undo the most recent app-triggered operation when sufficient metadata exists in memory

### 19.3 Undo UX

Undo is exposed from the result modal.

Optional future surfaces:

- history page
- note-local recovery controls

### 19.4 Undo correctness requirement

Undo must not rely purely on the current page content in memory.

It must consult durable history.

### 19.5 Failure behavior

If undo cannot be completed safely:

- report failure clearly
- do not perform partial recovery logic silently
- advise the user to inspect history manually if needed

---

## 20. History inspection specification

### 20.1 Minimal requirement

The app must be able to show recent history for a file on demand.

### 20.2 Response shape

A history entry should include at minimum:

- a stable id or rev identifier
- timestamp
- summary/description
- file path relevance

### 20.3 MVP UI stance

A raw but useful history response is acceptable in v0.

Fancy history pages are deferred.

---

## 21. Rebuild specification

### 21.1 Rendering model

The site is generated, not live-rendered from a database.

### 21.2 Rebuild trigger

After any successful mutating operation, the system must trigger a rebuild.

### 21.3 Required rebuild behavior

- rebuild after `write_file`
- rebuild after successful undo
- rebuild after file creation
- rebuild after file move/rename if added later

### 21.4 MVP rebuild granularity

A coarse full rebuild is acceptable.

Do not optimize early unless rebuild latency becomes a real usability problem.

### 21.5 Rebuild failure behavior

If the file mutation succeeded but rebuild failed:

- the file change remains valid
- the job should report rebuild failure distinctly
- the user should be told content changed but the site view may be stale

---

## 22. Current-page context specification

### 22.1 Page context requirement

When the modal is opened from a note page, the UI should pass the current file path to the server.

### 22.2 Behavior when page context is missing

If page context is unavailable:

- the modal still works
- the agent is informed that no current file is selected
- vault-wide or general instructions remain allowed

### 22.3 Importance of context

Current page context is the main replacement for dedicated note-local action buttons.

---

## 23. Conversation continuity specification

### 23.1 Modal-session continuity

The modal may preserve the immediate conversation history for the duration of a single open session.

### 23.2 Scope

This continuity is:

- modal-local
- ephemeral
- not guaranteed across page reloads
- not guaranteed across server restarts

### 23.3 Why this is enough

This supports short follow-up interactions without requiring a persistent chat architecture.

---

## 24. Fetch and source-note workflows

### 24.1 URL support in MVP

The agent may use `fetch_url` when the user asks to save, summarize, or transform a web page into a vault note.

### 24.2 Source-note behavior

A typical workflow is:

1. fetch URL
2. synthesize title/body
3. create a note under `Sources/`
4. rebuild the site
5. report created file path

### 24.3 Minimal note contract

A created source note should include:

- title
- kind/source-like metadata if used
- original URL
- generated markdown body

---

## 25. File layout specification

Recommended project layout:

```text
obsidian-ops/
  app.py
  config.py
  queue.py
  agent.py
  tools.py
  history.py
  rebuild.py
  inject.py
  static/
    ops.js
    ops.css
  tests/
```

Recommended vault relationship:

```text
vault/
  Notes/
  Projects/
  Sources/
  Templates/
  .obsidian/
```

Generated site output may live:

- inside the app workspace, or
- in a configured output directory outside the vault

The generated site should not become part of the content model.

---

## 26. Configuration specification

### 26.1 Required config values

- `vault_path`
- `site_output_dir`
- `vllm_base_url`
- `model_name`
- `server_port`
- `max_concurrent_jobs`

### 26.2 Recommended optional config values

- `rebuild_command`
- `allowed_write_roots`
- `protected_paths`
- `fetch_timeout_seconds`
- `history_limit_default`

### 26.3 Configuration goals

Config should remain small and understandable.

---

## 27. Observability specification

### 27.1 User-facing observability

The user needs to see:

- job queued
- job running
- tool activity summaries
- success/failure
- whether rebuild succeeded
- whether undo is available

### 27.2 Developer-facing observability

The server should log:

- job creation
- job start/finish
- tool calls
- write operations
- rebuild start/finish
- history/undo failures
- SSE stream errors

### 27.3 Persistence stance for logs

Normal server logs are sufficient for v0.

Do not build a separate durable activity subsystem yet.

---

## 28. Error handling specification

### 28.1 Categories of failure

- model error
- tool validation error
- path safety violation
- file read/write failure
- Jujutsu history failure
- rebuild failure
- SSE interruption

### 28.2 Error UX rules

Errors must be:

- surfaced in the modal
- concise
- attributable
- not disguised as generic “something went wrong” messages when specifics are known

### 28.3 Partial success rule

If a file write succeeds but rebuild fails, the job should report partial success.

If a history step fails after a write, the runtime should treat that as severe and surface it clearly.

---

## 29. Security and trust model

### 29.1 Environment assumption

The system assumes a trusted local environment or private network environment.

### 29.2 Security stance for MVP

- no app auth
- no multi-user isolation
- no cloud secrets management
- no arbitrary shell tool exposed to the model

### 29.3 Tool boundary safety

The model should only have access to narrowly defined vault tools.

Avoid exposing unrestricted shell execution in v0.

### 29.4 Path safety

All file tools must enforce vault-root constraints.

---

## 30. Technical requirements and metrics

This section defines measurable engineering targets for the MVP.

### 30.1 Reference environment

Unless otherwise noted, all targets apply to a reference environment roughly equivalent to:

- modern 8-core desktop CPU
- 32 GB RAM
- local NVMe SSD
- local vLLM endpoint on the same machine or LAN
- vault size up to 10,000 markdown files and 2 GB total repository size

The reference environment is a benchmark baseline, not a deployment requirement.

### 30.2 UI performance metrics

#### TR-UI-001 FAB availability
The floating action button must appear on at least **99.5%** of rendered note pages in a representative site build.

#### TR-UI-002 Modal open latency
From click to visible modal render:

- p50: **≤ 100 ms**
- p95: **≤ 200 ms**

#### TR-UI-003 Submission acknowledgement latency
From submit click to receipt of job id:

- p50: **≤ 150 ms**
- p95: **≤ 400 ms**

#### TR-UI-004 First progress visibility
For jobs longer than 1 second, first visible progress event should appear within:

- p50: **≤ 1.0 s**
- p95: **≤ 2.0 s**

#### TR-UI-005 Post-success affordance latency
After job completion, refresh and undo affordances must appear within **250 ms** of terminal event receipt.

### 30.3 API performance metrics

#### TR-API-001 Job create endpoint
`POST /api/jobs` latency target:

- p50: **≤ 100 ms**
- p95: **≤ 300 ms**

excluding client network latency outside the local network.

#### TR-API-002 SSE stream setup
`GET /api/jobs/{job_id}/stream` must establish a valid event stream within:

- p50: **≤ 200 ms**
- p95: **≤ 500 ms**

#### TR-API-003 Undo endpoint latency
For single-file undos not blocked by rebuild time:

- p50: **≤ 500 ms** to response acceptance
- p95: **≤ 1.5 s** to response acceptance

### 30.4 Queue and concurrency metrics

#### TR-JOB-001 Concurrency default
Default worker concurrency must be **2**.

#### TR-JOB-002 Supported concurrency ceiling
The system must support **3 concurrent jobs** without deadlock, file corruption, or event-stream misrouting.

#### TR-JOB-003 File lock correctness
At no point may two mutating operations hold the same file lock simultaneously.

**Acceptance rule:** 0 violations across a 10,000-job randomized concurrency test.

#### TR-JOB-004 Queue fairness
In the absence of file-lock conflicts, jobs must begin in FIFO order.

**Acceptance rule:** At least **99%** FIFO adherence across synthetic queue tests.

#### TR-JOB-005 Restart tolerance
Unexpected process restart must not corrupt vault files or Jujutsu history state.

### 30.5 Write-path metrics

#### TR-WRITE-001 Atomicity
Write operations must be atomic at the target-file level.

**Acceptance rule:** In forced-failure tests during write, the file is always either fully old or fully new, never partially written.

#### TR-WRITE-002 Single-file write latency
For markdown files up to 512 KB, excluding model time:

- p50 atomic write + history record step: **≤ 200 ms**
- p95 atomic write + history record step: **≤ 500 ms**

#### TR-WRITE-003 Path validation
100% of path traversal attempts must be rejected.

#### TR-WRITE-004 Protected path safety
100% of writes into configured protected paths must be rejected unless explicitly permitted.

### 30.6 Rebuild metrics

#### TR-REBUILD-001 Small vault rebuild
For a vault of up to 1,000 notes:

- p50 full rebuild: **≤ 2 s**
- p95 full rebuild: **≤ 5 s**

#### TR-REBUILD-002 Medium vault rebuild
For a vault of up to 10,000 notes:

- p50 full rebuild: **≤ 8 s**
- p95 full rebuild: **≤ 20 s**

#### TR-REBUILD-003 Rebuild trigger reliability
100% of successful mutating jobs must attempt a rebuild.

#### TR-REBUILD-004 Partial-success visibility
100% of rebuild failures after successful writes must be surfaced as partial-success outcomes, not generic failure.

### 30.7 History and undo metrics

#### TR-HIST-001 History durability
100% of successful mutating writes must be represented in Jujutsu-backed durable history.

#### TR-HIST-002 Undo success rate
For the last successful single-file app-triggered change:

- automated undo success rate: **≥ 99%** across test runs

#### TR-HIST-003 History lookup latency
Recent history lookup for a single file:

- p50: **≤ 300 ms**
- p95: **≤ 1.0 s**

#### TR-HIST-004 Undo completion time
Single-file undo including rebuild on the reference environment:

- p50: **≤ 3 s**
- p95: **≤ 10 s**

### 30.8 Agent/runtime metrics

#### TR-AGENT-001 Tool-call execution visibility
Every mutating job longer than 2 seconds must emit at least one progress event per major tool step.

#### TR-AGENT-002 Context-size guardrail
The runtime must enforce a configurable maximum file/context payload size before sending content to the model.

**Default:** soft warning at **256 KB**, hard limit at **1 MB** per file read unless the tool explicitly supports chunking.

#### TR-AGENT-003 Tool isolation
100% of file mutations must occur through approved tool functions, not by executing arbitrary shell commands.

#### TR-AGENT-004 Model timeout
Default model request timeout must be configurable and set to **120 s** by default.

### 30.9 Resource usage targets

#### TR-RES-001 Server memory footprint
Idle FastAPI + overlay + queue process memory target:

- p50 RSS: **≤ 250 MB**
- p95 RSS: **≤ 500 MB**

excluding vLLM.

#### TR-RES-002 CPU overhead at idle
Idle server CPU usage target: **< 2%** average on the reference machine.

#### TR-RES-003 SSE connection handling
The server must support at least **10 simultaneous SSE streams** without stream mix-ups or process instability.

### 30.10 Reliability targets

#### TR-REL-001 Crash-free operation
Under a 24-hour soak test with periodic job submission, the server should maintain **≥ 99.5%** process uptime excluding intentional restarts.

#### TR-REL-002 Data integrity
Across automated fault-injection tests, vault file corruption rate must be **0**.

#### TR-REL-003 History integrity
Across automated fault-injection tests, unrecoverable durable-history inconsistencies attributable to app logic must be **0**.

#### TR-REL-004 Duplicate terminal event rate
Duplicate final SSE terminal events must occur in **< 0.1%** of jobs.

### 30.11 Observability requirements

#### TR-OBS-001 Structured logs
All server logs must be structured and include:

- timestamp
- severity
- request id or job id when applicable
- event type
- human-readable message

#### TR-OBS-002 Job lifecycle logging
Each job must log:

- created
- started
- completed or failed
- files changed
- rebuild outcome

#### TR-OBS-003 Error attribution
All terminal job failures must include a categorized error code.

Minimum categories:

- `model_error`
- `tool_validation_error`
- `path_error`
- `file_io_error`
- `history_error`
- `rebuild_error`
- `internal_error`

### 30.12 Test requirements

#### TR-TEST-001 Unit coverage
Core tool and queue modules must maintain at least **85% line coverage**.

#### TR-TEST-002 Integration coverage
The following must have automated integration tests:

- job submission
- SSE streaming
- file writes
- undo
- rebuild trigger
- path safety
- file locking

#### TR-TEST-003 Concurrency test suite
A concurrency suite must cover:

- same-file conflicting jobs
- different-file concurrent jobs
- vault-wide job mixed with single-file jobs
- process interruption during write

#### TR-TEST-004 Golden-output tests
At least one golden test set must validate that representative instructions produce acceptable file mutations on a sample vault.

---

## 31. Functional requirements

This section converts the design into explicit requirements.

### 31.1 UI requirements

#### FR-UI-001 Floating action button availability
The system must render one floating action button on every normal content page in the generated site.

#### FR-UI-002 Modal invocation
Clicking the floating action button must open the operations modal without a full page reload.

#### FR-UI-003 Page-context display
When a current file path is available, the modal must display it clearly.

#### FR-UI-004 Job progress rendering
The modal must display live progress updates while a job is running.

#### FR-UI-005 Result state clarity
The modal must clearly distinguish:

- success
- partial success
- failure

#### FR-UI-006 Undo affordance
When a mutation succeeds and recovery is available, the modal must expose an undo action.

### 31.2 API requirements

#### FR-API-001 Job submission endpoint
The system must provide `POST /api/jobs` to create a new job.

#### FR-API-002 Job streaming endpoint
The system must provide `GET /api/jobs/{job_id}/stream` as an SSE endpoint for progress and final result delivery.

#### FR-API-003 Recent jobs endpoint
The system must provide `GET /api/jobs` for recent ephemeral job inspection.

#### FR-API-004 Undo endpoint
The system must provide `POST /api/undo`.

#### FR-API-005 History endpoint
The system must provide a lightweight history inspection endpoint for file history.

#### FR-API-006 Structured error responses
All non-SSE API errors must return structured JSON with:

- error code
- human-readable message
- request correlation id when available

### 31.3 Job-system requirements

#### FR-JOB-001 Ephemeral queue
Jobs must be queued and executed from in-memory state only in v0.

#### FR-JOB-002 Terminal states
Every job must end in exactly one terminal state:

- `succeeded`
- `failed`

#### FR-JOB-003 Queue ordering
Jobs must be dequeued FIFO unless blocked by file locking or explicit future prioritization.

#### FR-JOB-004 File locking
No two mutating jobs may write to the same file concurrently.

#### FR-JOB-005 Job traceability
Each job must have a unique id and expose its status, creation time, and terminal outcome.

### 31.4 Tooling requirements

#### FR-TOOL-001 Read capability
The agent must be able to read markdown files from the vault.

#### FR-TOOL-002 Write capability
The agent must be able to create and replace markdown files through a controlled write tool.

#### FR-TOOL-003 Search capability
The agent must be able to search the vault for matching content.

#### FR-TOOL-004 History capability
The system must expose recent file history to the agent and the user.

#### FR-TOOL-005 Undo capability
The system must expose a tool or service path that can reverse the most recent relevant file change.

### 31.5 Safety requirements

#### FR-SAFE-001 Vault-root enforcement
All file operations must be constrained to the configured vault root.

#### FR-SAFE-002 Protected path enforcement
Configured protected paths must not be modified by default.

#### FR-SAFE-003 No arbitrary shell execution
The model must not have access to a general shell-execution tool in v0.

#### FR-SAFE-004 Recoverability
Every successful mutation must be recoverable through durable history semantics.

### 31.6 Rebuild requirements

#### FR-REBUILD-001 Success-triggered rebuild
Every successful mutating operation must trigger a rebuild attempt.

#### FR-REBUILD-002 Rebuild result reporting
The final job result must include whether rebuild succeeded, failed, or was skipped.

#### FR-REBUILD-003 Stale-view communication
If rebuild fails after content mutation, the UI must inform the user that the rendered site may be stale.

---

## 32. Acceptance criteria

The MVP is accepted when all of the following are true:

1. The generated site is served locally with the operations overlay injected.
2. The floating action button appears on rendered pages.
3. The modal can submit a natural-language instruction with current page context.
4. A worker can execute the agent loop and stream progress via SSE.
5. The agent can read and write markdown files through tools.
6. Successful writes are recorded in Jujutsu-backed durable history.
7. Successful writes trigger a rebuild.
8. The modal can report final success or failure.
9. The user can undo the latest change for a file.
10. The system remains usable after repeated daily note-maintenance workflows.
11. The system meets or exceeds the p95 latency and reliability targets defined in Section 30 on the reference environment.

---

## 33. Milestones

### Phase 0: agent and tool proof of concept

Deliver:

- file tools
- Jujutsu history wrapper
- vLLM tool loop
- manual terminal testing against a sample vault

### Phase 1: web shell

Deliver:

- FastAPI app
- static mounts
- injected FAB and modal
- job submission endpoint
- SSE stream endpoint

### Phase 2: queue and mutation loop

Deliver:

- in-memory queue
- worker tasks
- per-file locking
- tool progress events
- rebuild trigger

### Phase 3: recovery and polish

Deliver:

- undo endpoint and UI action
- lightweight history endpoint
- better rebuild/failure messaging
- follow-up modal behavior
- metric instrumentation for Section 30

---

## 34. Deferred enhancements

After the MVP, likely next additions are:

1. optional selection-aware mode inside the same modal UX
2. simple recent-jobs page
3. richer history inspection UI
4. durable recent-job cache on disk
5. file move/rename tool
6. protected folders or path classes
7. incremental rebuild optimization
8. multi-step modal conversation persistence
9. benchmark automation and regression dashboards

---

## 35. Final recommendation

Build the simplified MVP exactly in its simplest form:

**render vault → open modal → describe intent → run agent → mutate files → record history with Jujutsu → rebuild → refresh or undo**

Do not reintroduce the heavier structured architecture too early.

The value of this version is not formal elegance.

The value is that it is small enough to build, understandable enough to trust, and measurable enough to harden into a daily control surface for a markdown vault.
