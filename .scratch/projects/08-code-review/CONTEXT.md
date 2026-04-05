# Code Review — Context

## Scope

Full codebase review of `obsidian-ops` at commit `8c46e29` (HEAD of `main`).

- **Package**: `obsidian_ops` — 13 Python modules, 1159 LOC (source), 528 LOC (tests)
- **Frontend**: 2 static files (ops.css 174 LOC, ops.js 270 LOC)
- **Infrastructure**: devenv.nix + devenv.yaml (Nix flake), pyproject.toml (hatchling build)
- **Demo**: Typer CLI (`demo_cli.py`) + sample vault + shell script
- **Dependencies**: pydantic 2, pydantic-settings, typer, fastapi, uvicorn, openai, httpx
- **Python target**: 3.13 (enforced via devenv + pyproject.toml)
- **VCS for vault**: Jujutsu (jj), not git

## Architecture Summary

obsidian-ops is a local-first web overlay for an Obsidian vault. It:

1. Takes a vault directory of markdown files as input
2. Uses **Kiln** (a static site generator) to render the vault to HTML
3. Injects a floating action button (FAB) overlay into every generated HTML page
4. Serves the generated site via FastAPI with a `/ops` panel for AI-assisted editing
5. Routes user instructions through an LLM agent (OpenAI-compatible API, targeting vLLM)
6. The agent has tools to read/write/search vault files, fetch URLs, and inspect jj history
7. After changes, the worker commits via jj, rebuilds with Kiln, and re-injects the overlay
8. SSE streaming delivers real-time progress to the browser

## Data Flow

```
Browser FAB -> POST /api/jobs -> JobQueue -> run_worker
  -> Agent.run (LLM tool loop) -> ToolRuntime (read/write/search/fetch)
  -> jj commit -> KilnRebuilder -> inject_overlay -> SSE "done"
  -> Browser receives SSE, shows summary, offers Refresh/Undo
```
