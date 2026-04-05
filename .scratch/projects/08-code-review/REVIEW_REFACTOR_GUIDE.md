# Review Refactor Guide — Step-by-Step Implementation

This guide walks through every fix and improvement from the code review (ISSUES.md).
Steps are ordered so earlier changes don't conflict with later ones.
Each step states exactly what to change, where, and how to verify.

**Ground rules**:
- Make one commit per step (or per logical sub-step where noted).
- Run `devenv shell -- python -m pytest tests/ -q` after every step. All 44 existing tests must still pass.
- Run `devenv shell -- python -m ruff check src/ tests/` after every step. No new violations.
- Read the referenced file and surrounding context before editing.

---

## Phase 1 — Lint and Hygiene (Steps 1-4)

These are mechanical fixes. Start here to build confidence and get a clean baseline.

### Step 1: Fix ruff lint violations (L1)

**Issue**: 5 ruff errors across the codebase.

#### 1a. `StrEnum` migration

**File**: `src/obsidian_ops/models.py`

Change:
```python
from enum import Enum
# ...
class JobStatus(str, Enum):
```
To:
```python
from enum import StrEnum
# ...
class JobStatus(StrEnum):
```

Remove the `Enum` import if it's no longer used. Keep `StrEnum`.

#### 1b. Line too long in queue.py

**File**: `src/obsidian_ops/queue.py:114-116`

The string on line 115 is 122 chars. Break it:
```python
                    except Exception as exc:  # noqa: BLE001
                        msg = (
                            "Files were changed but history recording failed. "
                            "You may need to inspect the vault manually."
                        )
                        raise RuntimeError(msg) from exc
```

#### 1c. Remove unused import in test_queue.py

**File**: `tests/test_queue.py:3`

Delete the line `import asyncio` — it's unused.

#### 1d. Fix B023 closure capture (also addresses H1)

**File**: `src/obsidian_ops/queue.py:73-146`

Extract the body of the `while True` loop into a standalone async function. This binds `job` and `job_id` as parameters instead of closures:

```python
async def _process_job(
    job_id: str,
    job: Job,
    queue: JobQueue,
    agent: Agent,
    jj: JujutsuHistory,
    rebuilder: KilnRebuilder,
    injector: Callable,
    settings: Settings,
) -> None:
    job.status = JobStatus.RUNNING
    await queue.broadcaster.publish(job_id, SSEEvent(type="status", message="Job started"))

    async def on_progress(event: SSEEvent) -> None:
        job.messages.append(event.message)
        await queue.broadcaster.publish(job_id, event)

    try:
        # ... (move the existing try body here unchanged)
    except Exception as exc:  # noqa: BLE001
        # ... (existing except body)
    finally:
        await queue.broadcaster.close(job_id)


async def run_worker(
    queue: JobQueue,
    agent: Agent,
    jj: JujutsuHistory,
    rebuilder: KilnRebuilder,
    injector: Callable,
    settings: Settings,
) -> None:
    while True:
        job_id = await queue.next_job_id()
        job = queue.get_job(job_id)
        if job is None:
            continue
        await _process_job(job_id, job, queue, agent, jj, rebuilder, injector, settings)
```

**Verify**: `ruff check src/ tests/` should now report 0 errors.

---

### Step 2: Fix `.tmuxp.yaml` path (L5)

**File**: `.tmuxp.yaml:9`

Change:
```yaml
- cd ~/Documents/Notes/Projects/obsidian-ops
```
To:
```yaml
- cd ~/Documents/Projects/obsidian-ops
```

**Verify**: This is a config-only change. No tests needed.

---

### Step 3: Add `vendorHash` comment in devenv.nix (L4)

**File**: `devenv.nix:12-15`

Add a comment above the override:
```nix
    # NOTE: vendorHash must be updated when changing the kiln version in devenv.yaml.
    # To get the new hash: build, copy the expected hash from the error, paste here.
    (inputs.kiln.packages.${pkgs.system}.default.overrideAttrs (_: {
      vendorHash = "sha256-HL4H+HOVHu7H71V7t4bjWBcquaimuh/GkPnuwPiuZ0A=";
      doCheck = false;
    }))
```

