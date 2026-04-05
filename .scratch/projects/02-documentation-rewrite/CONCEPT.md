# Obsidian Ops — Concept

## 1. One-sentence pitch

A floating action button on your Kiln-rendered vault site opens a modal where you describe what you want done; a local LLM agent with file tools executes it, and Jujutsu provides durable history and instant recovery.

---

## 2. What the product is

Obsidian Ops is a **local-first operations overlay** for an Obsidian vault.

The user browses their vault as a Kiln-rendered website served locally. A floating action button sits on every page. Clicking it opens one modal. The user types a natural-language instruction. A local agent receives that instruction plus the current page context, uses a small set of file tools to read, write, search, and fetch, then reports what it did. Jujutsu records every successful mutation as a durable, undoable change boundary.

The product is:

- a local overlay on a rendered Obsidian vault
- an agentic file-operations surface for markdown
- a small async runtime with a minimal UI
- a file-native system with durable recovery through Jujutsu

The product is not:

- a browser IDE or collaborative editor
- a command-registry app or structured workflow engine
- a database-backed job system
- a toolbar-heavy editing surface
- a second history system layered on top of version control

---

## 3. Mental model

```text
User types instruction --> Agent receives instruction + current page context
                           Agent calls tools (read, write, search, fetch)
                           Writes are recorded through Jujutsu
                           <-- Agent responds with summary + refresh/undo affordances
```

There is no command registry. No structured mutation protocol. No per-command UI surface. The agent has tools and a system prompt. The user describes what they want. The agent figures out the rest.

The safety net is Jujutsu-backed durable history, not app-owned snapshot machinery.

---

## 4. Product shape

Three real components:

- **Browser** — Kiln-rendered vault site with an injected overlay (FAB + modal + SSE listener)
- **Server** — single FastAPI process serving the site, overlay assets, API endpoints, in-memory queue, and agent workers
- **Vault** — Obsidian markdown files under a Jujutsu workspace

```text
Browser
  |-- Kiln-rendered vault pages
  |-- injected FAB + modal (ops.js, ops.css)
  |-- SSE listener for job progress
        |
        | POST /api/jobs
        | GET  /api/jobs/{job_id}/stream
        v
FastAPI (single process)
  |-- site mount: /
  |-- ops asset mount: /ops/
  |-- API routes: /api/*
  |-- in-memory queue --> worker tasks
  |-- agent loop + tool runtime
  |-- Jujutsu wrapper
  |-- Kiln rebuild wrapper
        |
        |-- vault markdown files
        |-- Jujutsu repo / working copy
        |-- generated site output
```

---

## 5. Core loop

**render vault -> open modal -> describe intent -> run agent -> mutate files -> record history with Jujutsu -> rebuild -> refresh or undo**

That is the product.

---

## 6. Interaction model

### 6.1 User experience

1. User browses their vault as a locally served Kiln-rendered site.
2. A floating action button sits in the bottom-right corner of every page.
3. Click FAB -> modal opens with:
   - current page path shown as context
   - one text input: "What would you like to do?"
   - submit button
4. User types something like:
   - "clean up the structure of this note"
   - "create a summary note from this page"
   - "find related notes and add links"
   - "save this article into Sources and summarize it"
5. Modal shows queued/running progress via SSE.
6. Agent works: reads files, searches the vault, optionally fetches a URL, writes files, records durable history through Jujutsu, and triggers a rebuild.
7. Modal shows a summary of what happened plus refresh and undo actions.
8. User refreshes and sees the updated content.

### 6.2 The modal is the entire UI surface

One modal handles everything:

- **Input**: free-text instruction
- **Context**: current page path, automatically populated
- **Progress**: streamed status and tool activity
- **Output**: final summary and result state
- **Actions**: refresh, undo, optional follow-up prompt in the same session

The user does not need to learn a command tree, a toolbar, or a dashboard.

---

## 7. Agent design

### 7.1 System prompt

```text
You are an assistant that helps manage and improve notes in an Obsidian vault.
You have tools to read, write, list, search, fetch URLs, inspect history, and undo changes.

Rules:
- Preserve YAML frontmatter unless the user asks to change it.
- Preserve wikilinks unless the user asks to change them.
- Do not delete content unless the user clearly intends that outcome.
- Prefer minimal, local edits when possible.
- When creating new files, use sensible markdown structure.
- After making changes, summarize what you did briefly.

The user is currently viewing: {current_file_path}
```

One general prompt. No command-specific templates.

### 7.2 Tool surface

```text
read_file(path) -> str
write_file(path, content) -> str
list_files(glob="**/*.md") -> list[str]
search_files(query, glob="**/*.md") -> list[{path, snippet}]
fetch_url(url) -> str
undo_last_change() -> str
get_file_history(path, limit=10) -> list[str]
```

Seven tools. That is the MVP.

### 7.3 Agent loop

Standard tool-use loop:

1. Send system prompt + user instruction + page context + tool definitions to vLLM
2. Model responds with text and/or tool calls
3. Execute tool calls, collect results
4. Send results back to the model
5. Repeat until the model returns a final response
6. Stream intermediate progress and final summary to the browser

### 7.4 Model requirements

The local LLM must support:

