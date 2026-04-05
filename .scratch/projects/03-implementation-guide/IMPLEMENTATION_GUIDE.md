# Obsidian Ops — Implementation Guide

## Overview

This guide walks you through building Obsidian Ops from scratch. Follow it top to bottom. Each step builds on the previous one. By the end, you will have a working local-first agent overlay for an Obsidian vault.

**What you are building:** A FastAPI server that serves a Kiln-rendered Obsidian vault with an injected floating action button. Clicking the button opens a modal where the user types a natural-language instruction. A local LLM agent executes the instruction using file tools. Jujutsu records every change for undo/recovery. The site rebuilds after each mutation.

**Read these first:**

- `.scratch/projects/02-documentation-rewrite/CONCEPT.md` — what the product is
- `.scratch/projects/02-documentation-rewrite/ARCHITECTURE.md` — how it fits together
- `.scratch/projects/02-documentation-rewrite/SPEC.md` — detailed requirements

---

## Prerequisites

### System requirements

- Python 3.13+
- `jj` (Jujutsu) installed and on PATH
- `kiln` installed and on PATH
- A vLLM instance running an OpenAI-compatible Chat Completions API with tool use
- An Obsidian vault already initialized as a Jujutsu workspace (`jj init` already run, `.jj/` exists)

### Python dependencies

Already declared in `pyproject.toml`:

```
fastapi>=0.115.0
pydantic>=2.12.5
uvicorn>=0.34.0
openai>=1.60.0
httpx>=0.28.0
```

Dev:

```
pytest>=7.0
pytest-cov>=4.1
pytest-asyncio>=0.24.0
ruff>=0.5.0
```

Install with:

```bash
pip install -e ".[dev]"
```

---

## Project structure

When you are done, the source tree will look like this:

```
src/obsidian_ops/
  __init__.py
  config.py            # Step 1
  models.py            # Step 2
  locks.py             # Step 3
  fs_atomic.py         # Step 4
  history_jj.py        # Step 5
  rebuild.py           # Step 6
  page_context.py      # Step 7
  inject.py            # Step 8
  tools.py             # Step 9
  agent.py             # Step 10
  queue.py             # Step 11
  app.py               # Step 12
  static/
    ops.css            # Step 13
    ops.js             # Step 14
tests/
  __init__.py
  test_config.py       # Step 15
  test_locks.py
  test_fs_atomic.py
  test_page_context.py
  test_inject.py
  test_history_jj.py
  test_queue.py
  test_api.py
```

Build them in this order. Each module depends only on modules before it.

---

## Step 1: `config.py` — Settings

**Purpose:** Load all configuration from environment variables with sensible defaults. Every other module imports settings from here.

**What to implement:**

A single Pydantic `BaseSettings` class named `Settings` with these fields:

| Field | Type | Env var | Default | Notes |
|-------|------|---------|---------|-------|
| `vault_dir` | `Path` | `OPS_VAULT_DIR` | *(required)* | Absolute path to the Obsidian vault root |
| `site_dir` | `Path` | `OPS_SITE_DIR` | *(required)* | Absolute path to Kiln output directory |
| `vllm_base_url` | `str` | `OPS_VLLM_BASE_URL` | `http://127.0.0.1:8000/v1` | vLLM endpoint |
| `vllm_model` | `str` | `OPS_VLLM_MODEL` | `local-model` | Model name |
| `vllm_api_key` | `str` | `OPS_VLLM_API_KEY` | `""` | API key (empty = no auth) |
| `jj_bin` | `str` | `OPS_JJ_BIN` | `jj` | Path to jj binary |
| `kiln_bin` | `str` | `OPS_KILN_BIN` | `kiln` | Path to kiln binary |
| `kiln_timeout_s` | `int` | `OPS_KILN_TIMEOUT_S` | `180` | Kiln rebuild timeout in seconds |
| `workers` | `int` | `OPS_WORKERS` | `1` | Worker count (locked to 1 for v0) |
| `max_tool_iterations` | `int` | `OPS_MAX_TOOL_ITERATIONS` | `12` | Agent loop iteration cap |
| `max_search_results` | `int` | `OPS_MAX_SEARCH_RESULTS` | `12` | Search result cap per query |
| `page_url_prefix` | `str` | `OPS_PAGE_URL_PREFIX` | `/` | URL prefix for page resolution |
| `host` | `str` | `OPS_HOST` | `127.0.0.1` | Server bind address |
| `port` | `int` | `OPS_PORT` | `8080` | Server port |

**Implementation details:**

- Use `pydantic_settings.BaseSettings` with `model_config = SettingsConfigDict(env_prefix="OPS_")`.
- Add a `@field_validator` on `vault_dir` to resolve it to an absolute path and verify it exists.
- Add a `@field_validator` on `site_dir` to resolve it to an absolute path (create it if missing).
- Expose a module-level function `get_settings()` that constructs and returns a `Settings` instance. Use `@lru_cache` so it is created once per process.

**Constraints:**

- `host` must default to `127.0.0.1`, not `0.0.0.0`. There is no authentication. Binding to all interfaces would expose the vault to the network.
- `workers` is locked to 1 for v0. You can accept other values but the queue will only ever run 1 worker.