**Verify**: `devenv shell` still enters cleanly.

---

### Step 4: Consolidate Job ID generation (M7)

**File**: `src/obsidian_ops/models.py:18`

Change the `id` field from:
```python
id: str = Field(default_factory=lambda: uuid4().hex)
```
To a required field with no default:
```python
id: str
```

This makes it explicit that callers must provide an ID. `JobQueue.create_job` and `create_undo_job` already do.

**Verify**: Run tests. `test_queue.py` tests create jobs via `JobQueue` so they already pass IDs.

---

## Phase 2 — Security Hardening (Steps 5-9)

These address the critical and high-severity security findings.

### Step 5: Add URL validation to `fetch_url` (C1)

**File**: `src/obsidian_ops/tools.py`

Add a validation function above the `ToolRuntime` class:

```python
import ipaddress
from urllib.parse import urlparse

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_url(url: str) -> str:
    """Validate a URL is safe to fetch. Returns the URL or raises ValueError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    # Resolve hostname to IP and check against blocked ranges
    import socket
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname {parsed.hostname!r}: {exc}") from exc

    for family, _type, _proto, _canonname, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(f"URL resolves to blocked address range: {ip}")

    return url
```

Then in `fetch_url`, add validation at the top:
```python
async def fetch_url(self, url: str) -> str:
    url = _validate_url(url)  # <-- add this line
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ... rest unchanged
```

**Important**: The `_validate_url` raises `ValueError`. Step 8 below changes `call_tool` to let `ValueError` propagate, so this will abort the agent loop on blocked URLs rather than letting the LLM retry.

**New test file**: `tests/test_url_validation.py`

```python
import pytest
from obsidian_ops.tools import _validate_url


def test_allows_public_https():
    assert _validate_url("https://example.com/page") == "https://example.com/page"


def test_blocks_private_ip():
    with pytest.raises(ValueError, match="blocked address"):
        _validate_url("http://192.168.1.1/")


def test_blocks_link_local():
    with pytest.raises(ValueError, match="blocked address"):
        _validate_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_localhost():
    with pytest.raises(ValueError, match="blocked address"):
        _validate_url("http://127.0.0.1:8000/v1")


def test_blocks_non_http_scheme():
    with pytest.raises(ValueError, match="Only http/https"):
        _validate_url("file:///etc/passwd")


def test_blocks_empty_hostname():
    with pytest.raises(ValueError, match="no hostname"):
        _validate_url("http:///path")
```

**Verify**: All tests pass including the new ones.

---

### Step 6: Restrict writable file extensions (H2)

**File**: `src/obsidian_ops/tools.py`

Add a constant and validation to `write_file`:

```python
ALLOWED_WRITE_EXTENSIONS = {".md", ".txt", ".canvas", ".json", ".csv"}
```

In the `write_file` method, after `validate_vault_path` and before acquiring the lock:
```python
async def write_file(self, path: str, content: str) -> str:
    abs_path = validate_vault_path(self._settings.vault_dir, Path(path))
    if abs_path.suffix.lower() not in ALLOWED_WRITE_EXTENSIONS:
        raise ValueError(
            f"Writing {abs_path.suffix!r} files is not allowed. "
            f"Permitted extensions: {', '.join(sorted(ALLOWED_WRITE_EXTENSIONS))}"
        )
    lock = self._locks.get_lock(str(abs_path))
    # ... rest unchanged
```

**New tests** (add to `tests/test_fs_atomic.py` or a new `tests/test_tools.py`):

```python
def test_write_file_rejects_python_extension():
    # Test via ToolRuntime or by calling the validation directly
    ...

def test_write_file_allows_markdown():
    ...
```

You'll need a minimal `ToolRuntime` fixture for these. Create `tests/test_tools.py` with a fixture that constructs a `ToolRuntime` with a real temp vault dir, a mock `FileLockManager`, and a mock `JujutsuHistory`.

