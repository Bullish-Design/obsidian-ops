# Simplified Obsidian Ops Implementation Guide
## Canonical simplified / agentic / Jujutsu-backed version

## Executive summary

This implementation guide **replaces** the previous drifted version.

The canonical implementation is:

- **local-first**
- **file-native**
- **one floating action button**
- **one modal**
- **natural-language instructions only**
- **one generic job API**
- **SSE progress streaming**
- **in-memory async job queue**
- **low concurrency**
- **per-file in-process locking**
- **coarse Kiln rebuilds after successful writes**
- **Jujutsu as the only durable history / undo / diff / restore layer**

This guide intentionally does **not** implement:

- command-specific public APIs like `/api/rewrite` or `/api/save_url`
- a selection toolbar
- a command registry
- SQLite
- durable jobs
- a second custom snapshot/history subsystem
- Git as the product’s primary history model

The governing loop is:

**render vault → open modal → describe intent → run agent → mutate files → record change with Jujutsu → rebuild → refresh or undo**

---

## 1. What changed from the previous guide

The previous implementation guide drifted away from the simplified direction. These are the required corrections:

| Old direction | Canonical direction |
|---|---|
| Git-backed undo and diff | **Jujutsu-backed** undo and history |
| `/api/rewrite`, `/api/organize_note`, `/api/save_url` | **`POST /api/jobs`** |
| polling job status | **SSE streaming** |
| command-oriented runtime | **tool-using agent loop** |
| selection resolution as core behavior | **no selection-toolbar flow in v0** |
| user manually enters file path | **current page context is automatic** |
| three public commands | **one natural-language job surface** |

If you preserve these corrections, the implementation will stay aligned with the concept, canonical direction, architecture, and revised README.

---

## 2. Scope and implementation posture

### In scope

- Serve a Kiln-rendered vault site through one FastAPI app
- Inject one lightweight overlay (`ops.js`, `ops.css`)
- Accept one natural-language instruction plus current page context
- Run one generic agent/tool loop against the vault
- Stream progress over SSE
- Write markdown files atomically
- Record user-visible change boundaries through Jujutsu
- Trigger a coarse rebuild after successful writes
- Expose lightweight history and undo affordances

### Out of scope

- Durable queue recovery after restart
- Selection-toolbar editing
- Command-specific public APIs
- Database-backed job/history systems
- Rich app-owned history metadata
- Multi-surface UI
- Fine-grained incremental renderer integration
- Any custom VCS layer parallel to Jujutsu

### Important design choice for v0

Use **exactly one mutating Jujutsu command per successful app job**:

- the app writes files directly
- then it finalizes the current change with `jj commit -m "<summary>"`

That matters because it makes **`jj undo` a clean v0 undo mechanism**: one successful app mutation job maps to one user-visible Jujutsu change boundary.

---

## 3. Assumptions

- Python 3.12
- FastAPI
- Kiln installed and available as `kiln`
- Jujutsu installed and available as `jj`
- The vault is already inside a Jujutsu workspace (`.jj/` exists)
- vLLM is running an OpenAI-compatible Chat API endpoint
- The rendered site output directory can be blown away and regenerated
- The vault is used by one local user through one local app process

This guide keeps the runtime simple by **requiring the Jujutsu workspace to already exist** rather than teaching the app to initialize or migrate repos.

---

## 4. Recommended project layout

Keep the codebase roughly this small:

```text
obsidian_ops/
  __init__.py
  app.py
  config.py
  models.py
  queue.py
  agent.py
  tools.py
  history_jj.py
  rebuild.py
  inject.py
  locks.py
  fs_atomic.py
  page_context.py
  static/
    ops.js
    ops.css
tests/
  test_atomic.py
  test_queue.py
  test_history_jj.py
  test_page_context.py
  test_api.py
```

This is the right scale.

Do not introduce:

- `commands.py`
- `db.py`
- `repositories/`
- `services/` sprawl
- command-specific route modules
- a hybrid history adapter layer

---

## 5. Runtime flow

```mermaid
flowchart LR
  A[Browser page] --> B[FAB opens modal]
  B --> C[POST /api/jobs]
  C --> D[In-memory queue]
  D --> E[Worker starts job]
  E --> F[Agent loop]
  F --> G[read/write/search/fetch tools]
  G --> H[Atomic file write]
  H --> I[jj commit -m summary]
  I --> J[kiln generate]
  J --> K[SSE final event]
  K --> L[Refresh or undo]
  L --> M[POST /api/undo]
  M --> N[jj undo]
  N --> O[kiln generate]
```

### Core runtime rules

