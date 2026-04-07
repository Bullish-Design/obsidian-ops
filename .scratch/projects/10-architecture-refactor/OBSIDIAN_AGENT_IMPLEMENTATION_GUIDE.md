# OBSIDIAN_AGENT_IMPLEMENTATION_GUIDE

## Table of Contents

1. Purpose and Scope
   - What this guide covers, what is explicitly out of scope for the intern.
2. Success Criteria (Definition of Done)
   - Concrete completion criteria for API behavior, tests, and local run flow.
3. Required Inputs and Preconditions
   - Prerequisite tools, expected repositories, and environment assumptions.
4. High-Level Implementation Plan
   - Ordered phases and why the sequence reduces risk.
5. Step 1: Create the repository skeleton
   - Files/directories to create and baseline packaging setup.
   - Verification gate: package import and repo layout checks.
6. Step 2: Define project metadata and dependencies
   - `pyproject.toml`, dev dependencies, scripts, pytest/ruff config.
   - Verification gate: dependency sync and static checks command success.
7. Step 3: Add runtime settings (`config.py`)
   - `AgentSettings`, env-prefix strategy, validators, cached loader.
   - Verification gate: config unit tests and negative validation cases.
8. Step 4: Add API models (`models.py`)
   - `ApplyRequest`, `OperationResult`, response semantics.
   - Verification gate: serialization/validation tests.
9. Step 5: Migrate foundation modules unchanged
   - `fs_atomic.py`, `locks.py`, `page_context.py` copy strategy.
   - Verification gate: carried-over unit tests pass with import updates.
10. Step 6: Add VCS adapter module (`vcs.py`)
    - Migrate `JujutsuHistory`, rename from `history_jj.py`, retain behavior.
    - Verification gate: VCS tests with mocked subprocess behavior.
11. Step 7: Add tool runtime (`tools.py`)
    - Import rewiring and tool definitions/execution path checks.
    - Verification gate: per-tool tests on temporary vault fixtures.
12. Step 8: Add agent runner (`agent.py`)
    - Introduce `AgentRunner` protocol and adapt progress callback contract.
    - Verification gate: mocked LLM/tool-calling loop tests.
13. Step 9: Build FastAPI app (`app.py`)
    - Lifespan wiring, `/api/health`, `/api/apply`, `/api/undo`, timeout behavior.
    - Verification gate: endpoint tests for success/no-op/failure/timeout.
14. Step 10: Add executable entrypoint (`__main__.py`)
    - Uvicorn startup wiring and env-driven host/port launch.
    - Verification gate: process launch and health check curl test.
15. Step 11: End-to-end local verification
    - Manual vault test flow for apply + undo.
    - Verification gate: HTTP responses + filesystem/JJ outcomes.
16. Step 12: Final QA checklist and handoff notes
    - Required artifacts before opening PR.
17. Appendix A: Endpoint contract reference
    - Final request/response examples.
18. Appendix B: Test command matrix
    - Exact commands, order, and expected outcomes.
19. Appendix C: Common failure modes and fixes
    - Fast diagnosis playbook for intern blockers.

## 1. Purpose and Scope

This guide is for implementing the **obsidian-agent** repository from scratch according to `SIMPLIFIED_CONCEPT.md`.

In scope:
- Build a standalone Python service exposing `/api/apply`, `/api/undo`, `/api/health`.
- Run the existing agent loop and vault tools synchronously (no SSE, no queue).
- Commit changes with Jujutsu when edits occur.
- Provide comprehensive tests and a repeatable local verification flow.

Out of scope:
- Forge (Go) implementation.
- obsidian-ops process supervisor/CLI implementation.
- Streaming progress UX.
- `/api/history` endpoint.

## 2. Success Criteria (Definition of Done)

The implementation is complete only when all of these are true:

1. `obsidian-agent` starts with `python -m obsidian_agent` and serves `/api/health`.
2. `POST /api/apply` returns `OperationResult` and handles success, no-op, failure, and timeout.
3. `POST /api/undo` returns `OperationResult` and performs `jj undo`.
4. If apply produces file changes, the service commits via Jujutsu.
5. No SSE routes, SSE models, queue worker, or broadcaster exist in this repo.
6. Unit tests for config/models/app/agent/tools/vcs/foundation modules pass.
7. Manual end-to-end verification against a temporary vault passes.

