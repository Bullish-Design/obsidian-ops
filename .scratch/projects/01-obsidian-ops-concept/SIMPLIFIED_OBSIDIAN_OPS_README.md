# Obsidian Ops

Local-first operations overlay for an Obsidian vault.

Obsidian Ops is a small app that sits on top of a Kiln-rendered vault site. From any page, you click one floating action button, open one modal, describe what you want in natural language, and let a local agent work directly against your markdown files.

The vault is the source of truth. The rendered site is derived output. Jobs are transient and in memory. **Jujutsu is the durable history, diff, restore, and undo layer.**

---

## What it is

Obsidian Ops is:

- a **local overlay** on top of a rendered Obsidian vault
- a **single-modal interface** for natural-language note operations
- a **small async runtime** with an in-memory job queue
- a **tool-using local agent** that reads, writes, searches, and creates markdown files
- a **file-native system** with durable recovery through Jujutsu

## What it is not

Obsidian Ops is not:

- a browser IDE
- a command-registry app
- a selection-toolbar editing system
- a database-backed job platform
- a workflow engine
- a second custom history system layered on top of version control

---

## Core loop

The product is built around one simple loop:

**render vault → open modal → describe intent → run agent → mutate files → record durable history with Jujutsu → rebuild → refresh or undo**

That is the product.

---

## Why this exists

Most note tooling tends to fall into one of two buckets:

- manual editing everywhere, which is safe but slow
- highly structured automation, which is powerful but heavy, rigid, and hard to extend

Obsidian Ops takes a simpler path:

- natural-language input at the UI
- a very small tool surface at runtime
- direct markdown mutation in the vault
- confidence through durable history and easy recovery

The goal is not to force the user into a command tree. The goal is to let the user describe intent in plain language and have the system carry it out safely.

---

## User experience

From any rendered vault page:

1. Click the floating action button.
2. A modal opens with the current page path already available as context.
3. Type a request such as:
   - “clean up this note”
   - “summarize this page into a new note”
   - “find related notes and link them here”
   - “save this article into Sources and summarize it”
4. Submit the job.
5. Watch streamed progress in the same modal.
6. Review the result summary.
7. Refresh or undo if needed.

There is no command palette to learn, no toolbar ecosystem, and no separate structured action surface in v0.

---

## Product shape

Obsidian Ops has three real components:

- **browser**
- **server**
- **vault**

The agent runs inside the server. Kiln renders the vault as a site. Jujutsu provides durable history and recovery.

```text
Browser
  ├── Kiln-rendered vault pages
  ├── injected FAB + modal
  └── SSE listener for job updates
        │
        │ POST /api/jobs
        │ GET  /api/jobs/{job_id}/stream
        ▼
FastAPI app
  ├── serves generated site
  ├── serves /ops overlay assets
  ├── accepts jobs
  ├── streams job progress
  ├── runs in-memory queue + workers
  ├── runs agent/tool loop
  ├── calls Jujutsu wrapper
  └── triggers Kiln rebuilds
        │
        ├── vault markdown files
        ├── Jujutsu repo / working copy
        └── generated site output
```

---

## Architectural stance

The simplified MVP is intentionally opinionated.

### Keep

- one floating action button
- one modal
- natural-language instructions only
- one FastAPI process
- one in-memory async job queue
- low concurrency
- per-file in-process locking
- SSE progress streaming
- coarse rebuilds after successful writes
- thin wrappers around the renderer, LLM, and Jujutsu

### Avoid

- command registries
- command-specific public mutation APIs
- selection-toolbar UX in v0
- durable job databases
- SQLite metadata systems
- hybrid history designs
- large service or repository abstractions that add more mental overhead than value

---

## Runtime model

### Jobs

Jobs are transient and in memory.

That means:

- queued and running jobs do not need to survive restart in v0
- successful file changes remain durable because Jujutsu records them
- rendered site output can always be regenerated

### Concurrency

The runtime should stay conservative:

- low worker concurrency
- one active mutation per file at a time
- per-file locks inside the process

### Progress transport

Progress is streamed with SSE.

The modal is responsible for:

- showing queued and running state
- surfacing readable progress messages
- presenting the final summary
- exposing refresh and undo affordances

---

## Agent model

The agent is the core runtime behavior.

This is not a structured command platform with an agent facade layered on top. The app accepts user intent, gives the agent a small set of tools, and lets the agent decide how to perform the task.

### Agent inputs

