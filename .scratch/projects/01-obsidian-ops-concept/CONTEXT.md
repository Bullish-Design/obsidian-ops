# Obsidian Ops — Context

## Current State

Project scaffold is complete. All core source files have been created per the implementation guide:

- `src/obsidian_ops/` — all 12 modules implemented (config, models, locks, fs_atomic, history_jj, rebuild, page_context, inject, tools, agent, queue, app)
- `src/obsidian_ops/static/` — ops.css and ops.js browser overlay
- `pyproject.toml` — configured with obsidian-ops name, ty typechecker
- `.tmuxp.yaml` — updated to reflect obsidian-ops

## What Just Happened

Scaffolded the entire project from the concept documents in `.scratch/projects/01-obsidian-ops-concept/`. All source files were created following the `SIMPLIFIED_OBS:

- Single FastAPI process
- In-memory async job queue with SSE
- OpenAI-compatible tool-use agent loop (vLLM)
- Jujutsu-backed durable history
- Kiln rebuild wrapper
- Per-file async locking
- Atomic file writes
- Browser overlay (FAB + modal)

## What's Next

1. Write unit tests (test_atomic, test_page_context, test_queue, test_inject)
2. Write integration tests (API endpoints, Jujutsu integration)
3. Run ty type checker to verify type correctness
4. Run ruff to verify linting
5. Manual acceptance pass with a real vault

## Key Decisions

- Using `ty` (Astral) instead of mypy for type checking
- Python 3.13 as minimum version
- hatchling as build backend
- pydantic for models/settings
- httpx for async HTTP (URL fetching)
- openai SDK for vLLM communication (OpenAI-compatible API)