## 3. Required Inputs and Preconditions

Before starting, confirm:

1. You have the source monolith repository available (for copying modules):
   - `src/obsidian_ops/agent.py`
   - `src/obsidian_ops/tools.py`
   - `src/obsidian_ops/fs_atomic.py`
   - `src/obsidian_ops/locks.py`
   - `src/obsidian_ops/page_context.py`
   - `src/obsidian_ops/history_jj.py`
2. Tooling installed and working:
   - Python 3.13
   - `uv`
   - `jj`
3. You are using project tooling through `devenv shell -- ...`.

## 4. High-Level Implementation Plan

Implement in this order:

1. Scaffold repo and dependency baseline.
2. Add configuration and models.
3. Migrate foundational filesystem + lock + context modules.
4. Add VCS wrapper and tools.
5. Add agent loop with minimal protocol.
6. Add FastAPI app endpoints and timeout behavior.
7. Add entrypoint and complete test suite.
8. Run end-to-end manual validation.

Why this order:
- It builds from low-risk pure modules to high-coupling runtime wiring.
- Each later step depends on verified earlier blocks.
- Failures are easier to isolate.

## 5. Step 1: Create the Repository Skeleton

Implementation tasks:

1. Create the repository layout:

```text
obsidian-agent/
├── src/obsidian_agent/
│   ├── __init__.py
│   └── __main__.py
├── tests/
├── pyproject.toml
├── README.md
└── devenv.nix
```

2. Add empty placeholders for planned modules:
   - `app.py`, `config.py`, `models.py`, `agent.py`, `tools.py`, `vcs.py`, `fs_atomic.py`, `locks.py`, `page_context.py`.

Verification gate (must pass before Step 2):

1. Confirm tree shape is correct:

```bash
rg --files
```

2. Confirm package is importable (after dependencies are added in Step 2, rerun import check there).

## 6. Step 2: Define Project Metadata and Dependencies

Implementation tasks:

1. Create `pyproject.toml` with required runtime dependencies:
   - `pydantic>=2.12.5`
   - `pydantic-settings>=2.0.0`
   - `fastapi>=0.115.0`
   - `uvicorn>=0.34.0`
   - `openai>=1.60.0`
   - `httpx>=0.28.0`

2. Add dev dependencies:
   - `pytest>=7.0`
   - `pytest-asyncio>=0.24.0`
   - `pytest-cov>=4.1`
   - `ruff>=0.5.0`
   - `ty>=0.0.1` (if used in your standard stack)

3. Add pytest config (`testpaths`, minimal addopts).
4. Add Ruff config (line length, target version, lint set).
5. Add module execution script if desired:
   - Optional: `obsidian-agent = "obsidian_agent.__main__:main"`

Verification gate:

1. Sync dependencies:

```bash
devenv shell -- uv sync --extra dev
```

2. Confirm import path works:

```bash
devenv shell -- python -c "import obsidian_agent; print('ok')"
```

3. Confirm lint/type/test tools can execute:

```bash
devenv shell -- ruff check src tests
devenv shell -- pytest -q
```

Expected: early tests may be empty, but command execution must succeed.

## 7. Step 3: Add Runtime Settings (`config.py`)

Implementation tasks:

1. Implement `AgentSettings` in `src/obsidian_agent/config.py` using `BaseSettings`.
2. Use `env_prefix="AGENT_"` and `extra="ignore"`.
3. Include fields:
   - `vault_dir: Path`
   - `vllm_base_url: str = "http://127.0.0.1:8000/v1"`
   - `vllm_model: str = "local-model"`
   - `vllm_api_key: str = ""`
   - `jj_bin: str = "jj"`
   - `host: str = "127.0.0.1"`
   - `port: int = 8081`
   - `max_tool_iterations: int = 12`
   - `max_search_results: int = 12`
   - `page_url_prefix: str = "/"`
   - `operation_timeout_s: int = 120`