- Use **one worker** by default
- Use **per-file locks**
- Use **SSE** for progress
- Use **one Jujutsu commit boundary** per successful job
- Use **coarse rebuilds** after successful write jobs and undo

---

## 6. Models and config

### `obsidian_ops/config.py`

```python
from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    vault_dir: Path = Field(..., description="Path to the Obsidian vault root.")
    site_dir: Path = Field(..., description="Path to Kiln output directory.")
    jj_bin: str = Field(default="jj")
    kiln_bin: str = Field(default="kiln")
    kiln_timeout_s: int = Field(default=180)
    worker_concurrency: int = Field(default=1)

    vllm_base_url: str = Field(default="http://127.0.0.1:8000/v1")
    vllm_api_key: str = Field(default="EMPTY")
    vllm_model: str = Field(default="local-model")

    max_tool_iterations: int = Field(default=12)
    max_search_results: int = Field(default=12)
    page_url_prefix: str = Field(default="/")

    @classmethod
    def from_env(cls) -> "Settings":
        vault_dir = os.environ["OPS_VAULT_DIR"]
        site_dir = os.environ["OPS_SITE_DIR"]
        return cls(
            vault_dir=Path(vault_dir).expanduser().resolve(),
            site_dir=Path(site_dir).expanduser().resolve(),
            jj_bin=os.environ.get("OPS_JJ_BIN", "jj"),
            kiln_bin=os.environ.get("OPS_KILN_BIN", "kiln"),
            kiln_timeout_s=int(os.environ.get("OPS_KILN_TIMEOUT_S", "180")),
            worker_concurrency=int(os.environ.get("OPS_WORKERS", "1")),
            vllm_base_url=os.environ.get("OPS_VLLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            vllm_api_key=os.environ.get("OPS_VLLM_API_KEY", "EMPTY"),
            vllm_model=os.environ.get("OPS_VLLM_MODEL", "local-model"),
            max_tool_iterations=int(os.environ.get("OPS_MAX_TOOL_ITERATIONS", "12")),
            max_search_results=int(os.environ.get("OPS_MAX_SEARCH_RESULTS", "12")),
            page_url_prefix=os.environ.get("OPS_PAGE_URL_PREFIX", "/"),
        )
```

### `obsidian_ops/models.py`

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    current_url_path: str = Field(..., description="Browser pathname, e.g. /notes/foo/")
    current_file_path: str | None = Field(
        default=None,
        description="Vault-relative markdown path if the browser already knows it."
    )


class ProgressEvent(BaseModel):
    type: Literal["status", "tool", "result", "error", "done"]
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str
    state: JobState
    request: JobRequest
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class HistoryEntry(BaseModel):
    text: str


class JobSummary(BaseModel):
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    history_hint: str | None = None
```

---

## 7. Per-file locking and atomic writes

### `obsidian_ops/locks.py`

```python
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator


class PathLocks:
    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}

    async def _get(self, path: Path) -> asyncio.Lock:
        key = str(path.resolve())
        async with self._guard:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    @asynccontextmanager
    async def hold(self, path: Path) -> AsyncIterator[None]:
        lock = await self._get(path)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
```

### `obsidian_ops/fs_atomic.py`

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp.",
        dir=str(path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
```

---

## 8. Current-page context resolution

Canonical direction says the current page path should be **automatic**. In v0, keep it simple:

1. the browser sends `location.pathname`
2. the server resolves that to a vault-relative markdown path
3. the resolved file path is injected into the agent prompt

This assumes the site output path mostly mirrors the vault path.

### `obsidian_ops/page_context.py`

```python
from __future__ import annotations

from pathlib import Path


class PageContextError(RuntimeError):
    pass


def infer_markdown_path_from_url(url_path: str, vault_dir: Path) -> str:
    """
    Minimal v0 resolver:
    - /foo/bar/      -> foo/bar.md
    - /foo/bar.html  -> foo/bar.md
    - /              -> index.md if it exists
    """
    normalized = url_path.strip()
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    if normalized == "/":
        candidate = vault_dir / "index.md"
        if candidate.is_file():
            return "index.md"
        raise PageContextError("Unable to infer current page for root URL")

    path = normalized.strip("/")

    if path.endswith(".html"):
        rel = path[:-5] + ".md"
    else:
        rel = path.rstrip("/") + ".md"

    candidate = vault_dir / rel
    if candidate.is_file():
        return rel

    candidate = vault_dir / path / "index.md"
    if candidate.is_file():
        return str(Path(path) / "index.md")

    raise PageContextError(f"Unable to infer markdown path for URL: {url_path}")
```

Later, if Kiln exposes a source-path manifest, replace this with that. For v0, keep it boring.

---

## 9. Jujutsu wrapper