Each job should provide:

- the user’s natural-language instruction
- the current page path
- optional current page content or nearby context
- tool definitions
- a short system prompt with preservation rules

### Typical prompt posture

The system prompt should stay small and general. It should emphasize rules like:

- preserve YAML frontmatter unless explicitly asked to change it
- preserve wikilinks unless explicitly asked to change them
- prefer minimal edits when possible
- do not delete content without clear user intent
- summarize changes after completion

---

## Tool surface

The recommended MVP tool set is intentionally small:

```text
read_file(path)
write_file(path, content)
list_files(glob="**/*.md")
search_files(query, glob="**/*.md")
fetch_url(url)
undo_last_change(path)
get_file_history(path, limit=10)
```

These tools are enough to support the core product loop without introducing a command taxonomy.

---

## History and undo

**Jujutsu is the authoritative durable history layer.**

That means:

- durable change history comes from Jujutsu
- undo and restore semantics are backed by Jujutsu
- recent file history is read through a thin Jujutsu wrapper
- the app does not build a second heavy snapshot or history system in parallel

User-facing language should stay simple:

- history
- changes
- restore
- undo

The user does not need to learn Jujutsu terminology to use the product confidently.

---

## Rendering model

Kiln is the renderer. Obsidian Ops is the overlay and orchestration layer around it.

After a successful mutation:

1. the agent writes files safely
2. the app records durable history through Jujutsu
3. Kiln rebuilds the site
4. the modal exposes refresh and undo actions

A coarse rebuild is acceptable in v0 if it keeps the implementation simpler.

---

## Canonical API surface

The public API should stay intentionally small.

### Required routes

- `POST /api/jobs`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}/stream`
- `POST /api/undo`
- `GET /api/history`

### Explicitly not canonical for v0

- `POST /api/rewrite`
- `POST /api/organize_note`
- `POST /api/save_url`
- `POST /api/edit/selection`
- `POST /api/edit/file`
- command-specific public endpoints in general

The app accepts **intent**, not a growing family of public command handlers.

---

## Example flow

### Submit a generic job

```json
{
  "instruction": "Find related notes and add a short Related section to this page.",
  "current_file_path": "Projects/Alpha/meeting-notes.md"
}
```

### Stream progress over SSE

Typical progress messages might look like:

- `job queued`
- `reading current file`
- `searching related notes`
- `writing updated markdown`
- `recording history`
- `rebuild started`
- `job completed`

The exact internal steps may vary, but the transport remains the same: one job submission, one progress stream, one result surface.

---

## Example use cases

### Clean up a note

- reorganize headings
- tighten prose
- preserve frontmatter and links
- keep the change reversible

### Create a synthesis note

- search related notes
- gather relevant context
- create a new markdown summary note
- link back to source notes

### Save and summarize a URL

- fetch a URL
- create a source note in the vault
- summarize the content
- preserve a durable recovery path if the result is not right

### Build an index page

- search a folder or topic
- collect references
- create a navigable index note
- refresh the rendered site

### Undo a bad result

- inspect recent history
- undo the last change
- refresh the rendered site
- continue working from the same modal

---

## Suggested project shape

A good v0 implementation should stay roughly this small:

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

This is the intended scale.

---

## Non-goals for v0

The simplified README should be read with these explicit non-goals in mind:

- no database-backed job system
- no durable queue recovery after restart
- no command registry
- no public command-specific mutation endpoints
- no selection-toolbar editing flow
- no hybrid history layer
- no app-owned snapshot system as the primary durability model
- no large multi-layer service architecture unless later scope explicitly changes

---

## Design principles

- **One modal is the product surface.**
- **Files are canonical.**
- **Natural language is the interface.**
- **Recovery is mandatory.**
- **Derived state is disposable.**
- **Minimal implementation is a feature.**

---

## Success criteria

The product direction is being honored when this feels true:

1. You can browse the vault normally in the browser.
2. You can open one modal from any page.
3. You can type a natural-language request.
4. You can watch streamed progress.
5. You can refresh and see the updated result.
6. You can undo confidently.
7. You never have to think in terms of a command tree.

---

## Final summary

Obsidian Ops v0 is a **local-first, Kiln-rendered, single-modal operations app** for an Obsidian vault.

It should feel small, direct, and confident:

- one modal
- one generic job surface
- one small tool-using agent loop
- one durable history model through Jujutsu

That is the canonical simplified README direction.