4. Add validator ensuring `vault_dir` exists and is a directory.
5. Add cached loader `get_agent_settings()` via `@lru_cache(maxsize=1)`.

Testing/verification tasks:

1. Create `tests/test_config.py` covering:
   - Loads valid env values.
   - Defaults apply when optional env vars are absent.
   - Invalid/missing `vault_dir` raises validation error.

2. Run:

```bash
devenv shell -- pytest tests/test_config.py -q
```

Pass criteria:
- All config tests pass.
- Settings object values match expected defaults and overrides.

## 8. Step 4: Add API Models (`models.py`)

Implementation tasks:

1. Implement request model:
   - `ApplyRequest` with `instruction`, `current_url_path`, optional `current_file_path`.
2. Implement shared response model:
   - `OperationResult` with `ok`, `updated`, `summary`, `changed_files`, `warning`, `error`.
3. Set `changed_files` default to empty list.
4. Do not include any queue/SSE/job status models.

Testing/verification tasks:

1. Create `tests/test_models.py` to validate:
   - Minimal valid payload parsing.
   - `changed_files` default behavior.
   - Optional `warning`/`error` serialization.

2. Run:

```bash
devenv shell -- pytest tests/test_models.py -q
```

Pass criteria:
- Serialization output shape matches API contract.

## 9. Step 5: Migrate Foundation Modules Unchanged

Implementation tasks:

1. Copy modules from monolith with **no logic changes**:
   - `fs_atomic.py`
   - `locks.py`
   - `page_context.py`
2. Only update import paths/package names if necessary.
3. Preserve constants and behavior exactly (`MAX_FILE_SIZE_BYTES`, protected dirs, etc.).

Testing/verification tasks:

1. Copy/adapt tests:
   - `test_fs_atomic.py`
   - `test_locks.py`
   - `test_page_context.py`
2. Update imports from `obsidian_ops.*` to `obsidian_agent.*`.
3. Run:

```bash
devenv shell -- pytest tests/test_fs_atomic.py tests/test_locks.py tests/test_page_context.py -q
```

Pass criteria:
- All carried-over tests pass without behavior drift.

## 10. Step 6: Add VCS Module (`vcs.py`)

Implementation tasks:

1. Copy `history_jj.py` into `vcs.py`.
2. Keep class name `JujutsuHistory`.
3. Preserve methods:
   - `ensure_workspace()`
   - `commit(message)`
   - `undo()`
   - `log_for_file(path, limit)`
   - `diff_for_file(path)`
4. Keep subprocess timeout and error handling behavior.
5. Do not add `VCSAdapter` protocol for this MVP.

Testing/verification tasks:

1. Create/adapt `tests/test_vcs.py` from prior history tests.
2. Mock subprocess calls to test success/failure paths deterministically.
3. Run:

```bash
devenv shell -- pytest tests/test_vcs.py -q
```

Pass criteria:
- Commit/undo/log behavior and error mapping are covered and passing.

## 11. Step 7: Add Tool Runtime (`tools.py`)

Implementation tasks:

1. Copy `tools.py` from monolith.
2. Update imports to `obsidian_agent.*` modules.
3. Keep tool list for MVP:
   - `read_file`
   - `write_file`
   - `list_files`
   - `search_files`
   - `fetch_url`
   - `undo_last_change`
   - `get_file_history`
4. Keep `changed_files` tracking behavior.

Testing/verification tasks:

1. Create/adapt `tests/test_tools.py` with temp vault fixtures.
2. Cover:
   - Read/write happy path.
   - Path safety rejection.
   - Search limits.
   - `fetch_url` size/error behavior (mock `httpx`).
   - Undo/history delegation to VCS mock.
3. Run:

```bash
devenv shell -- pytest tests/test_tools.py -q
```

Pass criteria:
- Tool execution works and unsafe operations are rejected.

## 12. Step 8: Add Agent Runner (`agent.py`)

Implementation tasks:

1. Copy existing `agent.py` and rewire imports.
2. Add `AgentRunner` protocol with `run(instruction, file_path, on_progress)`.
3. Change progress callback signature from structured SSE events to plain string messages.
4. Remove all references to `SSEEvent`.
5. Keep bounded tool loop behavior (`max_tool_iterations`).