**Verify**: Tests pass. Try `write_file("evil.sh", "#!/bin/bash\nrm -rf /")` in a test — should raise `ValueError`.

---

### Step 7: Add pending-job cap for rate limiting (H3)

**File**: `src/obsidian_ops/queue.py`

Add a constant and check in `JobQueue`:

```python
MAX_PENDING_JOBS = 50
```

In `create_job` and `create_undo_job`, add a check before creating:
```python
def create_job(self, instruction: str, file_path: str | None) -> Job:
    pending_count = sum(1 for j in self._jobs.values() if j.status == JobStatus.QUEUED)
    if pending_count >= MAX_PENDING_JOBS:
        raise ValueError("Too many pending jobs. Please wait for current jobs to complete.")
    # ... rest unchanged
```

**File**: `src/obsidian_ops/app.py`

In the `create_job` and `undo` endpoints, catch `ValueError` from the queue and return 429:

```python
@app.post("/api/jobs", response_model=JobResponse)
async def create_job(request: JobRequest) -> JobResponse:
    queue: JobQueue = app.state.queue
    app_settings = app.state.settings
    file_path = request.current_file_path
    if file_path is None:
        file_path = resolve_page_path(
            app_settings.vault_dir,
            request.current_url_path,
            app_settings.page_url_prefix,
        )
    try:
        job = queue.create_job(request.instruction, file_path)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return JobResponse(job_id=job.id)
```

Same pattern for the `/api/undo` endpoint.

**New tests**:
```python
def test_create_job_rejects_when_queue_full():
    queue = JobQueue()
    for i in range(50):
        queue.create_job(f"job {i}", None)
    with pytest.raises(ValueError, match="Too many pending"):
        queue.create_job("one too many", None)
```

**Verify**: All tests pass.

---

### Step 8: Let security exceptions propagate from `call_tool` (M5)

**File**: `src/obsidian_ops/tools.py:99-121`

Change the exception handling in `call_tool` to re-raise `ValueError` (which is what `validate_vault_path`, `_validate_url`, and the extension check all raise):

```python
async def call_tool(self, name: str, arguments: dict) -> str:
    try:
        # ... (all the if/elif branches unchanged)
        return f"Unknown tool: {name}"
    except ValueError:
        raise  # Security-related errors must propagate
    except Exception as exc:  # noqa: BLE001
        return f"Tool '{name}' failed: {exc}"
```

**File**: `src/obsidian_ops/agent.py`

In `Agent.run`, the tool call loop needs to handle `ValueError` from `call_tool` by aborting:

```python
for tool_call in assistant_message.tool_calls:
    tool_name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = {}
    await on_progress(
        SSEEvent(
            type="tool",
            message=f"Calling {tool_name}({_summarize_args(arguments)})",
        )
    )
    try:
        result = await self._tools.call_tool(tool_name, arguments)
    except ValueError as exc:
        raise RuntimeError(f"Tool '{tool_name}' blocked: {exc}") from exc
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        }
    )
```

**Verify**: Existing tests pass. The `RuntimeError` will be caught by `run_worker`'s outer `except Exception`, setting job status to FAILED.

---

### Step 9: Add CORS middleware (M6)

**File**: `src/obsidian_ops/app.py`

Add the import:
```python
from fastapi.middleware.cors import CORSMiddleware
```

In `create_app()`, after creating the `FastAPI` instance, add:
```python
def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{settings.host}:{settings.port}"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    # ... rest of create_app unchanged
```

**New test** (add to `tests/test_api.py`):
```python
def test_cors_rejects_foreign_origin(test_client: TestClient) -> None:
    response = test_client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "Access-Control-Allow-Origin" not in response.headers or \
        response.headers["Access-Control-Allow-Origin"] != "http://evil.example.com"
```

**Verify**: Tests pass.

---

## Phase 3 — Memory and Reliability (Steps 10-14)

### Step 10: Add job eviction to JobQueue (C2, jobs)

**File**: `src/obsidian_ops/queue.py`

Add eviction logic. When a new job is created, prune completed/failed jobs older than a threshold:

```python
from datetime import timedelta

MAX_COMPLETED_JOBS = 200
EVICTION_AGE = timedelta(hours=1)
```

Add a private method to `JobQueue`:
```python
def _evict_old_jobs(self) -> None:
    if len(self._jobs) <= MAX_COMPLETED_JOBS:
        return
    now = datetime.now(UTC)
    to_remove = [
        jid
        for jid, j in self._jobs.items()
        if j.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)
        and j.finished_at is not None
        and (now - j.finished_at) > EVICTION_AGE
    ]
    for jid in to_remove:
        del self._jobs[jid]
```

Call `self._evict_old_jobs()` at the start of `create_job` and `create_undo_job`.

**New test**:
```python
def test_eviction_removes_old_completed_jobs():
    queue = JobQueue()
    # Create and complete many jobs with backdated finished_at
    from datetime import timedelta, UTC, datetime
    for i in range(210):
        job = queue.create_job(f"job {i}", None)
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC) - timedelta(hours=2)
    # Creating one more should trigger eviction
    new_job = queue.create_job("new", None)
    assert len(queue._jobs) <= MAX_COMPLETED_JOBS + 1  # +1 for the new pending job
```

**Verify**: Tests pass.

---

### Step 11: Add lock eviction to FileLockManager (C2, locks)

**File**: `src/obsidian_ops/locks.py`

Add pruning for unlocked locks when the dict exceeds a threshold:

```python
MAX_CACHED_LOCKS = 500


class FileLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, path: str) -> asyncio.Lock:
        resolved = str(Path(path).resolve())
        if resolved not in self._locks:
            self._prune_if_needed()
            self._locks[resolved] = asyncio.Lock()
        return self._locks[resolved]

    def _prune_if_needed(self) -> None:
        if len(self._locks) <= MAX_CACHED_LOCKS:
            return
        # Remove locks that are not currently held
        to_remove = [
            key for key, lock in self._locks.items()
            if not lock.locked()
        ]
        for key in to_remove:
            del self._locks[key]
```

**New test**:
```python
def test_lock_manager_prunes_unlocked_entries():
    manager = FileLockManager()
    for i in range(600):
        manager.get_lock(f"/tmp/file_{i}.md")
    # After exceeding MAX_CACHED_LOCKS, unlocked entries should be pruned
    assert len(manager._locks) <= 501  # 500 max + 1 for the new one
```

**Verify**: Tests pass.

---

### Step 12: Add timeout to SSE subscriber.get() (M4)

**File**: `src/obsidian_ops/app.py:109-126`

Change the `event_generator` to use a timeout:

```python
async def event_generator():
    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        # ... (existing early-return logic unchanged)

    while True:
        try:
            event = await asyncio.wait_for(subscriber.get(), timeout=30.0)
        except asyncio.TimeoutError:
            # Send a keepalive comment to detect dead connections
            yield ": keepalive\n\n"
            continue
        if event is None:
            break
        yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
```

Add `import asyncio` to the top of `app.py` if not already present (it is, from the lifespan).

**Verify**: Existing SSE tests still pass. The keepalive is an SSE comment (starts with `:`) so clients ignore it.

---

### Step 13: Make `inject_overlay` atomic (M2)

**File**: `src/obsidian_ops/inject.py`

Use atomic writes for the HTML modification:

```python
from obsidian_ops.fs_atomic import write_file_atomic

def inject_overlay(site_dir: Path) -> int:
    modified = 0
    for html_file in site_dir.rglob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        if MARKER in content:
            continue

        lower_content = content.lower()
        head_close_idx = lower_content.find("</head>")
        if head_close_idx == -1:
            continue

        updated = content[:head_close_idx] + INJECTION + content[head_close_idx:]
        write_file_atomic(html_file, updated)
        modified += 1

    return modified
```

**Verify**: Existing `test_inject.py` tests all pass (4 tests).

---

### Step 14: Sanitize newlines in `_summarize_args` (L3)

**File**: `src/obsidian_ops/agent.py:33-42`