This is the only durable history layer.

### Why this wrapper should stay thin

The app should not invent its own version-control worldview. It only needs:

- workspace existence checks
- one user-visible change boundary after successful writes
- recent history text for a file
- last-change undo

### `obsidian_ops/history_jj.py`

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel


class JujutsuError(RuntimeError):
    pass


class CommitResult(BaseModel):
    summary: str
    log_entry: str | None = None


class JujutsuHistory:
    def __init__(self, repo_dir: Path, jj_bin: str = "jj") -> None:
        self.repo_dir = repo_dir
        self.jj_bin = jj_bin

    def ensure_workspace(self) -> None:
        if not (self.repo_dir / ".jj").exists():
            raise JujutsuError(
                f"{self.repo_dir} is not a Jujutsu workspace. "
                "Initialize the vault with jj before starting the app."
            )

    def _run(self, *args: str, timeout_s: int = 60) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            [self.jj_bin, *args],
            cwd=str(self.repo_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
        if cp.returncode != 0:
            raise JujutsuError(cp.stderr.strip() or cp.stdout.strip() or "jj command failed")
        return cp

    def commit_current_change(self, message: str) -> CommitResult:
        """
        Finish the current working-copy change and start a new empty one.
        This is the key v0 durability boundary.
        """
        self._run("commit", "-m", message, timeout_s=120)
        log_entry = self._run("log", "-r", "@-", "--no-graph").stdout.strip()
        return CommitResult(summary=message, log_entry=log_entry or None)

    def undo_last_change(self) -> str:
        self._run("undo", timeout_s=120)
        return "jj undo completed"

    def history_for_file(self, file_relpath: str, limit: int = 10) -> list[str]:
        cp = self._run(
            "log",
            file_relpath,
            "--limit",
            str(limit),
            "--no-graph",
        )
        return [line for line in cp.stdout.splitlines() if line.strip()]

    def diff_for_file(self, file_relpath: str) -> str:
        cp = self._run("diff", file_relpath, timeout_s=120)
        return cp.stdout
```

### Important behavioral note

This wrapper is intentionally simple because the runtime is intentionally simple:

- all successful app mutations end in **one** `jj commit -m ...`
- default worker concurrency is **one**
- undo in v0 is **last app change**, implemented with `jj undo`

That is a good simplified baseline.

---

## 10. Kiln rebuild wrapper

### `obsidian_ops/rebuild.py`

```python
from __future__ import annotations

import subprocess
from pathlib import Path


class RebuildError(RuntimeError):
    pass


def run_kiln_generate(kiln_bin: str, vault_dir: Path, site_dir: Path, timeout_s: int = 180) -> None:
    cp = subprocess.run(
        [
            kiln_bin,
            "generate",
            "--input",
            str(vault_dir),
            "--output",
            str(site_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_s,
    )
    if cp.returncode != 0:
        raise RebuildError(cp.stderr.strip() or cp.stdout.strip() or "kiln generate failed")
```

Keep rebuilds coarse in v0.

---

## 11. Tool surface

The agent gets a very small tool surface.

### `obsidian_ops/tools.py`

```python
from __future__ import annotations

from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from obsidian_ops.fs_atomic import atomic_write_text, read_text
from obsidian_ops.history_jj import JujutsuHistory
from obsidian_ops.locks import PathLocks


class ReadFileArgs(BaseModel):
    path: str


class WriteFileArgs(BaseModel):
    path: str
    content: str


class ListFilesArgs(BaseModel):
    glob: str = Field(default="**/*.md")


class SearchFilesArgs(BaseModel):
    query: str
    glob: str = Field(default="**/*.md")
    limit: int = Field(default=12)


class FetchUrlArgs(BaseModel):
    url: str


class GetHistoryArgs(BaseModel):
    path: str
    limit: int = Field(default=10)


class ToolRuntime:
    def __init__(
        self,
        vault_dir: Path,
        locks: PathLocks,
        history: JujutsuHistory,
        max_search_results: int,
    ) -> None:
        self.vault_dir = vault_dir
        self.locks = locks
        self.history = history
        self.max_search_results = max_search_results
        self.changed_files: set[str] = set()
        self.created_files: set[str] = set()

    def _resolve(self, relpath: str) -> Path:
        full = (self.vault_dir / relpath).resolve()
        if self.vault_dir.resolve() not in full.parents and full != self.vault_dir.resolve():
            raise ValueError(f"Path escapes vault: {relpath}")
        return full

    async def read_file(self, args: ReadFileArgs) -> str:
        return read_text(self._resolve(args.path))

    async def write_file(self, args: WriteFileArgs) -> str:
        path = self._resolve(args.path)
        existed = path.exists()
        async with self.locks.hold(path):
            atomic_write_text(path, args.content)
        if existed:
            self.changed_files.add(args.path)
        else:
            self.created_files.add(args.path)
        return f"Wrote {args.path}"

    async def list_files(self, args: ListFilesArgs) -> list[str]:
        return sorted(
            str(p.relative_to(self.vault_dir))
            for p in self.vault_dir.glob(args.glob)
            if p.is_file()
        )

    async def search_files(self, args: SearchFilesArgs) -> list[dict]:
        limit = min(args.limit, self.max_search_results)
        results: list[dict] = []
        needle = args.query.lower()
        for p in self.vault_dir.glob(args.glob):
            if not p.is_file():
                continue
            text = read_text(p)
            lowered = text.lower()
            idx = lowered.find(needle)
            if idx == -1:
                continue
            start = max(0, idx - 120)
            end = min(len(text), idx + len(args.query) + 120)
            results.append(
                {
                    "path": str(p.relative_to(self.vault_dir)),
                    "snippet": text[start:end],
                }
            )
            if len(results) >= limit:
                break
        return results

    async def fetch_url(self, args: FetchUrlArgs) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(args.url)
            response.raise_for_status()
            text = response.text
        return text[:120000]

    async def get_file_history(self, args: GetHistoryArgs) -> list[str]:
        return self.history.history_for_file(args.path, limit=args.limit)


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict


def tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="read_file",
            description="Read a markdown file from the vault.",
            parameters=ReadFileArgs.model_json_schema(),
        ),
        ToolSpec(
            name="write_file",
            description="Write markdown content to a vault file.",
            parameters=WriteFileArgs.model_json_schema(),
        ),
        ToolSpec(
            name="list_files",
            description="List markdown files in the vault.",
            parameters=ListFilesArgs.model_json_schema(),
        ),
        ToolSpec(
            name="search_files",
            description="Search markdown files for relevant context.",
            parameters=SearchFilesArgs.model_json_schema(),
        ),
        ToolSpec(
            name="fetch_url",
            description="Fetch the contents of a URL for summarization or note creation.",
            parameters=FetchUrlArgs.model_json_schema(),
        ),
        ToolSpec(
            name="get_file_history",
            description="Return recent history lines for a file.",
            parameters=GetHistoryArgs.model_json_schema(),
        ),
    ]


def openai_tools_payload() -> list[dict]:
    out: list[dict] = []
    for spec in tool_specs():
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return out
```

---

## 12. Agent loop

This is the canonical heart of the app.

Use one general system prompt. Do not route through structured command handlers.

### `obsidian_ops/agent.py`

```python
from __future__ import annotations

import json
from typing import Awaitable, Callable

from openai import AsyncOpenAI

from obsidian_ops.models import JobRequest, JobSummary, ProgressEvent
from obsidian_ops.tools import (
    FetchUrlArgs,
    GetHistoryArgs,
    ListFilesArgs,
    ReadFileArgs,
    SearchFilesArgs,
    ToolRuntime,
    WriteFileArgs,
    openai_tools_payload,
)


ToolEmitter = Callable[[ProgressEvent], Awaitable[None]]


SYSTEM_PROMPT = """\
You are an assistant that helps manage and improve notes in an Obsidian vault.

Rules:
- Preserve YAML frontmatter unless explicitly asked to change it.
- Preserve wikilinks unless explicitly asked to change them.
- Prefer minimal edits when possible.
- Do not delete content unless the user clearly intends that outcome.
- When creating a new file, return clean markdown with a useful title and headings.
- Summarize what you changed at the end.
"""


async def run_agent_job(
    *,
    client: AsyncOpenAI,
    model: str,
    request: JobRequest,
    current_file_path: str,
    tools: ToolRuntime,
    emit: ToolEmitter,
    max_tool_iterations: int,
) -> JobSummary:
    await emit(
        ProgressEvent(
            type="status",
            message="starting agent",
            payload={"current_file_path": current_file_path},
        )
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Current file path: {current_file_path}\n\n"
                f"User instruction: {request.instruction}"
            ),
        },
    ]

    async def call_tool(name: str, args_json: str):
        raw = json.loads(args_json or "{}")
        await emit(ProgressEvent(type="tool", message=f"calling {name}", payload=raw))

        if name == "read_file":
            return await tools.read_file(ReadFileArgs(**raw))
        if name == "write_file":
            return await tools.write_file(WriteFileArgs(**raw))
        if name == "list_files":
            return await tools.list_files(ListFilesArgs(**raw))
        if name == "search_files":
            return await tools.search_files(SearchFilesArgs(**raw))
        if name == "fetch_url":
            return await tools.fetch_url(FetchUrlArgs(**raw))
        if name == "get_file_history":
            return await tools.get_file_history(GetHistoryArgs(**raw))
        raise RuntimeError(f"unknown tool: {name}")

    for _ in range(max_tool_iterations):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools_payload(),
            tool_choice="auto",
        )

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                result = await call_tool(tc.function.name, tc.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            continue

        final_text = (message.content or "").strip()
        await emit(
            ProgressEvent(
                type="result",
                message="agent finished",
                payload={"summary": final_text},
            )
        )
        return JobSummary(
            summary=final_text,
            changed_files=sorted(tools.changed_files),
            created_files=sorted(tools.created_files),
        )

    raise RuntimeError("agent exceeded maximum tool iterations")
```

### Notes

- The agent loop is generic.
- The tools are generic.
- The user instruction is generic.
- There is no command taxonomy hiding underneath.

That is the point.

---

## 13. In-memory queue with SSE subscribers

### Queue design

The queue should hold:

- job records
- a runner callable
- a set of subscriber queues for SSE

This lets the worker publish progress updates that are immediately streamable to the browser.

### `obsidian_ops/queue.py`

```python
from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from obsidian_ops.models import JobRecord, JobRequest, JobState, ProgressEvent


JobRunner = Callable[[Callable[[ProgressEvent], Awaitable[None]]], Awaitable[dict]]


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._jobs: dict[str, JobRecord] = {}
        self._runners: dict[str, JobRunner] = {}
        self._subscribers: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}
        self._guard = asyncio.Lock()

    async def create_job(self, request: JobRequest, runner: JobRunner) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            state=JobState.queued,
            request=request,
            created_at=datetime.now(timezone.utc),
        )
        async with self._guard:
            self._jobs[job_id] = record
            self._runners[job_id] = runner
            self._subscribers[job_id] = []
        await self._queue.put(job_id)
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        return list(self._jobs.values())

    async def subscribe(self, job_id: str) -> asyncio.Queue[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        async with self._guard:
            if job_id not in self._subscribers:
                raise KeyError(job_id)
            self._subscribers[job_id].append(q)
        return q

    async def publish(self, job_id: str, event: ProgressEvent) -> None:
        async with self._guard:
            subscribers = list(self._subscribers.get(job_id, []))
        for q in subscribers:
            await q.put(event)

    async def worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            record = self._jobs[job_id]
            runner = self._runners[job_id]

            record.state = JobState.running
            record.started_at = datetime.now(timezone.utc)
            await self.publish(job_id, ProgressEvent(type="status", message="job started"))

            try:
                result = await runner(lambda event: self.publish(job_id, event))
                record.state = JobState.succeeded
                record.result = result
                await self.publish(
                    job_id,
                    ProgressEvent(type="done", message="job succeeded", payload=result),
                )
            except Exception as exc:
                record.state = JobState.failed
                record.error = f"{type(exc).__name__}: {exc}"
                await self.publish(
                    job_id,
                    ProgressEvent(
                        type="error",
                        message=record.error,
                        payload={"traceback": traceback.format_exc()},
                    ),
                )
            finally:
                record.finished_at = datetime.now(timezone.utc)
                self._queue.task_done()
```

---

## 14. Overlay injection

The overlay is tiny:

- one FAB
- one modal
- job submission
- SSE subscription
- refresh / undo buttons

### `obsidian_ops/inject.py`

```python
from __future__ import annotations

from pathlib import Path


INJECT_MARKER = "<!-- obsidian-ops overlay -->"


def inject_overlay(site_dir: Path, css_href: str = "/ops/ops.css", js_src: str = "/ops/ops.js") -> None:
    css_tag = f'<link rel="stylesheet" href="{css_href}">'
    js_tag = f'<script defer src="{js_src}"></script>'
    marker = f"{INJECT_MARKER}\n{css_tag}\n{js_tag}\n"

    for html_file in site_dir.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        if INJECT_MARKER in text:
            continue
        if "</head>" in text:
            text = text.replace("</head>", marker + "</head>", 1)
        elif "</body>" in text:
            text = text.replace("</body>", marker + "</body>", 1)
        html_file.write_text(text, encoding="utf-8")
```

---

## 15. Browser overlay

### `obsidian_ops/static/ops.css`

```css
#ops-fab {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 99999;
  padding: 10px 12px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.78);
  color: white;
  font: 14px/1.2 system-ui, sans-serif;
  cursor: pointer;
  user-select: none;
}