Testing/verification tasks:

1. Create/adapt `tests/test_agent.py` using mocked `openai.AsyncOpenAI` responses.
2. Verify:
   - Tool call dispatch.
   - Iteration cap behavior.
   - Final summary/result shape includes `changed_files`.
   - Progress callback is invoked with strings.
3. Run:

```bash
devenv shell -- pytest tests/test_agent.py -q
```

Pass criteria:
- Agent loop passes deterministic mocked scenarios.

## 13. Step 9: Build FastAPI App (`app.py`)

Implementation tasks:

1. Implement lifespan initialization:
   - Load settings.
   - Initialize `JujutsuHistory` and call `ensure_workspace()`.
   - Create `FileLockManager`, `ToolRuntime`, `Agent`.
   - Store on `app.state`.
2. Add endpoint `GET /api/health` returning `{ "status": "ok" }`.
3. Add endpoint `POST /api/apply`:
   - Validate payload with `ApplyRequest`.
   - Resolve file path via `resolve_page_path()` unless `current_file_path` provided.
   - Reset runtime changed-file tracking at start of request.
   - Execute `agent.run(...)` inline under `asyncio.wait_for(..., timeout=operation_timeout_s)`.
   - If `changed_files` non-empty, perform `jj.commit(...)`.
   - Return `OperationResult`.
4. Add endpoint `POST /api/undo`:
   - Execute `jj.undo()` under timeout.
   - Return `OperationResult(ok=True, updated=True, summary="Last change undone.")`.
5. Error handling rules:
   - Timeout -> `ok=false`, `error="Operation timed out after <N>s"`.
   - Any fatal exception -> `ok=false`, descriptive `error`.

Testing/verification tasks:

1. Create `tests/test_app.py` to cover:
   - `/api/health` success.
   - `/api/apply` success with file changes (`updated=true`, commit called).
   - `/api/apply` no-op (`updated=false`, commit not called).
   - `/api/apply` agent failure (`ok=false`).
   - `/api/apply` timeout (`ok=false`, timeout message).
   - `/api/undo` success.
2. Mock agent and VCS for deterministic behavior.
3. Run:

```bash
devenv shell -- pytest tests/test_app.py -q
```

Pass criteria:
- All endpoint contracts and edge cases pass.

## 14. Step 10: Add Executable Entrypoint (`__main__.py`)

Implementation tasks:

1. Create `__main__.py` that:
   - Loads `AgentSettings`.
   - Starts Uvicorn for `obsidian_agent.app:app` with configured host/port.
2. Ensure module execution works:
   - `python -m obsidian_agent`

Testing/verification tasks:

1. Add a light test for entrypoint config wiring (mock uvicorn run call), or verify manually.
2. Manual process verification:

```bash
AGENT_VAULT_DIR=/tmp/test-vault devenv shell -- python -m obsidian_agent
```

3. In another terminal:

```bash
curl -sS http://127.0.0.1:8081/api/health
```

Pass criteria:
- Health endpoint returns `{"status":"ok"}` while process is running.

## 15. Step 11: End-to-End Local Verification

Implementation tasks:

1. Create a disposable local test vault with markdown files and initialize `jj` workspace.
2. Start agent service pointing at that vault.
3. Run apply request with a simple instruction likely to edit one file.
4. Confirm response shape and `updated` behavior.
5. Confirm vault file content changed on disk when `updated=true`.
6. Confirm Jujutsu commit exists after changed apply.
7. Run undo request and verify file rollback.

Suggested manual commands:

```bash
mkdir -p /tmp/oa-vault
printf "# Note\n" > /tmp/oa-vault/index.md
cd /tmp/oa-vault && jj git init

AGENT_VAULT_DIR=/tmp/oa-vault \
AGENT_VLLM_BASE_URL=http://127.0.0.1:8000/v1 \
AGENT_VLLM_MODEL=local-model \
devenv shell -- python -m obsidian_agent
```

```bash
curl -sS -X POST http://127.0.0.1:8081/api/apply \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"Add a one-line summary to this note","current_url_path":"/"}'
```