---

## Step 2: `models.py` — Data models

**Purpose:** Pydantic models for jobs, API requests, API responses, and SSE events. Used by the queue, API routes, and agent.

**What to implement:**

### `JobStatus` (str enum)

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

### `Job`

```python
class Job(BaseModel):
    id: str                                # UUID hex, generated on creation
    instruction: str                       # user's natural-language request
    file_path: str | None = None           # resolved vault-relative markdown path
    status: JobStatus = JobStatus.QUEUED
    messages: list[str] = []               # accumulated progress messages
    result: dict | None = None             # final summary payload
    error: str | None = None               # error message if failed
    created_at: datetime                   # set on creation
    finished_at: datetime | None = None    # set when terminal state reached
```

### `JobRequest` (API input)

```python
class JobRequest(BaseModel):
    instruction: str
    current_url_path: str
    current_file_path: str | None = None
```

### `JobResponse` (API output for job creation)

```python
class JobResponse(BaseModel):
    job_id: str
```

### `SSEEvent`

```python
class SSEEvent(BaseModel):
    type: str        # "status" | "tool" | "result" | "error" | "done"
    message: str
    payload: dict = {}
```

The `type` field values:

- `status` — job lifecycle (queued, running, committing, rebuilding)
- `tool` — tool call activity (reading file X, searching for Y, writing file Z)
- `result` — final agent summary with changed files
- `error` — something went wrong
- `done` — terminal event, signals stream end

### `HistoryEntry`

```python
class HistoryEntry(BaseModel):
    summary: str
    timestamp: str | None = None
```

---

## Step 3: `locks.py` — Per-file locking

**Purpose:** Prevent concurrent writes to the same vault file. Even with one worker, the agent could issue parallel tool calls within a single turn.

**What to implement:**

A class `FileLockManager` that manages `asyncio.Lock` instances keyed by resolved absolute file path.

```python
class FileLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, path: str) -> asyncio.Lock:
        """Return the lock for this path, creating it if needed."""
        resolved = str(Path(path).resolve())
        if resolved not in self._locks:
            self._locks[resolved] = asyncio.Lock()
        return self._locks[resolved]
```

**Usage pattern (by tools.py later):**

```python
lock = lock_manager.get_lock(abs_path)
async with lock:
    # perform atomic write
```

**Constraints:**

- Vault-wide operations that touch many files must acquire locks in sorted path order to prevent deadlock. Document this in a docstring but don't enforce it in the lock manager itself — callers are responsible.

---

## Step 4: `fs_atomic.py` — Atomic file operations

**Purpose:** Safe file reads and atomic write-by-replace. Ensures writes either fully succeed or leave the original file untouched.

**What to implement:**

### `read_file_safe(path: Path) -> str`

- Read and return the UTF-8 text content of the file.
- If the file is larger than 1MB, raise a `ValueError` with a clear message.
- If the file is larger than 256KB, log a warning (but still return the content).

### `write_file_atomic(path: Path, content: str) -> None`

1. Ensure parent directories exist (`path.parent.mkdir(parents=True, exist_ok=True)`).
2. Write content to a temporary file in the same directory using `tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp")`.
3. Flush and fsync the temp file (`f.flush()`, `os.fsync(f.fileno())`).
4. Atomic replace: `os.replace(tmp_path, path)`.
5. If any step fails after temp file creation, clean up the temp file in a `finally` block (best-effort `os.unlink`).

### `validate_vault_path(vault_root: Path, target: Path) -> Path`

- Resolve both paths to absolute.
- Verify `target` is inside `vault_root` using `target.resolve().is_relative_to(vault_root.resolve())`.
- Reject paths containing `..` segments before resolution.
- Reject paths that write into `.jj/`, `.obsidian/`, or other protected directories.
- Return the resolved absolute path if valid; raise `ValueError` if not.

**Protected directory list:** `.jj`, `.obsidian`, `.git`, `__pycache__`.

---

## Step 5: `history_jj.py` — Jujutsu wrapper

**Purpose:** Thin wrapper around the `jj` CLI for commit, undo, log, and diff. This is the sole durable history layer — the app does not build its own.

**What to implement:**

A class `JujutsuHistory`:

```python
class JujutsuHistory:
    def __init__(self, vault_dir: Path, jj_bin: str = "jj") -> None:
        self._vault_dir = vault_dir
        self._jj_bin = jj_bin
```

### Methods

#### `async def ensure_workspace(self) -> None`

- Run `jj status` in `vault_dir`.
- If it fails (non-zero exit), raise `RuntimeError("Vault is not a Jujutsu workspace")`.

#### `async def commit(self, message: str) -> str`

- Run `jj commit -m "<message>"` in `vault_dir`.
- Return stdout on success.
- Raise `RuntimeError` with stderr on failure.

#### `async def undo(self) -> str`

- Run `jj undo` in `vault_dir`.
- Return stdout on success.
- Raise `RuntimeError` with stderr on failure.

#### `async def log_for_file(self, path: str, limit: int = 10) -> list[str]`