#ops-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99998;
  background: rgba(0, 0, 0, 0.35);
  display: none;
}

#ops-modal {
  position: fixed;
  top: 10%;
  left: 50%;
  transform: translateX(-50%);
  width: min(760px, 92vw);
  z-index: 99999;
  background: #fff;
  color: #111;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.25);
  padding: 16px;
  display: none;
}

#ops-modal textarea {
  width: 100%;
  min-height: 110px;
}

#ops-progress {
  max-height: 240px;
  overflow: auto;
  background: #f6f6f6;
  padding: 8px;
  border-radius: 6px;
  white-space: pre-wrap;
}
```

### `obsidian_ops/static/ops.js`

```javascript
(function () {
  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;
      else node.setAttribute(k, v);
    });
    children.forEach((c) => node.appendChild(c));
    return node;
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  }

  function ensureUI() {
    if (document.getElementById("ops-fab")) return;

    const backdrop = el("div", { id: "ops-backdrop" });
    const modal = el("div", { id: "ops-modal" });
    const fab = el("div", { id: "ops-fab", text: "Ops" });

    backdrop.onclick = () => {
      backdrop.style.display = "none";
      modal.style.display = "none";
    };

    fab.onclick = openModal;

    document.body.appendChild(backdrop);
    document.body.appendChild(modal);
    document.body.appendChild(fab);
  }

  function openModal() {
    const backdrop = document.getElementById("ops-backdrop");
    const modal = document.getElementById("ops-modal");
    modal.innerHTML = "";

    const title = el("h3", { text: "Obsidian Ops" });
    const textarea = el("textarea");
    textarea.placeholder = "What would you like to do?";

    const context = el("p", {
      text: `Current page: ${location.pathname}`,
    });

    const progress = el("div", { id: "ops-progress" });
    const submit = el("button", { type: "button", text: "Submit" });
    const refresh = el("button", { type: "button", text: "Refresh" });
    refresh.style.marginLeft = "8px";
    refresh.onclick = () => location.reload();

    const undo = el("button", { type: "button", text: "Undo last change" });
    undo.style.marginLeft = "8px";
    undo.onclick = async () => {
      progress.textContent += "\nundo requested...";
      const res = await postJSON("/api/undo", {});
      streamJob(res.job_id, progress);
    };

    submit.onclick = async () => {
      progress.textContent = "submitting job...\n";
      const job = await postJSON("/api/jobs", {
        instruction: textarea.value,
        current_url_path: location.pathname,
      });
      streamJob(job.job_id, progress);
    };

    modal.appendChild(title);
    modal.appendChild(context);
    modal.appendChild(textarea);
    modal.appendChild(el("div", {}, [submit, refresh, undo]));
    modal.appendChild(progress);

    backdrop.style.display = "block";
    modal.style.display = "block";
  }

  function streamJob(jobId, progressEl) {
    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    es.onmessage = (event) => {
      progressEl.textContent += event.data + "\n";
    };
    es.addEventListener("done", (event) => {
      progressEl.textContent += `DONE: ${event.data}\n`;
      es.close();
    });
    es.addEventListener("error", (event) => {
      progressEl.textContent += `ERROR: ${event.data}\n`;
    });
  }

  ensureUI();
  document.body.addEventListener("htmx:afterSwap", ensureUI);
})();
```

### Why this JS is correct for the simplified product

- no selection toolbar
- no command buttons
- no command registry leaking into the UI
- one text box
- one progress surface
- one undo affordance

That is exactly what we want.

---

## 16. FastAPI app

### `obsidian_ops/app.py`

```python
from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from obsidian_ops.agent import run_agent_job
from obsidian_ops.config import Settings
from obsidian_ops.history_jj import JujutsuHistory
from obsidian_ops.inject import inject_overlay
from obsidian_ops.locks import PathLocks
from obsidian_ops.models import JobRequest, ProgressEvent
from obsidian_ops.page_context import infer_markdown_path_from_url
from obsidian_ops.queue import InMemoryJobQueue
from obsidian_ops.rebuild import run_kiln_generate
from obsidian_ops.tools import ToolRuntime


