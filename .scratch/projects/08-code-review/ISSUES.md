# Code Review — Issues

Findings ordered by severity: **Critical > High > Medium > Low > Informational**.

---

## Critical

### C1. SSRF via `fetch_url` tool — no URL validation

**File**: `src/obsidian_ops/tools.py:78-89`

The `fetch_url` tool accepts any URL from the LLM agent and makes an HTTP GET request with no restrictions. An attacker who can influence the LLM's tool calls (via prompt injection in vault content) could:

- Fetch internal services: `http://169.254.169.254/latest/meta-data/` (cloud metadata)
- Port-scan the local network: `http://192.168.1.x:port/`
- Exfiltrate vault data by encoding it in a URL to an attacker-controlled server

**Recommendation**: Implement URL allowlisting or at minimum block private/link-local IP ranges. Consider whether this tool is even needed given the local-first design.

---

### C2. Unbounded memory growth — jobs and locks never evicted

**File**: `src/obsidian_ops/queue.py:35-37`, `src/obsidian_ops/locks.py:15-22`

`JobQueue._jobs` is a plain dict that grows forever. Every job created is retained in memory indefinitely. Similarly, `FileLockManager._locks` creates a new `asyncio.Lock` for every unique file path and never removes them.

For a long-running server, this is a memory leak. After thousands of operations, the process will consume significant memory.

**Recommendation**: Add TTL-based eviction or a max-size LRU for completed jobs. For locks, use `weakref` or prune entries when unlocked and idle.

---

## High

### H1. `on_progress` closure captures stale variables in worker loop

**File**: `src/obsidian_ops/queue.py:90-92`

Ruff flags B023 here. The `on_progress` inner function captures `job` and `job_id` from the enclosing `while True` loop without binding them as default arguments. If the loop iteration changes these variables before `on_progress` is called, the closure will reference the wrong job.

In practice this is currently safe because `await agent.run(...)` blocks until completion before the next iteration, but it's fragile — any future change to run jobs concurrently would break.

**Recommendation**: Bind the variables explicitly: `async def on_progress(event, _job=job, _id=job_id)` or extract the loop body into a separate function.

---

### H2. `write_file` tool allows writing any file type, not just markdown

**File**: `src/obsidian_ops/tools.py:30-38`

The tool description says "Write markdown content to a file" but there's no enforcement of file extension. The LLM could write `.py`, `.sh`, `.html`, or any other file type into the vault. Combined with the fact that the vault is also a jj workspace (which may have hooks), this could lead to code execution.

**Recommendation**: Restrict writes to known safe extensions (`.md`, `.txt`, `.canvas`, `.json`) or at least warn/log when non-markdown files are written.

---

### H3. No rate limiting on job creation

**File**: `src/obsidian_ops/app.py:86-98`

The `/api/jobs` and `/api/undo` endpoints have no rate limiting. An attacker or misbehaving client could flood the queue with thousands of jobs, each triggering LLM calls, jj commits, and Kiln rebuilds.

**Recommendation**: Add a per-client rate limit or a global concurrency cap on pending jobs.

---

### H4. `lru_cache` on `get_settings()` prevents runtime reconfiguration and complicates testing

**File**: `src/obsidian_ops/config.py:46-48`

`get_settings()` is cached with `lru_cache(maxsize=1)`, which means environment variable changes after first call are ignored. Tests must call `get_settings.cache_clear()` manually (see `test_api.py:36`), and the test does `importlib.reload(app_module)` to work around `app = create_app()` running at module import time.

**Recommendation**: Consider dependency injection rather than module-level singleton pattern. At minimum, document the cache-clearing requirement for tests.

---

### H5. Module-level `create_app()` call forces side effects on import

**File**: `src/obsidian_ops/app.py:152`

`app = create_app()` runs at import time. This calls `get_settings()`, which reads env vars and validates `vault_dir` exists. This means importing the module for any reason (type checking, testing, linting) requires valid env vars to be set.

The test fixture works around this with `importlib.reload()`, which is fragile.

**Recommendation**: Use a factory pattern where `app` is only created when the server starts (e.g., via `uvicorn --factory`).

---

## Medium

### M1. `subprocess.run` calls are blocking (wrapped in `asyncio.to_thread`)

**Files**: `src/obsidian_ops/history_jj.py:14-26`, `src/obsidian_ops/rebuild.py:16-31`

Both `JujutsuHistory._run_jj()` and `KilnRebuilder.rebuild()` use `asyncio.to_thread(subprocess.run(...))`. This works but ties up a thread from the default executor for the duration of the subprocess. Since jj and kiln operations can take seconds to minutes (kiln timeout is 180s), this could exhaust the thread pool under load.

**Recommendation**: Use `asyncio.create_subprocess_exec` for true async subprocess handling. This would also allow streaming stdout/stderr to the progress log.

---

### M2. Race condition in `inject_overlay` during concurrent rebuilds

**File**: `src/obsidian_ops/inject.py:13-29`

`inject_overlay` reads, modifies, and writes HTML files non-atomically. If called concurrently (e.g., two rebuild+inject cycles overlapping), the same file could be read, injected, and written by both, resulting in double injection.

The MARKER check prevents functional breakage (the second call would find the marker and skip), but there's a TOCTOU window where both reads happen before either write completes.

**Recommendation**: Use the same `write_file_atomic` pattern from `fs_atomic.py`, or add a lock.

---

### M3. `search_files` is O(n*m) brute force — no indexing

**File**: `src/obsidian_ops/tools.py:49-76`

For every search, the code globs all matching files and scans every line of every file. For a large vault (thousands of files), this could be very slow and block the event loop thread.