- Run `jj log --no-graph -r "all()" --limit <limit> <path>` in `vault_dir`.
- Parse output into a list of summary strings, one per change entry.
- Return empty list if no history.

#### `async def diff_for_file(self, path: str) -> str`

- Run `jj diff <path>` in `vault_dir`.
- Return the raw diff output.

### Subprocess execution — critical requirement

**Every subprocess call must be non-blocking.** Use this pattern:

```python
async def _run_jj(self, *args: str) -> subprocess.CompletedProcess[str]:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self._jj_bin, *args],
            cwd=str(self._vault_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    return await asyncio.to_thread(_run)
```

All public methods call `_run_jj()`. Never call `subprocess.run()` directly from an async function — it blocks the event loop.

### Timeouts

| Operation | Timeout |
|-----------|---------|
| `jj commit` | 120s |
| `jj undo` | 120s |
| `jj log` | 60s |
| `jj diff` | 120s |

---

## Step 6: `rebuild.py` — Kiln rebuild wrapper

**Purpose:** Run `kiln generate` to rebuild the static site after a mutation.

**What to implement:**

A class `KilnRebuilder`:

```python
class KilnRebuilder:
    def __init__(self, vault_dir: Path, site_dir: Path, kiln_bin: str = "kiln", timeout_s: int = 180) -> None:
        self._vault_dir = vault_dir
        self._site_dir = site_dir
        self._kiln_bin = kiln_bin
        self._timeout_s = timeout_s
```

### Methods

#### `async def rebuild(self) -> str`

- Run `kiln generate --input <vault_dir> --output <site_dir>`.
- Use `asyncio.to_thread()` wrapping `subprocess.run()`, same pattern as `history_jj.py`.
- Return stdout on success.
- Raise `RuntimeError` with stderr on failure.

That's it. One method. Keep it simple.

---

## Step 7: `page_context.py` — URL-to-file resolution

**Purpose:** Map a browser URL path to a vault-relative markdown file path. When the user clicks the FAB on `/notes/foo/`, we need to know they are looking at `notes/foo.md`.

**What to implement:**

### `resolve_page_path(vault_dir: Path, url_path: str, prefix: str = "/") -> str | None`

Algorithm:

1. Strip the `prefix` from the start of `url_path`.
2. Strip leading and trailing slashes.
3. If the result is empty, try `index.md`.
4. Otherwise try `<result>.md`.
5. If that file doesn't exist, try `<result>/index.md`.
6. If neither exists, return `None`.
7. Return the vault-relative path (e.g., `notes/foo.md`).

**Examples:**

| URL path | Resolved file |
|----------|--------------|
| `/` | `index.md` |
| `/notes/foo/` | `notes/foo.md` (or `notes/foo/index.md`) |
| `/notes/foo` | `notes/foo.md` |
| `/about` | `about.md` |

**Known limitation:** This assumes Kiln's URL scheme mirrors the vault path structure. If Kiln uses slugification or custom routing, this will break. A Kiln source manifest would fix it but is out of scope.

---

## Step 8: `inject.py` — Overlay injection

**Purpose:** After Kiln generates the static site, inject `<link>` and `<script>` tags into every HTML page so the FAB and modal appear.

**What to implement:**

### `inject_overlay(site_dir: Path) -> int`

1. Glob for all `*.html` files in `site_dir` (recursively).
2. For each file, read its contents.
3. If the file already contains the injection marker `<!-- ops-overlay -->`, skip it.
4. Find `</head>` in the file (case-insensitive).
5. Insert the following just before `</head>`:

```html
<!-- ops-overlay -->
<link rel="stylesheet" href="/ops/ops.css">
<script src="/ops/ops.js" defer></script>
```

6. Write the modified file back.
7. Return the count of files modified.

**Constraints:**