def sse_frame(data: str, event: str | None = None) -> bytes:
    parts = []
    if event:
        parts.append(f"event: {event}")
    for line in data.splitlines() or [""]:
        parts.append(f"data: {line}")
    parts.append("")
    return ("\n".join(parts) + "\n").encode("utf-8")


def build_app(settings: Settings) -> FastAPI:
    queue = InMemoryJobQueue()
    locks = PathLocks()
    history = JujutsuHistory(settings.vault_dir, settings.jj_bin)
    llm = AsyncOpenAI(
        api_key=settings.vllm_api_key,
        base_url=settings.vllm_base_url,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        history.ensure_workspace()
        settings.site_dir.mkdir(parents=True, exist_ok=True)

        # Initial render + injection
        run_kiln_generate(settings.kiln_bin, settings.vault_dir, settings.site_dir, settings.kiln_timeout_s)
        inject_overlay(settings.site_dir)

        workers = [
            asyncio.create_task(queue.worker_loop())
            for _ in range(max(1, settings.worker_concurrency))
        ]
        try:
            yield
        finally:
            for worker in workers:
                worker.cancel()

    app = FastAPI(lifespan=lifespan)

    ops_static_dir = Path(__file__).parent / "static"
    app.mount("/ops", StaticFiles(directory=str(ops_static_dir)), name="ops")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/jobs")
    async def list_jobs() -> list[dict]:
        return [job.model_dump(mode="json") for job in queue.list()]

    @app.post("/api/jobs")
    async def create_job(request: JobRequest) -> dict:
        current_file_path = request.current_file_path or infer_markdown_path_from_url(
            request.current_url_path,
            settings.vault_dir,
        )

        async def runner(emit):
            tool_runtime = ToolRuntime(
                vault_dir=settings.vault_dir,
                locks=locks,
                history=history,
                max_search_results=settings.max_search_results,
            )

            summary = await run_agent_job(
                client=llm,
                model=settings.vllm_model,
                request=request,
                current_file_path=current_file_path,
                tools=tool_runtime,
                emit=emit,
                max_tool_iterations=settings.max_tool_iterations,
            )

            touched = summary.changed_files + summary.created_files
            if touched:
                await emit(ProgressEvent(type="status", message="recording history"))
                commit = history.commit_current_change(f"ops: {request.instruction[:80]}")
                summary.history_hint = commit.log_entry

                await emit(ProgressEvent(type="status", message="rebuilding site"))
                run_kiln_generate(settings.kiln_bin, settings.vault_dir, settings.site_dir, settings.kiln_timeout_s)
                inject_overlay(settings.site_dir)

            return summary.model_dump()

        job_id = await queue.create_job(request, runner)
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}/stream")
    async def stream_job(job_id: str):
        job = queue.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        async def event_iter():
            sub = await queue.subscribe(job_id)

            # If the job has already finished before subscription, emit a summary immediately.
            existing = queue.get(job_id)
            if existing and existing.state in {"succeeded", "failed"}:
                event = {
                    "state": existing.state,
                    "result": existing.result,
                    "error": existing.error,
                }
                yield sse_frame(json.dumps(event), event="done")
                return

            while True:
                event = await sub.get()
                payload = event.model_dump(mode="json")
                event_name = event.type if event.type in {"done", "error"} else None
                yield sse_frame(json.dumps(payload), event=event_name)
                if event.type == "done":
                    return

        return StreamingResponse(event_iter(), media_type="text/event-stream")

    @app.get("/api/history")
    async def history_for_file(path: str, limit: int = 10) -> dict:
        return {"entries": history.history_for_file(path, limit=limit)}

    @app.post("/api/undo")
    async def undo_last_change() -> dict:
        undo_request = JobRequest(
            instruction="Undo the last change",
            current_url_path="/",
            current_file_path=None,
        )

        async def runner(emit):
            await emit(ProgressEvent(type="status", message="undoing last change"))
            history.undo_last_change()
            await emit(ProgressEvent(type="status", message="rebuilding site"))
            run_kiln_generate(settings.kiln_bin, settings.vault_dir, settings.site_dir, settings.kiln_timeout_s)
            inject_overlay(settings.site_dir)
            return {"summary": "Undo completed"}

        job_id = await queue.create_job(undo_request, runner)
        return {"job_id": job_id}

    # mount the generated site last
    app.mount("/", StaticFiles(directory=str(settings.site_dir), html=True), name="site")
    return app


