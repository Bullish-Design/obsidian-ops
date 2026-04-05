# Simplified Obsidian Ops Console — Concept Document (Revised Canonical Version)

## 1. One-Sentence Pitch

A floating action button on your Kiln-rendered vault site opens a text input modal; you describe what you want done to the current note or vault, a local LLM agent with file tools executes it, and Jujutsu provides durable history and instant recovery.

---

## 2. Mental Model

```text
User types instruction ──► Agent receives instruction + current page context
                           Agent calls tools (read, write, search, fetch)
                           Writes are recorded through Jujutsu-backed history
                           ◄── Agent responds with summary + refresh/undo affordances
```

There is no command registry. No structured mutation protocol. No per-command UI surface. The agent has tools and a system prompt. The user describes what they want in natural language. The agent figures out the rest.

**The safety net is Jujutsu-backed durable history, not app-owned snapshot machinery.** The app writes markdown files directly, records durable change history through Jujutsu, and exposes simple undo/history actions in the UI.

---

## 3. Product Shape

The product has three real components:

- **browser**
- **server**
- **vault**

The agent is a loop inside the server. Kiln renders the vault as a site. Jujutsu provides durable change history and recovery.

```text
┌─────────────────────────────────────────────────┐
│ Browser                                         │
│                                                 │
│  Kiln-rendered vault site                       │
│  + injected FAB button ──► input modal          │
│  + SSE listener for job updates                 │
│                                                 │
└──────────────┬──────────────────────────────────┘
               │ POST /api/jobs
               │ GET  /api/jobs/{job_id}/stream
               ▼
┌─────────────────────────────────────────────────┐
│ FastAPI (single process)                        │
│                                                 │
│  Static mount: /        ► generated site        │
│  Static mount: /ops/    ► FAB + modal assets    │
│  API routes:  /api/     ► jobs + undo + history │
│                                                 │
│  in-memory async queue ─► agent workers         │
│                                                 │
└──────────────┬──────────────────────────────────┘
               │
       ┌───────┴────────┬──────────────┐
       ▼                ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│ Agent Loop  │  │ Vault Files │  │ Jujutsu      │
│ + vLLM      │  │ Markdown    │  │ history/undo │
└─────────────┘  └─────────────┘  └──────────────┘
```

---

## 4. Interaction Flow

### 4.1 User Experience

1. User browses their vault as a locally served Kiln-rendered site.
2. A floating action button sits in the bottom-right corner of every page.
3. Click FAB → modal opens with:
   - current page path shown as context
   - one text input: “What would you like to do?”
   - submit button
4. User types something like:
   - “clean up the structure of this note”
   - “create a summary note from this page”
   - “find related notes and add links”
   - “save this article into Sources and summarize it”
5. Modal shows queued/running progress via SSE.
6. Agent works: reads files, searches the vault, optionally fetches a URL, writes files, records durable history through Jujutsu, and triggers a rebuild.
7. Modal shows a summary of what happened plus refresh and undo actions when available.
8. User refreshes and sees the updated vault content.

### 4.2 The Modal Is the Entire UI Surface

No selection toolbar. No per-command buttons. No status dashboard required for the core loop. No activity feed panel required in v0.

One modal handles everything:

- **Input**: free-text instruction
- **Context**: current page path, automatically populated
- **Progress**: streamed status/tool activity
- **Output**: final summary and result state
- **Actions**: refresh, undo, optional follow-up prompt in the same modal session

This is the center of the product. The user should not need to learn a command tree.

---

## 5. Agent Design

### 5.1 System Prompt

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

That is enough for v0. The user’s natural-language instruction carries the specific intent.

### 5.2 Tools

```text
read_file(path: str) -> str
    Read a file from the vault, including frontmatter.

write_file(path: str, content: str, summary: str | None = None) -> ToolResult
    Write content to a vault file atomically.
    Record durable history through the Jujutsu wrapper.

list_files(glob: str = "**/*.md") -> list[str]
    List files in the vault.

search_files(query: str, glob: str = "**/*.md") -> list[{path, matches}]
    Search file contents with surrounding context.

fetch_url(url: str) -> str
    Fetch a URL and return content suitable for note creation or summarization.

undo_last_change(path: str) -> ToolResult
    Restore the most recent eligible change for a file through the app’s Jujutsu-backed history wrapper.

get_file_history(path: str, limit: int = 10) -> list[HistoryEntry]
    Return recent history entries for a file.
```

Seven tools are enough for the MVP.

### 5.3 Agent Loop

The agent uses a standard tool-use loop:

```text
1. Send system prompt + user instruction + page context + tool definitions to vLLM
2. vLLM responds with text and/or tool calls
3. Execute tool calls and collect results
4. Send tool results back to vLLM
5. Repeat until the model returns a final response
6. Stream intermediate progress and final summary to the browser
```

No command registry is required.

---

## 6. Job Queue and Concurrency

### 6.1 Why a Queue Exists

The queue exists so the UI can remain responsive while the agent works and so multiple jobs can be processed with bounded concurrency.

### 6.2 Queue Design

Jobs are intentionally **in memory only** in v0.

```python
@dataclass
class Job:
    id: str
    instruction: str
    file_path: str | None
    status: str = "queued"       # queued -> running -> succeeded / failed
    agent_messages: list = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
```

This is acceptable because:

- the product is local-first and single-user
- queued/running jobs do not need to survive restart in v0
- durable history of successful writes is provided by Jujutsu, not by the queue

### 6.3 Concurrency Rules

- low concurrency by default
- per-file locking required
- one active mutation per file at a time
- SSE is the progress transport

---

## 7. Jujutsu as the Durable History Layer

### 7.1 Core Stance

Jujutsu is the authoritative durable history and recovery layer.

The app should rely on it rather than building a second heavy custom history system.

### 7.2 What That Means

This replaces:

- a database-backed history ledger
- a custom snapshot store
- a hybrid history subsystem
- app-owned diff bookkeeping as the primary durability model

With:

- durable history for changed files
- undo/restore capability
- recent file history inspection
- diff/recovery operations behind a thin Jujutsu wrapper

### 7.3 Product-Language Rule

The UI should mostly say:

- history
- changes
- restore
- undo

It does not need to force VCS terminology into the product surface.

---

## 8. Kiln Integration: Minimal Overlay

### 8.1 Post-Build Injection

The site is rendered by Kiln. After build, the app injects a very small overlay into pages:

- `ops.js`
- `ops.css`

That overlay is responsible for:

- floating action button
- modal rendering
- job submission
- SSE progress updates
- refresh/undo affordances

### 8.2 Rebuild Strategy

After any successful file mutation:

1. file write completes safely
2. durable history is recorded through the Jujutsu wrapper
3. Kiln rebuild is triggered
4. modal exposes refresh once the result is ready

A coarse rebuild is acceptable in v0 if it keeps the implementation simpler.

---

## 9. FastAPI Server Shape

The server should stay extremely small.

Recommended public surface:

- `POST /api/jobs`
- `GET /api/jobs/{job_id}/stream`
- `GET /api/jobs`
- `POST /api/undo`
- `GET /api/history`

This is intentionally different from a command-specific API surface.

The simplified product should not grow endpoints like:

- `/api/rewrite`
- `/api/organize_note`
- `/api/save_url`
- `/api/edit/selection`

The app accepts intents, not commands.

---

## 10. Project Structure

A good implementation should stay around this scale:

```text
obsidian-ops/
├── app.py
├── config.py
├── queue.py
├── agent.py
├── tools.py
├── history_jj.py
├── rebuild.py
├── inject.py
├── static/
│   ├── ops.js
│   └── ops.css
└── tests/
```

That is the right order of magnitude.

No database. No migration scripts. No command registry. No structured endpoint sprawl.

---

## 11. Comparison to the Heavier Alternative

| Aspect | Heavier structured path | Simplified canonical path |
|---|---|---|
| Interaction model | many actions, toolbars, command surfaces | single modal |
| Command system | explicit command registry | natural language + tools |
| Jobs | durable DB-backed queue | in-memory queue |
| History | custom or hybrid app-owned history | Jujutsu-backed durable history |
| API | command-specific mutation endpoints | generic job submission |
| UI | multiple control surfaces | one FAB + one modal |
| Architecture | layered service/runtime heavy design | thin app + thin wrappers |

### What Is Gained

- much smaller mental model
- fewer moving parts
- much easier implementation path
- broader capability from the same simple tool surface
- strong recovery without inventing a second durability subsystem

### What Is Lost

- some determinism compared with hard-coded command modules
- durable queued job recovery after restart
- structured editing affordances like selection toolbar UX
- rich app-owned history metadata in v0

That tradeoff is correct for this product.

---

## 12. Success Criteria

The concept is being honored when all of this feels true:

1. browse vault normally in the browser
2. click FAB from any page
3. type a natural-language request
4. watch streamed progress in the modal
5. refresh and see updated content
6. undo the result confidently
7. inspect recent file history when needed

The core loop is:

**open modal → describe intent → let agent work → review result → refresh or undo → repeat**