```bash
curl -sS -X POST http://127.0.0.1:8081/api/undo
```

Pass criteria:
- Apply returns valid `OperationResult`.
- Undo returns `ok=true`, `updated=true`.
- `jj log` reflects commit then undo behavior.

## 16. Step 12: Final QA Checklist and Handoff Notes

Before opening PR, verify all checklist items:

1. No SSE code exists (`/stream`, `SSEEvent`, broadcaster, queue worker).
2. No Kiln/static-serving code exists in agent (`inject`, `rebuild`, static mounts).
3. API contract exactly matches simplified concept.
4. `AGENT_` prefixed config only (no `OPS_` fields inside agent settings).
5. Tests pass locally:

```bash
devenv shell -- pytest tests/ -q
```

6. Lint passes:

```bash
devenv shell -- ruff check src tests
```

7. Final handoff notes include:
   - Any deferred items.
   - Known limitations.
   - Exact commands used for validation.

## 17. Appendix A: Endpoint Contract Reference

### `POST /api/apply`

Request:

```json
{
  "instruction": "Add a summary section to this note",
  "current_url_path": "/notes/example"
}
```

Success response with changes:

```json
{
  "ok": true,
  "updated": true,
  "summary": "Added a summary section.",
  "changed_files": ["notes/example.md"],
  "warning": null,
  "error": null
}
```

Success response without changes:

```json
{
  "ok": true,
  "updated": false,
  "summary": "No edits were necessary.",
  "changed_files": [],
  "warning": null,
  "error": null
}
```

Failure response:

```json
{
  "ok": false,
  "updated": false,
  "summary": "",
  "changed_files": [],
  "warning": null,
  "error": "Operation timed out after 120s"
}
```

### `POST /api/undo`

Response:

```json
{
  "ok": true,
  "updated": true,
  "summary": "Last change undone.",
  "changed_files": [],
  "warning": null,
  "error": null
}
```

### `GET /api/health`

Response:

```json
{
  "status": "ok"
}
```

## 18. Appendix B: Test Command Matrix

Run these in order; do not continue if one fails:

1. Config + models:

```bash
devenv shell -- pytest tests/test_config.py tests/test_models.py -q
```

2. Foundation modules:

```bash
devenv shell -- pytest tests/test_fs_atomic.py tests/test_locks.py tests/test_page_context.py -q
```

3. VCS + tools:

```bash
devenv shell -- pytest tests/test_vcs.py tests/test_tools.py -q
```

4. Agent loop + app endpoints:

```bash
devenv shell -- pytest tests/test_agent.py tests/test_app.py -q
```

5. Full suite:

```bash
devenv shell -- pytest tests/ -q
```

6. Lint:

```bash
devenv shell -- ruff check src tests
```

## 19. Appendix C: Common Failure Modes and Fixes

1. `Vault directory does not exist` at startup.
- Cause: missing or incorrect `AGENT_VAULT_DIR`.
- Fix: point to a real directory and ensure it is mounted/accessible.

2. `jj` commands fail in apply/undo.
- Cause: vault not initialized as a JJ workspace.
- Fix: run `jj git init` in the vault before testing.

3. `/api/apply` always returns `updated=false`.
- Cause: `changed_files` tracking not reset/populated correctly.
- Fix: verify `ToolRuntime.write_file` adds relative paths and app handler reads runtime state correctly.

4. Timeout errors for normal instructions.
- Cause: low `operation_timeout_s` or stalled model/tool call.
- Fix: inspect logs, increase timeout cautiously, add per-call timeout diagnostics.

5. Tests pass individually but fail together.
- Cause: settings cache (`lru_cache`) leakage between tests.
- Fix: clear settings cache in fixtures (`get_agent_settings.cache_clear()`).

6. Endpoint response shape drift.
- Cause: ad hoc response dicts in handlers.
- Fix: always return `OperationResult` model instances from handlers.

7. Import errors after file copy.
- Cause: old `obsidian_ops.*` imports remain.
- Fix: run `rg -n "obsidian_ops" src tests` and replace with `obsidian_agent` imports.