def create_app() -> FastAPI:
    return build_app(Settings.from_env())


app = create_app()
```

### Why this app shape is canonical

- one generic job route
- one stream route
- one undo route
- one history route
- no command-specific routes
- no database
- no durable jobs
- no selection-specific editing protocol

---

## 17. End-to-end mutation semantics

A successful mutating job follows this order:

1. Browser submits:
   - instruction
   - current URL path
2. Server resolves current markdown file path
3. Worker starts the job
4. Agent reads/searches/fetches as needed
5. Agent writes one or more markdown files
6. App finalizes the working-copy change with `jj commit -m ...`
7. App triggers `kiln generate`
8. Overlay is re-injected
9. Job emits final SSE result
10. User refreshes or undoes

That is the core system.

---

## 18. Testing

### Unit tests

Test these first:

- atomic write round-trips
- page path inference
- Jujutsu workspace detection
- queue state transitions
- overlay injection

### `tests/test_atomic.py`

```python
from pathlib import Path
from obsidian_ops.fs_atomic import atomic_write_text, read_text


def test_atomic_write_roundtrip(tmp_path: Path):
    p = tmp_path / "a.md"
    atomic_write_text(p, "# one")
    assert read_text(p) == "# one"
    atomic_write_text(p, "# two")
    assert read_text(p) == "# two"