In the `_summarize_args` function, after truncation, replace newlines:

```python
def _summarize_args(arguments: dict) -> str:
    if not arguments:
        return ""
    parts = []
    for key, value in arguments.items():
        rendered = str(value).replace("\n", "\\n").replace("\r", "\\r")
        if len(rendered) > 80:
            rendered = rendered[:77] + "..."
        parts.append(f"{key}={rendered!r}")
    return ", ".join(parts)
```

**Verify**: Tests pass.

---

## Phase 4 — Architecture Improvements (Steps 15-18)

### Step 15: Convert to app factory pattern (H4, H5)

This is the largest change. It eliminates the module-level `app = create_app()` and the `lru_cache` on settings.

#### 15a. Remove `lru_cache` from `get_settings`

**File**: `src/obsidian_ops/config.py`

Remove `lru_cache` import and decorator. `get_settings` becomes a plain function that creates a new `Settings()` each time:

```python
def get_settings() -> Settings:
    return Settings()
```

#### 15b. Remove module-level `app` instantiation

**File**: `src/obsidian_ops/app.py`

Delete line 152:
```python
app = create_app()  # DELETE THIS LINE
```

#### 15c. Update `__main__.py` to use the factory

**File**: `src/obsidian_ops/__main__.py`

```python
from __future__ import annotations

import uvicorn

from obsidian_ops.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "obsidian_ops.app:create_app",
        host=settings.host,
        port=settings.port,
        factory=True,
    )


if __name__ == "__main__":
    main()
```

#### 15d. Update `demo_cli.py` to use the factory

**File**: `src/obsidian_ops/demo_cli.py:88-92`

Change the uvicorn command:
```python
_run_command(
    ["uvicorn", "obsidian_ops.app:create_app", "--factory", "--host", host, "--port", str(port)],
    cwd=paths.repo_root,
    env=env,
)
```

#### 15e. Simplify test fixture

**File**: `tests/test_api.py`

The fixture no longer needs `importlib.reload` or `get_settings.cache_clear()`:

```python
@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    vault_dir = tmp_path / "vault"
    site_dir = tmp_path / "site"
    vault_dir.mkdir()
    site_dir.mkdir()

    (vault_dir / "index.md").write_text("home", encoding="utf-8")
    (site_dir / "index.html").write_text("<html><head></head><body>ok</body></html>", encoding="utf-8")
    (site_dir / "guides").mkdir()
    (site_dir / "guides" / "getting-started.html").write_text(
        "<html><head></head><body>getting started</body></html>", encoding="utf-8",
    )
    (site_dir / "docs" / "page").mkdir(parents=True)
    (site_dir / "docs" / "page" / "index.html").write_text(
        "<html><head></head><body>docs page</body></html>", encoding="utf-8",
    )

    monkeypatch.setenv("OPS_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("OPS_SITE_DIR", str(site_dir))

    from obsidian_ops.app import create_app
    from obsidian_ops.history_jj import JujutsuHistory
    from obsidian_ops.rebuild import KilnRebuilder
    from obsidian_ops import queue as queue_module

    async def fake_ensure_workspace(self) -> None:
        return None

    async def fake_rebuild(self) -> str:
        return "ok"

    async def fake_run_worker(*_args, **_kwargs) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(JujutsuHistory, "ensure_workspace", fake_ensure_workspace)
    monkeypatch.setattr(KilnRebuilder, "rebuild", fake_rebuild)
    monkeypatch.setattr(queue_module, "run_worker", fake_run_worker)

    app = create_app()
    with TestClient(app) as client:
        yield client
```

**Verify**: All 44+ tests pass. The `importlib.reload` hack is gone.

---

### Step 16: Convert subprocess calls to async (M1)

#### 16a. `JujutsuHistory`

**File**: `src/obsidian_ops/history_jj.py`

Replace `_run_jj` implementation:

```python
async def _run_jj(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            self._jj_bin, *args,
            cwd=str(self._vault_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Jujutsu binary not found: {self._jj_bin}") from exc

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"jj command timed out after {timeout}s: jj {' '.join(args)}")

    return subprocess.CompletedProcess(
        args=[self._jj_bin, *args],
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )
```