- OpenAI-compatible Chat Completions API with tool use
- Reliable instruction following for file operations
- Context window sufficient for page content + tool results (16K+ tokens recommended)
- Consistent JSON output for tool-call arguments

The quality of the product experience is directly proportional to model quality. A 70B+ parameter model with strong tool-use capabilities is recommended. Smaller models may produce unreliable results that require frequent undo.

---

## 8. Job queue

### 8.1 Design

Jobs are **in-memory only**.

```python
@dataclass
class Job:
    id: str
    instruction: str
    file_path: str | None
    status: str           # queued -> running -> succeeded / failed
    messages: list[str]
    result: dict | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
```

This is acceptable because:

- the product is local-first and single-user
- queued/running jobs do not need to survive restart
- durable history of successful writes comes from Jujutsu, not the queue

### 8.2 Concurrency

- **Default: 1 worker.** This is a locked decision for v0.
- Per-file locking required.
- One active mutation per file at a time.
- SSE is the progress transport.

Single-worker concurrency is required for correct undo semantics. With one worker, there is a 1:1 mapping between jobs and Jujutsu change boundaries, which makes `jj undo` reliably reverse the last user-visible operation. Raising concurrency requires redesigning undo (see Section 10.2).

---

## 9. Jujutsu as the durable history layer

### 9.1 Core stance

Jujutsu is the authoritative durable history and recovery layer. The app does not build a second history system.

This replaces:

- database-backed history ledgers
- custom snapshot stores
- hybrid history subsystems
- app-owned diff bookkeeping

With:

- durable history for changed files
- undo/restore capability
- recent file history inspection
- diff/recovery behind a thin wrapper

### 9.2 One commit per job

Each successful mutating job performs exactly one `jj commit -m "<summary>"`. This creates a clean, predictable history boundary. Undo is `jj undo`. One job = one change = one undo.

### 9.3 Product language

The UI says:

- history
- changes
- restore
- undo

It does not force VCS terminology into the product surface.

---

## 10. Known limitations and risks

### 10.1 LLM quality dependence

The product value depends almost entirely on the local LLM's ability to interpret instructions and use tools correctly. There are no programmatic guardrails against bad model output beyond the max-iterations limit. A diff preview or dry-run mode would increase trust but is deferred from v0.

### 10.2 Undo only works reliably at concurrency=1

The undo model uses `jj undo`, which reverses the most recent Jujutsu operation globally. If concurrency is raised above 1, undo may reverse the wrong job. Raising concurrency requires switching to `jj restore` with specific change IDs.

### 10.3 Search is linear scan

The `search_files` tool scans vault files sequentially with substring matching. This is acceptable for small vaults but will be slow at 10,000+ files. A search index is a likely early optimization.

### 10.4 Coarse rebuilds add latency

Full `kiln generate` runs after every successful mutation. Combined with agent execution and jj commit, end-to-end job latency may reach 15-30 seconds for medium vaults.

### 10.5 No authentication

The server has no auth. It must bind to `127.0.0.1` by default to avoid network exposure.

---

## 11. Rendering and rebuild

### 11.1 Kiln integration

Kiln renders the vault into a static site. After build, the app injects a small overlay (`ops.js`, `ops.css`) into rendered HTML pages.

### 11.2 Rebuild strategy

After any successful mutation:

1. File write completes
2. `jj commit` records the change
3. `kiln generate` rebuilds the site
4. Overlay is re-injected
5. Modal exposes refresh

Coarse full rebuilds are acceptable in v0.

---

## 12. API surface

Intentionally small:

- `POST /api/jobs` — submit a natural-language job
- `GET /api/jobs/{job_id}/stream` — SSE progress stream
- `GET /api/jobs` — list recent jobs
- `POST /api/undo` — undo the last change
- `GET /api/history` — file history

The app accepts **intent**, not commands. No command-specific endpoints.

---

## 13. Project structure

```text
obsidian_ops/
  app.py
  config.py
  models.py
  queue.py
  agent.py
  tools.py
  history_jj.py
  rebuild.py
  inject.py
  locks.py
  fs_atomic.py
  page_context.py
  static/
    ops.js
    ops.css
tests/
```

No database. No migration scripts. No command registry. No endpoint sprawl.

---

## 14. Assumptions

- Python 3.13+
- FastAPI as the web framework
- Kiln installed and available as `kiln`
- Jujutsu installed and available as `jj`
- The vault is already inside a Jujutsu workspace (`.jj/` exists)
- vLLM running an OpenAI-compatible Chat API endpoint
- Single local user in a trusted environment
- Server binds to `127.0.0.1` by default

---

## 15. Success criteria

The concept is honored when all of this feels true:

1. Browse the vault normally in the browser
2. Click FAB from any page
3. Type a natural-language request
4. Watch streamed progress in the modal
5. Refresh and see updated content
6. Undo the result confidently
7. Never think in terms of a command tree

---

## 16. What is explicitly out of scope for v0

- Command registries or command-specific endpoints
- Selection toolbar or structured editing UX
- Database-backed job or history systems
- Multi-user coordination or authentication
- Plugin ecosystem
- Background autonomous vault scanning
- Durable job recovery after restart
- Rich diff UI or history browser
- Incremental rebuilds
- Cross-session conversation memory