```

### `tests/test_page_context.py`

```python
from pathlib import Path
from obsidian_ops.page_context import infer_markdown_path_from_url


def test_infer_from_folder_url(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "alpha.md").write_text("hi", encoding="utf-8")
    assert infer_markdown_path_from_url("/notes/alpha/", tmp_path) == "notes/alpha.md"
```

### `tests/test_queue.py`

```python
import asyncio
import pytest

from obsidian_ops.models import JobRequest, JobState, ProgressEvent
from obsidian_ops.queue import InMemoryJobQueue


@pytest.mark.asyncio
async def test_queue_runs_job():
    q = InMemoryJobQueue()

    async def runner(emit):
        await emit(ProgressEvent(type="status", message="hello"))
        return {"ok": True}

    job_id = await q.create_job(
        JobRequest(instruction="x", current_url_path="/"),
        runner,
    )

    worker = asyncio.create_task(q.worker_loop())
    await asyncio.sleep(0.2)

    job = q.get(job_id)
    assert job is not None
    assert job.state == JobState.succeeded
    worker.cancel()
```

### Jujutsu integration test strategy

Use a temp directory with a pre-initialized `.jj` workspace.

Test:

- edit a file
- call `commit_current_change(...)`
- verify `history_for_file(...)` is non-empty
- call `undo_last_change()`
- verify file contents are restored

### API integration test strategy

Mock:

- `run_agent_job`
- `run_kiln_generate`
- `inject_overlay`

Assert:

- `POST /api/jobs` returns a job id
- SSE emits status events then done
- `POST /api/undo` schedules an undo job
- `GET /api/history` returns entries

---

## 19. Manual acceptance checklist

Use this checklist with a real vault.

### Boot

- app starts
- initial Kiln build completes
- overlay appears on rendered pages

### Generic job

- open any rendered page
- click FAB
- type: `clean up this note but preserve links`
- submit
- see SSE progress in modal
- refresh
- content changed as expected

### Search/create job

- type: `find related notes and create a short Related section`
- verify the agent searches the vault and writes markdown
- verify rebuild completes

### URL job

- type: `fetch https://example.com and create a source note in Sources`
- verify the agent calls `fetch_url`
- verify a new note is created
- verify rebuild completes

