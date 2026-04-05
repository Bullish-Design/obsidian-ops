# Canonical Direction — Simplified Obsidian Ops

## Document status

- Status: Canonical direction
- Product: Obsidian Ops Console
- Variant: Simplified MVP
- Purpose: Resolve documentation drift and establish the authoritative direction for the simplified product

---

## 1. Canonical product statement

Obsidian Ops v0 is a **local-first, Kiln-rendered, single-modal operations app** for an Obsidian vault.

The user browses their vault as a generated website. A floating action button opens one modal. The user types a natural-language instruction. A local agent receives that instruction plus page context, uses a very small set of file tools, mutates markdown files in the vault, triggers a rebuild, and reports what it did.

**Jujutsu is the durable history, diff, restore, and undo layer.**

This is the canonical direction for the simplified product.

---

## 2. What the product is

The product is:

- a local overlay on top of a rendered Obsidian vault
- an agentic file-operations surface for markdown
- a small async runtime with a tiny UI
- a file-native system with durable recovery through Jujutsu

The product is not:

- a browser IDE
- a command-registry app
- a structured workflow engine
- a database-backed job system
- a toolbar-heavy editing surface
- a second parallel history system layered on top of VCS

---

## 3. Locked decisions

These decisions are canonical for the simplified MVP.

### 3.1 Interaction model

- one floating action button on every page
- one modal for input, progress, results, follow-up, refresh, and undo
- natural-language instructions only
- no selection toolbar in v0
- no per-command button ecosystem in v0
- no multi-surface command UI in v0

### 3.2 Runtime model

- one FastAPI process
- one in-memory async job queue
- one generic tool-use agent loop
- low concurrency
- per-file in-process locking
- SSE for progress streaming

### 3.3 Persistence model

- vault markdown files are the source of truth
- Jujutsu is the only durable history/recovery substrate in v0
- in-memory job state is acceptable
- loss of queued/running jobs on restart is acceptable
- rendered site output is derived and disposable

### 3.4 Architecture posture

- no SQLite database in v0
- no durable jobs database
- no custom snapshot store
- no hybrid history model
- no command registry
- no public command-specific API surface for normal operation

### 3.5 Rendering posture

- Kiln renders the vault into a static-ish site
- the app injects a lightweight operations overlay into rendered pages
- successful mutations trigger a coarse rebuild in v0
- coarse rebuilds are acceptable if they keep the architecture simpler

---

## 4. Canonical user flow

1. User opens the locally served rendered vault.
2. User clicks the floating action button.
3. Modal opens with the current page path already available as context.
4. User types a natural-language instruction.
5. The app creates an in-memory job.
6. The agent runs, calls file tools, and emits streamed progress events.
7. If files change, the app records durable history through Jujutsu and triggers a rebuild.
8. The modal shows a final summary, refresh affordance, and undo action when available.
9. The user refreshes or continues the conversation in the same modal session.

---

## 5. Canonical API surface

Keep the public API intentionally small.

### Required

- `POST /api/jobs`
- `GET /api/jobs/{job_id}/stream`
- `GET /api/jobs`
- `POST /api/undo`
- `GET /api/history` (lightweight, optional but recommended)

### Explicitly not canonical for v0

- `POST /api/rewrite`
- `POST /api/organize_note`
- `POST /api/save_url`
- `POST /api/edit/selection`
- `POST /api/edit/file`
- command-specific public endpoints in general

The simplified app should accept user intent through a generic job submission API, not through a growing command-specific surface.

---

## 6. Canonical agent/tool model

The agent should operate through a very small tool set.

Recommended tool surface:

- `read_file(path)`
- `write_file(path, content)`
- `list_files(glob="**/*.md")`
- `search_files(query, glob="**/*.md")`
- `fetch_url(url)`
- `undo_last_change(path)` or equivalent app-level undo wrapper
- `get_file_history(path, limit=10)`

Guiding rules:

- no command registry behind the scenes
- no command-specific prompt templates are required for v0
- one general system prompt is preferred
- the agent interprets user language rather than routing through a command taxonomy

---

## 7. Canonical Jujutsu stance

Jujutsu is the authoritative durable ledger for app-triggered changes.

That means:

- durable change history comes from Jujutsu
- undo/restore semantics are backed by Jujutsu
- recent file history is read through a thin Jujutsu wrapper
- the app should not build a second heavy snapshot/history system in parallel

User-facing UX should mostly speak in app terms:

- history
- changes
- restore
- undo

The app does not need to force Jujutsu terminology into the UI when simple product language is clearer.

---

## 8. Canonical simplifications

These simplifications are intentional and should be protected.

### Keep

- single modal
- in-memory queue
- SSE progress
- per-file locks
- coarse rebuild after successful writes
- minimal overlay JS/CSS
- thin wrappers around renderer, VCS, and LLM

### Avoid

- structured selection-edit protocols
- selection toolbar UX in v0
- command-module proliferation
- database-backed metadata systems
- hybrid history designs
- large service/repository abstractions that add more mental overhead than value

---

## 9. What this means for the current docs

### Closest to canonical

- `SIMPLIFIED_OBSIDIAN_OPS_SPEC_JUJUTSU.md`

### Needs light alignment

- `SIMPLIFIED_OBSIDIAN_OPS_CONCEPT.md`

### Needs substantial rewrite

- `SIMPLIFIED_OBSIDIAN_OPS_ARCHITECTURE.md`
- `SIMPLIFIED_OBSIDIAN_OPS_README.md`
- `SIMPLIFIED_OBSIDIAN_OPS_IMPLEMENTATION_GUIDE.md`

The biggest corrections needed across the docs are:

- remove Git as the primary durable history model
- remove command-specific public APIs as the main shape
- remove selection-toolbar and structured edit assumptions from v0
- remove database and hybrid-history assumptions from the simplified path

---

## 10. Canonical implementation target

A good v0 implementation should feel roughly like this:

- a small FastAPI app
- a rendered site mount
- an `/ops` static asset mount
- an in-memory queue with a few workers
- a generic job route
- an SSE route
- a small agent loop
- a thin Jujutsu wrapper
- a thin Kiln rebuild wrapper
- per-file locking

That is the intended center of gravity.

If an implementation starts drifting toward:

- command registries
- many public mutation endpoints
- DB-backed state ledgers
- custom snapshot stores
- selection-specific editing subsystems

then it is drifting away from the canonical simplified direction.

---

## 11. Final governing statement

**Render vault → open modal → describe intent → run agent → mutate files → record durable history with Jujutsu → rebuild → refresh or undo.**

That is the simplified product.
