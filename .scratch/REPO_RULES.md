# REPO RULES — Remora

## ABSOLUTE RULES — READ FIRST

1. **NO SUBAGENTS** — NEVER use the Task tool. Do ALL work directly. No exceptions.
2. **NEVER STOP AFTER COMPACTION** — Read CONTEXT.md, check PROGRESS.md, resume immediately. Keep working until the project is FULLY DONE.

---

Repo-specific standards and conventions. Loaded after `CRITICAL_RULES.md`.
These are **in addition to** the universal coding standards in CRITICAL_RULES.

---

## devenv.sh Environment (MANDATORY for execution/testing)

Use `devenv shell --` for commands that execute project code or tooling (tests, scripts, linters, formatters, dependency sync, app/runtime commands).  
You do **not** need `devenv shell --` for routine read-only shell inspection commands (e.g. `ls`, `cat`, `rg`, `git log`, `git show`).

**CRITICAL: Before the first test run in every session, ALWAYS sync dependencies:**
```bash
devenv shell -- uv sync --extra dev
```

**NEVER use `uv pip install`. ALWAYS use `uv sync`.**

```bash
devenv shell -- pytest tests/unit/test_lsp_graph.py -v
devenv shell -- ruff check src/
devenv shell -- ty check src
devenv shell -- uv sync --extra dev
```
For scripts/tests/tooling, never run `python`, `pytest`, `uv run`, or similar directly from system PATH.

---

## Hard Dependencies

All packages in `pyproject.toml` `[project.dependencies]` are hard dependencies:
- Import unconditionally (no `try/except ImportError` guards).
- Test unconditionally (no `pytest.mark.skipif` for missing deps).

---

## Coding Standards (repo-specific)


---

## Key Reference Files

| Document | Path |
|----------|------|


---

## Architecture Overview



---

## Test Suite

```
devenv shell -- python -m pytest tests/ --ignore=tests/benchmarks --ignore=tests/integration/cairn -q
```