### Undo

- click **Undo last change**
- see SSE progress
- refresh
- previous state returns

### History

- call `/api/history?path=<file>`
- verify recent history lines are returned

If those flows work, the simplified product loop works.

---

## 20. Operational notes

### Why one worker is a good default

One worker drastically simplifies:

- Jujutsu undo expectations
- rebuild sequencing
- user mental model
- debugging

You can raise concurrency later, but v0 should start with **1**.

### Why one Jujutsu mutation per job matters

If a job writes files and then performs exactly one `jj commit -m ...`, then:

- the durable history boundary is clean
- undo semantics are predictable
- the user can trust “undo last change”

### Why coarse rebuilds are fine

You want the simplest system that can work reliably. Full `kiln generate` after successful writes is acceptable in v0.

---

## 21. Do not reintroduce these

Do **not** reintroduce any of the following unless scope explicitly changes:

- `/api/rewrite`
- `/api/organize_note`
- `/api/save_url`
- selection capture/resolution as core runtime behavior
- polling as the primary progress transport
- Git-based undo as the product story
- a database
- a command registry
- per-command UI

If you do, you are drifting away from the canonical product.

---

## 22. Recommended implementation order for the intern

Build in this order:

1. `config.py`
2. `models.py`
3. `locks.py`
4. `fs_atomic.py`
5. `history_jj.py`
6. `rebuild.py`
7. `page_context.py`
8. `queue.py`
9. `inject.py`
10. static `ops.css`
11. static `ops.js`
12. `tools.py`
13. `agent.py`
14. `app.py`
15. tests
16. manual acceptance pass with a real vault

That order keeps the risk low and the feedback loop fast.

---

## 23. Final recommendation

Implement the simplified product exactly like this:

- one modal
- one generic job API
- one SSE stream
- one tool-using agent loop
- one in-memory queue
- one Jujutsu durability model
- one coarse rebuild step

That is the implementation target.

Any move toward structured public commands, selection tooling, or parallel durability systems is a move away from the intended product.
