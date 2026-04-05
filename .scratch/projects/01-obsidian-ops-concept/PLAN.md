# Obsidian Ops — Project Plan

> **NO SUBAGENTS:** Never use subagents (the Task tool) under any circumstances. Do all work directly.

## Overview

Local-first operations overlay for an Obsidian vault. A FastAPI app that serves a Kiln-rendered vault site, injects a lightweight operations overlay (FAB + modal), accepts natural-language instructions, runs a tool-using agent against vault markdown files, records durable history through Jujutsu, and triggers Kiln rebuilds.

## Implementation Steps

| # | Step | Status | Dependencies |
|---|------|--------|-------------|
| 1 | Scaffold project structure, pyproject.toml, config, models | done | — |
| 2 | Implement per-file locking and atomic writes | done | — |
| 3 | Implement Jujutsu history wrapper | done | — |
| 4 | Implement Kiln rebuild wrapper | done | — |
| 5 | Implement page context inference | done | — |
| 6 | Implement tool surface (read, write, list, search, fetch, history) | done | 2, 3 |
| 7 | Implement agent loop | done | 6 |
| 8 | Implement in-memory job queue with SSE subscribers | done | — |
| 9 | Implement overlay injection | done | — |
| 10 | Create browser overlay assets (ops.css, ops.js) | done | — |
| 11 | Wire FastAPI app with all routes | done | 3–10 |
| 12 | Write unit tests (atomic, page_context, queue, inject) | pending | 1–11 |
| 13 | Write integration tests (API, Jujutsu) | pending | 12 |
| 14 | Manual acceptance pass with real vault | pending | 13 |

## Acceptance Criteria

1. Generated site is served locally with operations overlay injected
2. FAB appears on rendered pages
3. Modal can submit natural-language instruction with current page context
4. Worker executes agent loop and streams progress via SSE
5. Agent can read and write markdown files through tools
6. Successful writes are recorded in Jujutsu-backed durable history
7. Successful writes trigger a rebuild
8. Modal reports final success or failure
9. User can undo the latest change for a file
10. System remains usable after repeated daily note-maintenance workflows