Remove the `import subprocess` at the top — wait, you still need `subprocess.CompletedProcess` for the return type. Keep the import but remove the `subprocess.run` usage.

#### 16b. `KilnRebuilder`

**File**: `src/obsidian_ops/rebuild.py`

```python
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class KilnRebuilder:
    def __init__(self, vault_dir: Path, site_dir: Path, kiln_bin: str = "kiln", timeout_s: int = 180) -> None:
        self._vault_dir = vault_dir
        self._site_dir = site_dir
        self._kiln_bin = kiln_bin
        self._timeout_s = timeout_s

    async def rebuild(self) -> str:
        proc = await asyncio.create_subprocess_exec(
            self._kiln_bin, "generate",
            "--input", str(self._vault_dir),
            "--output", str(self._site_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"kiln generate timed out after {self._timeout_s}s")

        if proc.returncode != 0:
            raise RuntimeError(stderr_bytes.decode("utf-8", errors="replace").strip() or "kiln generate failed")
        return stdout_bytes.decode("utf-8", errors="replace").strip()
```

**Verify**: `test_history_jj.py` tests pass (they use real jj). Other tests mock these classes so they're unaffected.

---

### Step 17: Move demo work directory out of `.scratch/` (L6)

**File**: `src/obsidian_ops/demo_cli.py:30-32`

Change:
```python
    work_root = repo_root / ".scratch" / "projects" / "06-demo-scaffold" / "generated"
```
To:
```python
    work_root = repo_root / ".demo"
```

**File**: `.gitignore`

Add `.demo/` to the gitignore:
```
# Demo runtime artifacts
.demo/
```

**Verify**: `ops-demo cleanup` and `ops-demo run` still work if you test manually.

---

### Step 18: Add `__all__` exports (L2)

**File**: `src/obsidian_ops/__init__.py`

Add a minimal public API export:
```python
__all__: list[str] = []
```

For the key modules, add `__all__` listing the public names. For example:

**`models.py`**:
```python
__all__ = ["Job", "JobRequest", "JobResponse", "JobStatus", "SSEEvent", "HistoryEntry"]
```

**`config.py`**:
```python
__all__ = ["Settings", "get_settings"]
```

**`app.py`**:
```python
__all__ = ["create_app"]
```

Do the same for `tools.py` (`ToolRuntime`, `get_tool_definitions`), `agent.py` (`Agent`), `queue.py` (`JobQueue`, `SSEBroadcaster`, `run_worker`), and the other modules.

**Verify**: Tests pass.

---

## Phase 5 — Test Coverage (Steps 19-22)

### Step 19: Add `ToolRuntime` unit tests

**New file**: `tests/test_tools.py`

Create a fixture that builds a `ToolRuntime` with a real temp vault, a `FileLockManager`, and a mock `JujutsuHistory`:

```python
@pytest.fixture
def tool_env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    site = tmp_path / "site"

    monkeypatch.setenv("OPS_VAULT_DIR", str(vault))
    monkeypatch.setenv("OPS_SITE_DIR", str(site))

    settings = Settings()
    locks = FileLockManager()
    jj = AsyncMock(spec=JujutsuHistory)
    runtime = ToolRuntime(settings, locks, jj)
    return runtime, vault
```

Test cases to write:
- `test_read_file` — write a file to vault, read it back via tool
- `test_write_file` — write via tool, verify on disk
- `test_write_file_rejects_bad_extension` — `.py` raises ValueError
- `test_list_files` — create several `.md` files, verify listing
- `test_search_files` — write files with known content, search
- `test_search_files_empty_query` — returns `[]`
- `test_call_tool_unknown_returns_error_string` — unknown tool name
- `test_call_tool_propagates_valueerror` — after Step 8's change
- `test_fetch_url_blocks_private_ip` — after Step 5's change

**Target**: Get `tools.py` above 80% coverage.

---