- If `</head>` is not found, skip the file (don't crash).
- Use plain string operations. No HTML parser needed for this.
- This runs after every `kiln generate` and once at server startup.

---

## Step 9: `tools.py` — Agent tool implementations

**Purpose:** The seven tools the LLM agent can call to interact with the vault. This is the core of the product — the agent reads, writes, searches, and fetches through these tools.

**Dependencies:** `config.py`, `locks.py`, `fs_atomic.py`, `history_jj.py`

**What to implement:**

A class `ToolRuntime` that holds references to settings, the lock manager, and the Jujutsu wrapper:

```python
class ToolRuntime:
    def __init__(
        self,
        settings: Settings,
        lock_manager: FileLockManager,
        jj: JujutsuHistory,
    ) -> None:
        self._settings = settings
        self._locks = lock_manager
        self._jj = jj
        self.changed_files: list[str] = []   # tracks files written in current job
```

### Tool 1: `read_file(path: str) -> str`

1. Validate path against vault root using `validate_vault_path()`.
2. Read file using `read_file_safe()`.
3. Return the content as a string.

### Tool 2: `write_file(path: str, content: str) -> str`

1. Validate path against vault root.
2. Acquire the per-file lock.
3. Write using `write_file_atomic()`.
4. Add the vault-relative path to `self.changed_files`.
5. Release lock (automatically via `async with`).
6. Return a confirmation string like `"Wrote <path> (<N> bytes)"`.

### Tool 3: `list_files(glob_pattern: str = "**/*.md") -> list[str]`

1. Use `Path(vault_dir).glob(glob_pattern)`.
2. Return vault-relative paths as strings.
3. Sort alphabetically.

### Tool 4: `search_files(query: str, glob_pattern: str = "**/*.md") -> list[dict]`

1. Glob for matching files in the vault.
2. For each file, read its content and do a case-insensitive substring search for `query`.
3. For each match, extract a context snippet (the matching line plus 1 line above and below).
4. Return a list of `{"path": "<relative>", "snippet": "<context>"}` dicts.
5. Cap results at `settings.max_search_results`.

### Tool 5: `fetch_url(url: str) -> str`

1. Use `httpx.AsyncClient` to GET the URL with a reasonable timeout (30s).
2. Return the response text, truncated to 120KB if larger.
3. On failure, return a clear error string (don't raise).

### Tool 6: `undo_last_change() -> str`

1. Delegate to `self._jj.undo()`.
2. Return the result string.

### Tool 7: `get_file_history(path: str, limit: int = 10) -> list[str]`

1. Validate path against vault root.
2. Delegate to `self._jj.log_for_file(path, limit)`.
3. Return the list of history entries.

### Tool definitions for the LLM

Also implement a function that returns the OpenAI-format tool definitions:

```python
def get_tool_definitions() -> list[dict]:
```

Each tool definition follows the OpenAI function-calling schema:

```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the contents of a markdown file in the vault.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Vault-relative file path (e.g. 'notes/example.md')"
                }
            },
            "required": ["path"]
        }
    }
}
```

Define all seven tools this way. The descriptions should be concise and practical — they are part of the LLM prompt.

### Tool dispatch

Implement a dispatch method:

```python
async def call_tool(self, name: str, arguments: dict) -> str:
```

This takes the tool name and arguments from the LLM response and routes to the correct method. Return the result as a string. If the tool name is unknown, return an error string.

### Reset per job

```python
def reset(self) -> None:
    self.changed_files = []
```

Call this at the start of each job so file tracking is clean.

---

## Step 10: `agent.py` — Agent loop

**Purpose:** The tool-use conversation loop against vLLM. Takes a user instruction, constructs the system prompt, calls the LLM, executes tool calls, and repeats until the model returns a final text response.

**Dependencies:** `config.py`, `models.py`, `tools.py`

**What to implement:**

### System prompt

```
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

If `current_file_path` is `None`, replace the last line with:
```
No specific file is currently selected. The user may be asking about the vault generally.
```

### Agent class

```python
class Agent:
    def __init__(self, settings: Settings, tool_runtime: ToolRuntime) -> None:
        self._settings = settings
        self._tools = tool_runtime
        self._client = openai.AsyncOpenAI(
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key or "no-key",
        )
```

### `async def run(self, instruction: str, file_path: str | None, on_progress: Callable) -> dict`

**`on_progress`** is an async callback: `async def on_progress(event: SSEEvent) -> None`. The agent calls it to stream progress to the browser.

**The loop:**

1. Reset tool runtime (`self._tools.reset()`).
2. Build the system prompt with `file_path`.
3. Initialize messages list with system message and user message.
4. Send a `status` progress event: `"Agent started"`.
5. Enter the tool-use loop (max `settings.max_tool_iterations` iterations):
   a. Call `self._client.chat.completions.create()` with:
      - `model=settings.vllm_model`
      - `messages=messages`
      - `tools=get_tool_definitions()`
      - `tool_choice="auto"`
   b. Get the assistant's response message.
   c. Append the assistant message to `messages`.
   d. If the response has no tool calls, break — the model is done.
   e. For each tool call in the response:
      - Parse `tool_call.function.name` and `json.loads(tool_call.function.arguments)`.
      - Send a `tool` progress event: `"Calling {name}({args summary})"`.
      - Execute via `self._tools.call_tool(name, arguments)`.
      - Append a tool result message to `messages`:
        ```python
        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
        ```
6. After the loop ends, extract the final text from the last assistant message.
7. Build and return the result dict:

```python
{
    "summary": final_text,
    "changed_files": self._tools.changed_files,
}
```

8. Send a `result` progress event with the summary.

**Error handling:**

- If the LLM call fails (network error, timeout), catch the exception and raise a descriptive `RuntimeError`.
- If a tool call fails, return the error string as the tool result (so the model can see it and adapt). Do not abort the loop on tool errors.
- If the loop reaches `max_tool_iterations` without a final response, return what you have with a note that the agent hit its iteration limit.

---

## Step 11: `queue.py` — Job queue and SSE

**Purpose:** In-memory FIFO job queue with one worker and SSE event broadcasting.

**Dependencies:** `config.py`, `models.py`

**What to implement:**

### `SSEBroadcaster`

Manages per-job SSE subscriber lists.

```python
class SSEBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """Create and return a new subscriber queue for this job."""
        q: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    async def publish(self, job_id: str, event: SSEEvent) -> None:
        """Send an event to all subscribers of this job."""
        for q in self._subscribers.get(job_id, []):
            await q.put(event)

    async def close(self, job_id: str) -> None:
        """Send None to all subscribers to signal stream end, then clean up."""
        for q in self._subscribers.get(job_id, []):
            await q.put(None)
        self._subscribers.pop(job_id, None)
```

### `JobQueue`

```python
class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._pending: asyncio.Queue[str] = asyncio.Queue()
        self.broadcaster = SSEBroadcaster()

    def create_job(self, instruction: str, file_path: str | None) -> Job:
        """Create a job, store it, enqueue it, return it."""
        job = Job(
            id=uuid.uuid4().hex[:8],
            instruction=instruction,
            file_path=file_path,
            created_at=datetime.now(UTC),
        )
        self._jobs[job.id] = job
        self._pending.put_nowait(job.id)
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> list[Job]:
        """Return recent jobs, newest first."""
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    async def next_job_id(self) -> str:
        """Block until a job is available, return its ID."""
        return await self._pending.get()
```

### Worker loop

Implement the worker as a standalone async function that the app starts as a background task:

```python
async def run_worker(
    queue: JobQueue,
    agent: Agent,
    jj: JujutsuHistory,
    rebuilder: KilnRebuilder,
    injector: Callable,        # inject_overlay function
    settings: Settings,
) -> None:
```

**The worker loop:**

1. `while True:`
2. `job_id = await queue.next_job_id()`
3. Get the job from `queue`.
4. Set `job.status = RUNNING`.
5. Publish a `status` event: `"Job started"`.
6. Create a progress callback that publishes SSE events:
   ```python
   async def on_progress(event: SSEEvent) -> None:
       job.messages.append(event.message)
       await queue.broadcaster.publish(job_id, event)
   ```
7. Try:
   a. Run the agent: `result = await agent.run(job.instruction, job.file_path, on_progress)`.
   b. If the agent wrote files (`result["changed_files"]` is non-empty):
      - Publish `status` event: `"Recording changes..."`.
      - `await jj.commit(f"ops: {job.instruction[:80]}")`.
      - Publish `status` event: `"Rebuilding site..."`.
      - `await rebuilder.rebuild()`.
      - `injector(settings.site_dir)`.
   c. Set `job.status = SUCCEEDED`, `job.result = result`, `job.finished_at = now()`.
   d. Publish a `done` event with the summary.
8. Except any exception:
   a. Set `job.status = FAILED`, `job.error = str(e)`, `job.finished_at = now()`.
   b. Publish an `error` event with the error message.
   c. Publish a `done` event to signal stream end.
9. Finally:
   a. `await queue.broadcaster.close(job_id)`.

**Partial success handling:**

If `jj commit` succeeds but `kiln generate` fails, the file changes are durable in Jujutsu but the site is stale. In this case:
- Still set `job.status = SUCCEEDED` (the vault change succeeded).
- Include a note in the result: `"Changes saved but site rebuild failed. Refresh may show stale content."`.
- Do NOT set `job.status = FAILED` for rebuild-only failures.

If `jj commit` fails after file writes, this is more severe:
- Set `job.status = FAILED`.
- Include a clear error: `"Files were changed but history recording failed. You may need to inspect the vault manually."`.

---

## Step 12: `app.py` — FastAPI application

**Purpose:** Wire everything together. HTTP routes, SSE streaming, static file mounts, and server lifespan.

**Dependencies:** Everything.

**What to implement:**

### Lifespan

Use FastAPI's `@asynccontextmanager` lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 1. Validate Jujutsu workspace
    jj = JujutsuHistory(settings.vault_dir, settings.jj_bin)
    await jj.ensure_workspace()

    # 2. Initial site build
    rebuilder = KilnRebuilder(settings.vault_dir, settings.site_dir, settings.kiln_bin, settings.kiln_timeout_s)
    await rebuilder.rebuild()
    inject_overlay(settings.site_dir)

    # 3. Initialize components
    lock_manager = FileLockManager()
    tool_runtime = ToolRuntime(settings, lock_manager, jj)
    agent = Agent(settings, tool_runtime)
    queue = JobQueue()

    # 4. Start worker
    worker_task = asyncio.create_task(
        run_worker(queue, agent, jj, rebuilder, inject_overlay, settings)
    )

    # 5. Store on app state for route access
    app.state.settings = settings
    app.state.queue = queue
    app.state.jj = jj
    app.state.rebuilder = rebuilder

    yield

    # 6. Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
```

### Routes

#### `GET /api/health`

Return `{"status": "ok"}`.

#### `POST /api/jobs`

1. Parse `JobRequest` from body.
2. Resolve `current_file_path`:
   - If provided in the request, use it.
   - Otherwise, call `resolve_page_path(settings.vault_dir, request.current_url_path, settings.page_url_prefix)`.
3. Create job via `queue.create_job(request.instruction, file_path)`.
4. Return `JobResponse(job_id=job.id)`.

#### `GET /api/jobs/{job_id}/stream`

1. Look up the job. If not found, return 404.
2. Subscribe to SSE: `subscriber = queue.broadcaster.subscribe(job_id)`.
3. Return a `StreamingResponse` with `media_type="text/event-stream"`:

```python
async def event_generator():
    # If the job is already done, send the final state immediately
    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        final = SSEEvent(type="done", message=job.result.get("summary", "") if job.result else job.error or "")
        yield f"event: done\ndata: {final.model_dump_json()}\n\n"
        return

    while True:
        event = await subscriber.get()
        if event is None:
            break
        event_type = event.type
        yield f"event: {event_type}\ndata: {event.model_dump_json()}\n\n"
```

#### `GET /api/jobs`

Return the list of recent jobs from `queue.list_jobs()`.

#### `POST /api/undo`

1. Create an undo job: `queue.create_job("undo", None)`.

Actually — undo is simpler than a full agent job. It doesn't need the agent. Handle it as a special case:

**Better approach:** Don't route undo through the agent. Handle it directly:

1. Run `jj.undo()`.
2. Run `rebuilder.rebuild()`.
3. Run `inject_overlay(settings.site_dir)`.
4. Return `{"status": "ok", "message": "Last change undone"}`.

But this must still be queued to avoid concurrent mutations. Two options:

**Option A (simpler):** Route undo through the job queue as a special job type. Add an `is_undo: bool` field to `Job`. In the worker loop, check `job.is_undo` and if true, skip the agent and go straight to `jj undo` + rebuild.

**Option B:** Execute undo inline but acquire a global lock. Since v0 has one worker, the worker queue effectively serializes everything.

**Go with Option A.** Add `is_undo: bool = False` to the `Job` model. In the worker:

```python
if job.is_undo:
    await jj.undo()
    await rebuilder.rebuild()
    injector(settings.site_dir)
    job.status = SUCCEEDED
    job.result = {"summary": "Last change undone."}
else:
    # normal agent flow
```

The `POST /api/undo` endpoint:

```python
job = queue.create_undo_job()  # sets is_undo=True, instruction="undo"
return JobResponse(job_id=job.id)
```

#### `GET /api/history`

1. Parse query param `path` (required) and `limit` (optional, default 10).
2. Call `jj.log_for_file(path, limit)`.
3. Return the list of entries.

### Static file mounts

Mount order matters. API routes are registered first (they are the most specific), then overlay assets, then the site catch-all:

```python
# After all API routes are defined:

# 1. Overlay assets: /ops/
app.mount("/ops", StaticFiles(directory=str(static_dir)), name="ops")

# 2. Generated site: / (catch-all, must be last)
app.mount("/", StaticFiles(directory=str(settings.site_dir), html=True), name="site")
```

Where `static_dir` is the `static/` directory inside the `obsidian_ops` package.

**Important:** The site mount uses `html=True` so that requests to `/notes/foo/` serve `/notes/foo/index.html` or similar.

### Entry point

Add a `__main__.py` or a console script:

```python
if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("obsidian_ops.app:app", host=settings.host, port=settings.port)
```

---

## Step 13: `static/ops.css` — Overlay styles

**Purpose:** Style the floating action button and modal. Keep it minimal and unobtrusive.

**What to implement:**

### FAB

- Fixed position, bottom-right corner (`bottom: 24px; right: 24px`).
- Circular button, ~56px diameter.
- Subtle background color, white icon/text.
- `z-index: 10000` to float above page content.
- Hover effect (slight scale or shadow change).
- Cursor pointer.

### Modal backdrop

- Fixed, full-viewport overlay.
- Semi-transparent dark background (`rgba(0,0,0,0.5)`).
- `z-index: 10001`.
- `display: none` by default, `display: flex` when active (centered content).

### Modal container

- White/light background, rounded corners, padding.
- Max width ~600px, max height ~80vh.
- Scrollable content area for progress output.

### Modal elements

- **Header area:** Current page path display (small, muted text).
- **Text input:** Full-width `<textarea>`, 3-4 rows.
- **Submit button:** Clear, styled, disabled while job is running.
- **Close button:** Top-right X or Cancel button.
- **Progress area:** Monospace, scrollable `<div>` for streamed events. Hidden until job starts.
- **Action area:** Buttons for Refresh and Undo, hidden until job completes successfully.

### States

Style these modal states:

- **Input state:** textarea + submit visible, progress hidden.
- **Running state:** textarea disabled, submit disabled, progress visible with streaming text.
- **Success state:** progress visible, summary highlighted, Refresh + Undo buttons visible, textarea re-enabled for follow-up.
- **Error state:** progress visible, error highlighted in red, textarea re-enabled.

---

## Step 14: `static/ops.js` — Browser overlay

**Purpose:** The entire client-side behavior. Renders the FAB, manages the modal, submits jobs, subscribes to SSE, and provides refresh/undo actions.

**What to implement:**

### Initialization

On `DOMContentLoaded`:

1. Create and inject the FAB element into `document.body`.
2. Create and inject the modal HTML into `document.body`.
3. Bind event listeners.

### FAB behavior

- On click: open the modal, populate the current page path from `window.location.pathname`.

### Modal behavior

#### Opening

- Show the modal backdrop and container.
- Set the page context text to the current URL path.
- Focus the textarea.

#### Closing

- If a job is running, show a brief confirmation or just allow it (the job continues in the background).
- Hide the modal.
- Reset to input state.

#### Submission

1. Read the textarea value.
2. POST to `/api/jobs`:
   ```json
   {
     "instruction": "<textarea value>",
     "current_url_path": "<window.location.pathname>"
   }
   ```
3. On response, get `job_id`.
4. Switch to running state.
5. Open SSE connection: `new EventSource("/api/jobs/<job_id>/stream")`.

#### SSE handling

Listen for events on the EventSource:

- `status` event: append message to progress area.
- `tool` event: append message to progress area.
- `result` event: display summary prominently.
- `error` event: display error in red.
- `done` event: close the EventSource. Switch to success or error state depending on content.

#### Refresh action

Button click: `window.location.reload()`.

#### Undo action

1. POST to `/api/undo`.
2. On response, get `job_id`.
3. Open SSE for the undo job.
4. On completion, show success and refresh button.

### HTMX tolerance

If the site uses HTMX for client-side navigation, the overlay elements must survive page swaps. Two approaches:

- **Option A:** Re-inject the FAB after every HTMX swap by listening to `htmx:afterSwap`.
- **Option B:** Place the FAB and modal outside the HTMX swap target (e.g., directly on `<body>`).

Go with Option B — elements injected directly onto `document.body` will survive content swaps within a sub-container.

### No framework

Write this as plain vanilla JavaScript. No React, no Vue, no build step. The entire overlay is one JS file and one CSS file.

---

## Step 15: Tests

**Purpose:** Verify correctness at the unit and integration level. Use pytest with pytest-asyncio.

### Test file: `tests/test_fs_atomic.py`

Test atomic writes:

- Write a new file, read it back, verify contents match.
- Write to an existing file, verify it is replaced atomically.
- Verify parent directories are created automatically.
- Verify content size guard: file > 1MB raises `ValueError`.
- Verify 256KB+ file logs a warning but still returns content.

Test path validation:

- Valid vault-relative path resolves correctly.
- Path with `../` is rejected.
- Path into `.jj/` is rejected.
- Path into `.obsidian/` is rejected.
- Path outside vault root is rejected.

### Test file: `tests/test_locks.py`

- Two coroutines acquiring the same lock execute sequentially.
- Two coroutines acquiring different locks can overlap.
- Same path always returns the same lock instance.

### Test file: `tests/test_page_context.py`

- `/` resolves to `index.md` (when it exists).
- `/notes/foo/` resolves to `notes/foo.md` (when it exists).
- `/notes/foo/` resolves to `notes/foo/index.md` (when `foo.md` doesn't exist but `foo/index.md` does).
- `/nonexistent` returns `None`.
- Prefix stripping works correctly.

### Test file: `tests/test_inject.py`

- HTML file gets overlay tags injected before `</head>`.
- Already-injected file (with marker) is skipped.
- File without `</head>` is skipped.
- Returns correct count of modified files.

### Test file: `tests/test_history_jj.py`

These are integration tests requiring a real `jj` installation. Use a temporary directory:

```python
@pytest.fixture
def jj_workspace(tmp_path):
    subprocess.run(["jj", "git", "init"], cwd=str(tmp_path), check=True)
    return tmp_path
```

Tests:

- `ensure_workspace()` succeeds in a valid workspace.
- `ensure_workspace()` raises in a non-workspace directory.
- Write a file, `commit()`, then `log_for_file()` returns at least one entry.
- `commit()` then `undo()` restores the previous state.

### Test file: `tests/test_queue.py`

- `create_job()` returns a job with status `QUEUED`.
- `list_jobs()` returns jobs newest-first.
- `get_job()` returns `None` for unknown ID.
- SSE broadcaster: publish sends to all subscribers.
- SSE broadcaster: close sends `None` sentinel.

### Test file: `tests/test_config.py`

- Required fields raise validation error when missing.
- Defaults are applied correctly.
- `vault_dir` must exist.
- `host` defaults to `127.0.0.1`.

### Test file: `tests/test_api.py`

Use FastAPI's `TestClient` (or `httpx.AsyncClient` with `ASGITransport`).

These require more setup — mock the vLLM endpoint and provide a temporary vault with jj. At minimum:

- `GET /api/health` returns 200 with `{"status": "ok"}`.
- `POST /api/jobs` with valid body returns 200 with `job_id`.
- `GET /api/jobs` returns a list.
- `POST /api/jobs` with missing instruction returns 422.

For full integration tests involving the agent, consider mocking the OpenAI client to return predetermined tool calls and final responses.

### Running tests

```bash
pytest tests/ -v
```

For coverage:

```bash
pytest tests/ --cov=obsidian_ops --cov-report=term-missing
```

---

## End-to-end walkthrough

Once everything is built, this is what happens when a user clicks the FAB and types "clean up this note":

1. **Browser:** User clicks FAB on `/notes/example/`. Modal opens showing the path.
2. **Browser:** User types "clean up this note" and clicks Submit.
3. **Browser:** `ops.js` sends `POST /api/jobs {"instruction": "clean up this note", "current_url_path": "/notes/example/"}`.
4. **Server (`app.py`):** Resolves `/notes/example/` to `notes/example.md` via `page_context.py`.
5. **Server (`app.py`):** Creates a job via `queue.create_job("clean up this note", "notes/example.md")`.
6. **Server (`app.py`):** Returns `{"job_id": "a1b2c3d4"}`.
7. **Browser:** Opens `EventSource("/api/jobs/a1b2c3d4/stream")`.
8. **Server (`queue.py`):** Worker picks up the job, sets status to RUNNING.
9. **Server (`agent.py`):** Constructs system prompt with `notes/example.md` as current file.
10. **Server (`agent.py`):** Sends messages + tool definitions to vLLM.
11. **vLLM:** Returns a tool call: `read_file(path="notes/example.md")`.
12. **Server (`tools.py`):** Reads the file, returns content to the agent loop.
13. **Server (`agent.py`):** Sends tool result back to vLLM.
14. **vLLM:** Returns another tool call: `write_file(path="notes/example.md", content="<cleaned up content>")`.
15. **Server (`tools.py`):** Acquires lock, atomic writes, releases lock, tracks the changed file.
16. **Server (`agent.py`):** Sends tool result back to vLLM.
17. **vLLM:** Returns final text: "I reorganized the note with clearer headings and moved the summary to the top."
18. **Server (`queue.py`):** Agent done. Worker runs `jj commit -m "ops: clean up this note"`.
19. **Server (`queue.py`):** Worker runs `kiln generate`.
20. **Server (`queue.py`):** Worker runs `inject_overlay()`.
21. **Server (`queue.py`):** Publishes `done` SSE event with summary.
22. **Browser:** Receives done event. Shows summary, Refresh button, Undo button.
23. **User:** Clicks Refresh. Page reloads with the cleaned-up note.

---

## Implementation checklist

Use this to track your progress:

- [ ] **Step 1:** `config.py` — Settings model
- [ ] **Step 2:** `models.py` — Pydantic data models
- [ ] **Step 3:** `locks.py` — Per-file lock manager
- [ ] **Step 4:** `fs_atomic.py` — Atomic reads/writes and path validation
- [ ] **Step 5:** `history_jj.py` — Jujutsu wrapper
- [ ] **Step 6:** `rebuild.py` — Kiln rebuild wrapper
- [ ] **Step 7:** `page_context.py` — URL-to-file resolution
- [ ] **Step 8:** `inject.py` — Overlay injection
- [ ] **Step 9:** `tools.py` — Agent tool implementations
- [ ] **Step 10:** `agent.py` — Agent loop
- [ ] **Step 11:** `queue.py` — Job queue and SSE broadcasting
- [ ] **Step 12:** `app.py` — FastAPI app and routes
- [ ] **Step 13:** `static/ops.css` — Overlay styles
- [ ] **Step 14:** `static/ops.js` — Browser overlay
- [ ] **Step 15:** Tests — Unit and integration tests
- [ ] **Manual acceptance:** Run through the 7 acceptance criteria from the spec

---

## Manual acceptance criteria

After everything is built and tests pass, verify these by hand:

1. App starts, initial Kiln build completes, overlay appears on pages.
2. FAB is visible in the bottom-right on rendered pages.
3. Submit a cleanup instruction — see SSE progress in the modal — refresh — content has changed.
4. Submit a "find related notes" instruction — verify new links or notes created.
5. Submit a URL fetch instruction — verify a source note is created with fetched content.
6. Click Undo — verify the previous state is restored.
7. Query `GET /api/history?path=<some-file>` — verify entries are returned.

---

## Common pitfalls

1. **Blocking the event loop.** Every `subprocess.run()` call must go through `asyncio.to_thread()`. If you call `subprocess.run()` directly in an `async def`, SSE streams will stall and HTTP requests will hang during `jj` and `kiln` operations.

2. **Binding to 0.0.0.0.** Don't. There's no auth. Always default to `127.0.0.1`.

3. **Forgetting to inject overlay after rebuild.** Every `kiln generate` must be followed by `inject_overlay()`. The overlay tags are in the generated HTML, not in the vault markdown. They disappear on every rebuild.

4. **Mount order.** The site `StaticFiles` mount must be last because it's a catch-all (`html=True`). If you mount it before `/ops/` or `/api/`, those routes will be shadowed.

5. **Path validation.** Every file tool must validate paths before operating. A missing validation means the LLM could read/write files outside the vault.

6. **Undo semantics at concurrency > 1.** Don't increase `workers` without redesigning undo. `jj undo` reverses the most recent global operation, not a specific job.

7. **Temp file cleanup.** In `write_file_atomic`, if the atomic replace fails, the temp file must be cleaned up. Use a `try/finally` block.

8. **SSE stream lifecycle.** Always send a terminal event (`done` or `error`) and call `broadcaster.close()`. If you don't, the browser's `EventSource` will keep reconnecting forever.