**Recommendation**: For the MVP this is fine, but consider adding a search index or at least caching file listings.

---

### M4. SSE stream doesn't handle client disconnect gracefully

**File**: `src/obsidian_ops/app.py:100-128`

The `event_generator()` async generator blocks on `await subscriber.get()` indefinitely. If the client disconnects, the generator hangs until the job completes and sends `None`. There's no timeout or cancellation check.

**Recommendation**: Add a timeout to `subscriber.get()` or check for client disconnection.

---

### M5. `call_tool` swallows all exceptions

**File**: `src/obsidian_ops/tools.py:99-121`

The outer `try/except Exception` in `call_tool` catches every error and returns it as a string. This means the LLM sees the error message and may retry, but the system has no way to distinguish transient failures from permanent ones. Security-relevant errors (path traversal, protected dir access) are silently converted to tool output strings that the LLM might try to work around.

**Recommendation**: Let security-related `ValueError` exceptions propagate so the agent loop can abort rather than letting the LLM try creative workarounds.

---

### M6. No CORS configuration

**File**: `src/obsidian_ops/app.py`

The FastAPI app has no CORS middleware configured. While this is a local-first app, any page opened in the same browser could POST to `http://127.0.0.1:8080/api/jobs` and trigger operations on the user's vault.

**Recommendation**: Add explicit CORS with a restrictive origin policy (e.g., only the served site's origin).

---

### M7. `Job` model duplicates `id` generation logic with `JobQueue.create_job`

**Files**: `src/obsidian_ops/models.py:18`, `src/obsidian_ops/queue.py:42`

`Job` has a `default_factory=lambda: uuid4().hex` for `id`, but `create_job` overrides it with `uuid4().hex[:8]` (truncated). The model default is never used. The 8-char hex ID has ~4 billion possibilities, which is sufficient for local use but worth noting the inconsistency.

**Recommendation**: Remove the `default_factory` from the model since all creation goes through `JobQueue`, or make both consistent.

---

## Low

### L1. Ruff lint violations (5 errors)

**Files**: Various

Current `ruff check` output:
- `UP042` in `models.py:10`: `JobStatus(str, Enum)` should be `StrEnum`
- `B023` in `queue.py:91-92`: Closure captures loop variables (see H1)
- `E501` in `queue.py:115`: Line too long (122 > 120)
- `F401` in `tests/test_queue.py:3`: Unused `asyncio` import

**Recommendation**: Fix all — they're trivial. The `StrEnum` change requires Python 3.11+ (already targeting 3.13).

---

### L2. No `__all__` exports in any module

**Files**: All `src/obsidian_ops/*.py`

No module defines `__all__`. For a library/package this makes the public API ambiguous.

**Recommendation**: Add `__all__` to at least `__init__.py` and major modules.

---

### L3. `_summarize_args` in agent.py doesn't escape special characters

**File**: `src/obsidian_ops/agent.py:33-42`

The function truncates and formats tool arguments for progress messages. If arguments contain SSE-breaking characters (newlines), the progress stream could be corrupted.

**Recommendation**: Sanitize or escape newlines in the rendered summary.

---

### L4. `devenv.nix` has hardcoded `vendorHash` for kiln override

**File**: `devenv.nix:12-15`

The kiln package override hardcodes a `vendorHash` and disables checks. This will break silently when the kiln version changes.

**Recommendation**: Document this and add a comment noting the hash must be updated with kiln version bumps.

---

### L5. `.tmuxp.yaml` references a different Notes path

**File**: `.tmuxp.yaml:9`

The tmuxp config `cd`s to `~/Documents/Notes/Projects/obsidian-ops` but the repo lives at `~/Documents/Projects/obsidian-ops`. This is tracked in git (`.gitignore` has it commented out).

**Recommendation**: Either fix the path or remove from git tracking.

---

### L6. Demo CLI hardcodes `.scratch/projects/06-demo-scaffold/generated` as work directory

**File**: `src/obsidian_ops/demo_cli.py:32`

The demo puts its runtime vault inside the `.scratch` project tracking directory. This mixes generated artifacts with project documentation.

**Recommendation**: Use a more conventional location like `.demo/` or `tmp/`.

---

## Informational

### I1. Test coverage is 53% overall

Key uncovered areas:
- `agent.py`: 26% — the entire LLM interaction loop is untested
- `tools.py`: 27% — no tool tests (read/write/search/fetch/undo/history)
- `queue.py`: 43% — `run_worker` is untested
- `demo_cli.py`: 0% — no tests at all
- `rebuild.py`: 65% — only the constructor is tested (via app startup)

The tested modules (config, fs_atomic, inject, locks, page_context, models) have excellent coverage (89-100%).

### I2. No CI/CD pipeline configured

There's no `.github/workflows/`, `.gitlab-ci.yml`, or similar. Tests and linting rely on manual execution via `devenv shell`.

### I3. No type checking in CI

`ty` is listed as a dev dependency but there's no evidence of it being run. `pyproject.toml` configures `[tool.ty]` but no type-checking command is documented.

### I4. Good architectural decisions

Several design choices are well-considered:
- Atomic file writes with `fsync` + `os.replace` — correct POSIX atomicity
- Path traversal protection with both `..` checks and `is_relative_to` verification
- Protected directory list (`.jj`, `.obsidian`, `.git`, `__pycache__`)
- Jujutsu for vault versioning — gives undo/history without polluting the vault with `.git`
- SSE for streaming progress — appropriate for the use case
- Clean URL middleware — nice UX for generated sites

### I5. Code style is consistent and clean

Modules are well-structured, small, and focused. Naming conventions are consistent. The step-by-step commit history shows disciplined incremental development.