### Step 20: Add `Agent.run` tests with mocked LLM

**New file**: `tests/test_agent.py`

Mock the OpenAI client to return scripted responses:

```python
@pytest.fixture
def mock_agent(tmp_path, monkeypatch):
    # Set up settings, tool runtime with mocks
    # Patch openai.AsyncOpenAI to return a mock client
    ...
```

Test cases:
- `test_agent_simple_text_response` — LLM returns text, no tool calls
- `test_agent_tool_call_and_response` — LLM calls `read_file`, then responds
- `test_agent_hits_iteration_cap` — LLM keeps calling tools, hits limit
- `test_agent_llm_error_raises_runtime_error` — mock raises, verify propagation

**Target**: Get `agent.py` above 70% coverage.

---

### Step 21: Add `run_worker` integration test

**File**: `tests/test_queue.py`

Add a test that exercises `run_worker` with a mock agent:

```python
@pytest.mark.asyncio
async def test_run_worker_processes_job():
    queue = JobQueue()
    mock_agent = AsyncMock()
    mock_agent.run.return_value = {"summary": "Done", "changed_files": []}
    mock_jj = AsyncMock()
    mock_rebuilder = AsyncMock()

    job = queue.create_job("test", "notes/a.md")

    # Run worker in background, cancel after first job
    worker = asyncio.create_task(
        run_worker(queue, mock_agent, mock_jj, mock_rebuilder, lambda _: None, mock_settings)
    )

    # Wait briefly for processing
    await asyncio.sleep(0.1)
    worker.cancel()

    assert job.status == JobStatus.SUCCEEDED
    assert job.result["summary"] == "Done"
```

Also test the undo path, the rebuild-failure path, and the jj-commit-failure path.

**Target**: Get `queue.py` above 70% coverage.

---

### Step 22: Add `KilnRebuilder` test

**File**: `tests/test_rebuild.py`

After Step 16 converts to async subprocess, you can test with a mock or a simple script:

```python
@pytest.mark.asyncio
async def test_rebuild_calls_kiln_generate(tmp_path):
    # Create a fake kiln script that just touches an output file
    fake_kiln = tmp_path / "fake_kiln.sh"
    fake_kiln.write_text('#!/bin/sh\necho "ok"', encoding="utf-8")
    fake_kiln.chmod(0o755)

    vault = tmp_path / "vault"
    vault.mkdir()
    site = tmp_path / "site"
    site.mkdir()

    rebuilder = KilnRebuilder(vault, site, kiln_bin=str(fake_kiln))
    result = await rebuilder.rebuild()
    assert result == "ok"
```

**Target**: Get `rebuild.py` above 80% coverage.

---

## Phase 6 — Final Verification

### Step 23: Full test suite and lint check

Run everything:
```bash
devenv shell -- python -m pytest tests/ -q --cov=obsidian_ops --cov-report=term-missing
devenv shell -- python -m ruff check src/ tests/
```

**Expected outcomes**:
- All tests pass (44 existing + ~20-30 new)
- 0 ruff violations
- Overall coverage above 70% (up from 53%)

### Step 24: Manual smoke test

```bash
devenv shell -- ops-demo run
```

1. Open `http://127.0.0.1:8080/` in a browser
2. Click the FAB button
3. Enter an instruction (e.g., "Add a summary to this page")
4. Verify SSE progress streaming works
5. Verify Refresh and Undo buttons work
6. Open browser devtools Network tab, verify CORS headers are present

---

## Summary

| Phase | Steps | Issues Addressed |
|-------|-------|-----------------|
| 1. Lint & Hygiene | 1-4 | L1, L4, L5, M7, H1 |
| 2. Security | 5-9 | C1, H2, H3, M5, M6 |
| 3. Memory & Reliability | 10-14 | C2, M2, M4, L3 |
| 4. Architecture | 15-18 | H4, H5, M1, L2, L6 |
| 5. Test Coverage | 19-22 | I1 |
| 6. Verification | 23-24 | — |

Total: 24 steps across 6 phases. Each step is independently committable and verifiable.
