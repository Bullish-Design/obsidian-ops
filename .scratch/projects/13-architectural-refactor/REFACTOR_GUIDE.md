# obsidian-ops Refactor: Step-by-Step Implementation Guide

## Preface: Design Decisions

The spec review (`CONCEPT_SPEC_REVIEW.md`) identified several ambiguities and contradictions.
This guide resolves them with binding decisions for implementation:

| # | Issue | Decision |
|---|-------|----------|
| 1 | Frontmatter update: shallow vs deep merge | **Shallow merge** at top level. Remove dot-notation / nested-path language from docstrings. Nested dicts are replaced wholesale. |
| 2 | YAML preservation (comments, style) | **Best-effort data preservation only.** Body preserved byte-for-byte. YAML key order preserved where pyyaml allows. Comments and flow-style may be lost. No round-trip YAML library in v1. |
| 3 | "Wikilinks first-class" claim | **Remove from v1 principles.** Reword to: "Obsidian-aware for frontmatter, headings, and block references." Wikilink analysis is a post-v1 extra. |
| 4 | Heading boundary wording | **"Next heading with level <= current level"** (i.e., same or fewer `#` chars). |
| 5 | Lock composition / self-deadlock | **Public methods acquire lock; internal `_unsafe_*` helpers do not.** No public mutating method may call another public mutating method. |
| 6 | Path sandbox TOCTOU | **Accept residual TOCTOU risk for v1.** Document that the sandbox targets accidental escape, not adversarial real-time symlink races. Use `os.path.realpath` validation at call time. |
| 7 | Block ref scope | **v1 supports simple paragraphs and single-line list items only.** Multi-line list items, blockquotes, callouts, code fences, and tables are out of scope. Document this constraint. |
| 8 | `search_files` on large files | **Skip files exceeding `MAX_READ_SIZE`.** Do not read them into memory. |
| 9 | `list_files` glob semantics | **Full relative-path glob matching** (e.g., `Projects/*.md` works). Rename docstring language from "filename glob" to "path glob." |
| 10 | HTTP heading/block params | **Use JSON request body** for heading and block_id parameters on all content-patch endpoints. |
| 11 | VCS HTTP error mapping | **Precondition failures (missing binary, no workspace) → 424 Failed Dependency.** Execution failures → 500. |

---

## Step 0: Project Scaffold & Dependencies

### Work

1. Update `pyproject.toml`:
   - Set `requires-python = ">=3.12"`.
   - Replace `dependencies` with `["pyyaml>=6.0"]` only.
   - Add `[project.optional-dependencies] server = ["fastapi>=0.115.0", "uvicorn>=0.34.0"]`.
   - Keep `dev` extras: `pytest>=8.0`, `pytest-cov>=5.0`, `ruff>=0.5.0`.
   - Remove `ops-demo` script entry, `pytest-asyncio`, `pydantic*`, `typer`, `openai`, `httpx`, `ty`.
   - Add `obsidian-ops-server = "obsidian_ops.server:main"` under `[project.scripts]` (optional, for later).
2. Create `src/obsidian_ops/__init__.py` with placeholder docstring and version.
3. Create `tests/conftest.py` with a `tmp_vault` fixture (see spec §13.1 for fixture layout).
4. Run `devenv shell -- uv sync --extra dev` to lock deps.
5. Run `devenv shell -- pytest tests/` — should collect 0 tests and exit 0.

### Verification

```
devenv shell -- uv sync --extra dev        # clean install, no errors
devenv shell -- pytest tests/ -v           # 0 tests collected, exit 0
devenv shell -- ruff check src/ tests/     # no lint errors
```

---

## Step 1: Exception Hierarchy (`errors.py`)

### Work

Create `src/obsidian_ops/errors.py` with exactly:

```python
class VaultError(Exception): ...
class PathError(VaultError): ...
class FileTooLargeError(VaultError): ...
class BusyError(VaultError): ...
class FrontmatterError(VaultError): ...
class ContentPatchError(VaultError): ...
class VCSError(VaultError): ...
```

Export all from `__init__.py`.

### Verification

```python
# In a quick test or REPL:
from obsidian_ops import PathError, VaultError
assert issubclass(PathError, VaultError)
assert issubclass(PathError, Exception)
```

No dedicated test file needed yet — these are trivially correct.
Confirm with `ruff check src/`.

---

## Step 2: Mutation Lock (`lock.py`)

### Work

Create `src/obsidian_ops/lock.py`:

- `MutationLock` class wrapping `threading.Lock`.
- `acquire()`: non-blocking (`lock.acquire(blocking=False)`). Raises `BusyError` if held.
- `release()`: releases the lock.
- Context-manager protocol (`__enter__` / `__exit__`) for safe release on exceptions.
- `is_held` property for `is_busy()` inspection.

### Tests — `tests/test_lock.py`

| Test | What it proves |
|------|---------------|
| `test_acquire_release` | Lock can be acquired and released normally. |
| `test_context_manager` | Lock released after `with` block exits. |
| `test_double_acquire_raises_busy` | Second acquire on same lock raises `BusyError`. |
| `test_release_on_exception` | Lock released even when body raises. |
| `test_is_held_reflects_state` | `is_held` is `True` inside context, `False` outside. |
| `test_concurrent_threads` | Spawn thread holding lock; main thread gets `BusyError`. Release in thread; main can then acquire. |

### Verification

```
devenv shell -- pytest tests/test_lock.py -v   # all pass
```

---

## Step 3: Path Sandbox (`sandbox.py`)

### Work

Create `src/obsidian_ops/sandbox.py`:

- `validate_path(root: Path, user_path: str) -> Path`
  - Returns the resolved absolute path within the vault.
  - Raises `PathError` for violations.
- Implementation per spec §5.1:
  1. Reject empty string.
  2. `os.path.normpath` to clean.
  3. Reject if starts with `/` or drive letter.
  4. Reject if starts with `..`.
  5. Join with root.
  6. If path exists: `os.path.realpath` and verify prefix match against resolved root.
  7. If path does not exist: validate parent directory instead (for write operations).
- Vault root resolved via `os.path.realpath` once and cached (done in `Vault.__init__`).

### Tests — `tests/test_sandbox.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_valid_simple` | `"note.md"` | Resolves to `{root}/note.md` |
| `test_valid_nested` | `"Projects/Alpha.md"` | Resolves correctly |
| `test_valid_spaces` | `"My Notes/file name.md"` | Valid |
| `test_valid_unicode` | `"日本語/ノート.md"` | Valid |
| `test_valid_normalization` | `"Projects/../Alpha.md"` | Resolves to `{root}/Alpha.md` |
| `test_reject_absolute` | `"/etc/passwd"` | `PathError` |
| `test_reject_traversal` | `"../../secrets.txt"` | `PathError` |
| `test_reject_sneaky_traversal` | `"a/b/../../../etc/passwd"` | `PathError` |
| `test_reject_empty` | `""` | `PathError` |
| `test_reject_symlink_escape` | Symlink → `/tmp` | `PathError` |
| `test_new_file_validates_parent` | Non-existent file in valid dir | Valid |
| `test_new_file_in_nonexistent_parent` | Parent doesn't exist but is within root | Valid (parent creation is caller's job) |

### Verification

```
devenv shell -- pytest tests/test_sandbox.py -v   # all pass
```

---

## Step 4: Search & Listing Utilities (`search.py`)

### Work

Create `src/obsidian_ops/search.py`:

- `walk_vault(root: Path, pattern: str, max_results: int) -> list[str]`
  - Walks the vault directory tree.
  - Matches full relative path against `pattern` using `fnmatch` or `pathlib.match`.
  - Skips directories/files starting with `.` or `_hidden_`.
  - Returns sorted list of vault-relative path strings.
  - Caps at `max_results`.
- `search_content(root: Path, query: str, files: list[str], max_results: int) -> list[SearchResult]`
  - Case-insensitive substring search.
  - Skips files exceeding `MAX_READ_SIZE`.
  - Returns `SearchResult(path, snippet)` with ~160-char context around first match.
  - Caps at `max_results`.

Define `SearchResult` dataclass here (or in a types module), export from `__init__.py`.

### Tests — `tests/test_search.py`

| Test | What it proves |
|------|---------------|
| `test_walk_default_glob` | `*.md` returns all markdown files. |
| `test_walk_subdirectory_glob` | `Projects/*.md` returns only files in Projects/. |
| `test_walk_skips_dotfiles` | `.hidden/` contents excluded. |
| `test_walk_skips_hidden_prefix` | `_hidden_dir/` contents excluded. |
| `test_walk_max_results` | Caps output length. |
| `test_walk_sorted` | Results are alphabetically sorted. |
| `test_search_finds_match` | Returns file with matching content. |
| `test_search_case_insensitive` | Matches regardless of case. |
| `test_search_snippet_context` | Snippet is ~160 chars around match. |
| `test_search_respects_glob` | Only searches files matching the glob filter. |
| `test_search_max_results` | Caps results. |
| `test_search_skips_large_files` | Files > 512KB silently skipped. |

### Verification

```
devenv shell -- pytest tests/test_search.py -v   # all pass
```

---

## Step 5: Vault Core — File Operations (`vault.py`)

### Work

Create `src/obsidian_ops/vault.py` with the `Vault` class:

- `__init__(self, root, *, jj_bin="jj", jj_timeout=120)`:
  - Validate root exists and is a directory.
  - Resolve and cache root via `os.path.realpath`.
  - Create `MutationLock` instance.
  - Store jj config for later.
- `read_file(self, path) -> str`: validate path, check size, read UTF-8.
- `write_file(self, path, content)`: acquire lock, validate path, mkdir parents, write.
- `delete_file(self, path)`: acquire lock, validate path, delete.
- `list_files(self, pattern, *, max_results)`: delegate to `walk_vault`.
- `search_files(self, query, *, glob, max_results)`: delegate to `search_content`.
- `is_busy(self) -> bool`: check lock state.

Constants: `MAX_READ_SIZE = 512 * 1024`, `MAX_LIST_RESULTS = 200`, `MAX_SEARCH_RESULTS = 50`, `SNIPPET_CONTEXT = 80`.

Export `Vault` from `__init__.py`.

### Tests — `tests/test_vault.py`

Use `tmp_vault` fixture from `conftest.py`.

| Test | What it proves |
|------|---------------|
| `test_init_valid_root` | Vault instantiates with valid directory. |
| `test_init_invalid_root` | `VaultError` for non-existent path. |
| `test_init_file_not_dir` | `VaultError` when root is a file. |
| `test_read_file` | Returns correct UTF-8 content. |
| `test_read_file_not_found` | Raises `FileNotFoundError`. |
| `test_read_file_too_large` | Raises `FileTooLargeError` for >512KB file. |
| `test_read_file_path_escape` | Raises `PathError` for `../` path. |
| `test_write_file_new` | Creates file and parent directories. |
| `test_write_file_overwrite` | Overwrites existing file. |
| `test_write_file_path_escape` | Raises `PathError`. |
| `test_delete_file` | Removes file. |
| `test_delete_file_not_found` | Raises `FileNotFoundError`. |
| `test_list_files_default` | Returns `.md` files. |
| `test_list_files_glob_pattern` | Respects custom glob. |
| `test_list_files_skips_hidden` | Dotfiles and `_hidden_` excluded. |
| `test_search_files_basic` | Finds matching content. |
| `test_is_busy` | Returns `False` normally, `True` during write. |

### Verification

```
devenv shell -- pytest tests/test_vault.py tests/test_lock.py tests/test_sandbox.py tests/test_search.py -v
# All pass — full core validated
```

---

## Step 6: Frontmatter (`frontmatter.py`)

### Work

Create `src/obsidian_ops/frontmatter.py`:

- `parse_frontmatter(text: str) -> tuple[dict | None, str]`
  - Splits text into (frontmatter_dict, body_string).
  - Returns `(None, full_text)` if no frontmatter block found.
  - Raises `FrontmatterError` for malformed YAML.
  - Handles optional BOM/leading whitespace before opening `---`.
- `serialize_frontmatter(data: dict, body: str) -> str`
  - Produces `---\n{yaml_dump}\n---\n{body}`.
  - Uses `pyyaml` `dump` with `default_flow_style=False`, `allow_unicode=True`, `sort_keys=False`.

Add `Vault` methods:

- `get_frontmatter(self, path)`: read file → `parse_frontmatter` → return dict or None.
- `set_frontmatter(self, path, data)`: read → parse → replace dict → serialize → write. Lock-acquiring.
- `update_frontmatter(self, path, updates)`: read → parse → shallow merge (`existing.update(updates)`) → serialize → write. Lock-acquiring. Creates frontmatter if none exists.
- `delete_frontmatter_field(self, path, field)`: read → parse → `pop(field, None)` → serialize → write. No-op if field absent. Lock-acquiring.

All mutating methods use `_unsafe_write_file` internally (no nested lock acquisition).

### Tests — `tests/test_frontmatter.py`

| Test | What it proves |
|------|---------------|
| `test_parse_valid` | Correctly extracts dict and body. |
| `test_parse_no_frontmatter` | Returns `(None, full_text)`. |
| `test_parse_malformed_yaml` | Raises `FrontmatterError`. |
| `test_parse_preserves_body` | Body content is byte-for-byte identical. |
| `test_parse_with_bom` | Handles BOM before `---`. |
| `test_serialize_roundtrip` | `serialize(parse(text))` preserves data semantics. |
| `test_get_frontmatter` | Returns dict via Vault method. |
| `test_get_frontmatter_none` | Returns None for file without frontmatter. |
| `test_set_frontmatter` | Replaces entire frontmatter, preserves body. |
| `test_set_frontmatter_no_existing` | Prepends frontmatter block. |
| `test_update_frontmatter_merge` | Only specified fields change. |
| `test_update_frontmatter_preserves_unmentioned` | Existing fields untouched. |
| `test_update_frontmatter_shallow` | Nested dict is replaced wholesale, not deep-merged. |
| `test_update_frontmatter_creates_new` | Creates frontmatter if file has none. |
| `test_delete_frontmatter_field` | Removes the specified field. |
| `test_delete_frontmatter_field_nonexistent` | No-op, no error. |
| `test_body_preserved_after_set` | Body identical before/after frontmatter change. |
| `test_body_preserved_after_update` | Body identical before/after frontmatter change. |

### Verification

```
devenv shell -- pytest tests/test_frontmatter.py -v   # all pass
devenv shell -- pytest tests/ -v                       # full suite still green
```

---

## Step 7: Content Patching (`content.py`)

### Work

Create `src/obsidian_ops/content.py`:

- `find_heading(text: str, heading: str) -> tuple[int, int] | None`
  - Returns `(start, end)` character offsets of the content under the heading.
  - Start = character after the heading line (including its newline).
  - End = character before the next heading with level <= current, or EOF.
  - Returns `None` if heading not found.
  - Matching: exact match on heading line after stripping trailing whitespace.
  - First match wins if duplicates exist.
- `find_block(text: str, block_id: str) -> tuple[int, int] | None`
  - Finds the paragraph or single-line list item containing `^block-id`.
  - Block boundary: from preceding blank line (or SOF) to the line containing the marker.
  - Returns `None` if not found.

Add `Vault` methods:

- `read_heading(self, path, heading)`: read → `find_heading` → slice → return or None.
- `write_heading(self, path, heading, content)`: read → find → splice or append → write. Lock-acquiring.
- `read_block(self, path, block_id)`: read → `find_block` → slice → return or None.
- `write_block(self, path, block_id, content)`: read → find → splice → write. Raises `ContentPatchError` if block not found. Lock-acquiring.

### Tests — `tests/test_content.py`

| Test | What it proves |
|------|---------------|
| `test_find_heading_h2` | Finds `## Summary` content correctly. |
| `test_find_heading_h1` | Works for top-level headings. |
| `test_find_heading_includes_subheadings` | `## Summary` includes `### Details` content. |
| `test_find_heading_stops_at_same_level` | Stops at next `##` heading. |
| `test_find_heading_stops_at_higher_level` | Stops at `#` heading. |
| `test_find_heading_at_eof` | Content extends to end of file. |
| `test_find_heading_not_found` | Returns `None`. |
| `test_find_heading_first_match` | Uses first occurrence of duplicate heading. |
| `test_write_heading_replaces` | Content between heading boundaries replaced. |
| `test_write_heading_appends` | Missing heading appended with blank line separator. |
| `test_find_block_paragraph` | Finds paragraph containing `^ref`. |
| `test_find_block_list_item` | Finds single-line list item containing `^ref`. |
| `test_find_block_not_found` | Returns `None`. |
| `test_write_block_replaces` | Replaces paragraph containing block ref. |
| `test_write_block_not_found_raises` | Raises `ContentPatchError`. |
| `test_read_heading_via_vault` | End-to-end through `Vault` class. |
| `test_write_heading_via_vault` | End-to-end through `Vault` class. |
| `test_read_block_via_vault` | End-to-end through `Vault` class. |
| `test_write_block_via_vault` | End-to-end through `Vault` class. |

### Verification

```
devenv shell -- pytest tests/test_content.py -v   # all pass
devenv shell -- pytest tests/ -v                   # full suite green
```

---

## Step 8: Version Control (`vcs.py`)

### Work

Create `src/obsidian_ops/vcs.py`:

- `JJ` class:
  - `__init__(self, cwd: Path, *, jj_bin: str = "jj", timeout: int = 120)`
  - `_run(self, *args) -> str`: runs `jj` subprocess with `cwd`, `timeout`, captures stdout+stderr. Raises `VCSError` on non-zero exit or timeout.
  - `describe(self, message: str)`: runs `jj describe -m <message>`.
  - `new(self)`: runs `jj new`.
  - `undo(self)`: runs `jj undo`.
  - `status(self) -> str`: runs `jj status`, returns stdout.

Add `Vault` methods:

- `commit(self, message)`: acquire lock → `jj.describe(message)` → `jj.new()`.
- `undo(self)`: acquire lock → `jj.undo()`.
- `vcs_status(self) -> str`: no lock → `jj.status()`.

JJ instance created lazily on first VCS call (not in `__init__`). If `jj` binary is not found, raise `VCSError` with clear message.

### Tests — `tests/test_vcs.py`

Use `unittest.mock.patch` to mock `subprocess.run` — do NOT require a real `jj` installation.

| Test | What it proves |
|------|---------------|
| `test_describe_runs_correct_command` | Calls `jj describe -m "msg"` with correct cwd. |
| `test_new_runs_correct_command` | Calls `jj new`. |
| `test_commit_runs_describe_then_new` | Both commands in correct order. |
| `test_undo_runs_correct_command` | Calls `jj undo`. |
| `test_status_returns_output` | Returns stdout string. |
| `test_nonzero_exit_raises_vcserror` | Non-zero exit → `VCSError` with stdout+stderr. |
| `test_timeout_raises_vcserror` | `TimeoutExpired` → `VCSError`. |
| `test_missing_binary_raises_vcserror` | `FileNotFoundError` → `VCSError`. |
| `test_commit_acquires_lock` | Lock held during commit. |
| `test_undo_acquires_lock` | Lock held during undo. |
| `test_status_no_lock` | `vcs_status` does not acquire lock. |

### Verification

```
devenv shell -- pytest tests/test_vcs.py -v   # all pass
devenv shell -- pytest tests/ -v               # full suite green
```

---

## Step 9: Public API & `__init__.py`

### Work

Finalize `src/obsidian_ops/__init__.py`:

```python
"""obsidian-ops: Sandboxed operations on an Obsidian vault."""

from obsidian_ops.vault import Vault
from obsidian_ops.errors import (
    VaultError,
    PathError,
    FileTooLargeError,
    BusyError,
    FrontmatterError,
    ContentPatchError,
    VCSError,
)
from obsidian_ops.search import SearchResult

__all__ = [
    "Vault",
    "SearchResult",
    "VaultError",
    "PathError",
    "FileTooLargeError",
    "BusyError",
    "FrontmatterError",
    "ContentPatchError",
    "VCSError",
]
```

### Verification

```python
# Smoke test: can import everything from the public API
from obsidian_ops import Vault, SearchResult, PathError, BusyError, VCSError
```

```
devenv shell -- pytest tests/ -v                                    # full suite green
devenv shell -- pytest tests/ --cov=obsidian_ops --cov-report=term-missing  # check coverage
devenv shell -- ruff check src/ tests/                              # clean lint
```

**Target: ≥90% line coverage on `src/obsidian_ops/` at this point.**

---

## Step 10: HTTP Server (`server.py`) — Optional

### Work

Create `src/obsidian_ops/server.py`:

- FastAPI app factory: `create_app(vault_root: str, **kwargs) -> FastAPI`.
- 1:1 endpoint mapping per spec §12.2, with these adjustments:
  - Content-patch endpoints use JSON bodies for heading/block_id (per Decision #10).
  - VCS precondition errors return 424, not 500 (per Decision #11).
- Error-handling middleware mapping exception types to HTTP status codes (spec §12.3).
- `main()` entrypoint: parse CLI args (`--vault`, `--host`, `--port`, `--jj-bin`, `--jj-timeout`), create app, run uvicorn.

### Tests — `tests/test_server.py`

Use `fastapi.testclient.TestClient` with a `tmp_vault`.

| Test | What it proves |
|------|---------------|
| `test_health` | `GET /health` returns 200 `{"status": "ok"}`. |
| `test_read_file` | `GET /files/note.md` returns file content. |
| `test_read_file_not_found` | Returns 404 with error body. |
| `test_write_file` | `PUT /files/new.md` creates file, returns 200. |
| `test_delete_file` | `DELETE /files/note.md` removes file. |
| `test_list_files` | `GET /files` returns file list. |
| `test_search_files` | `GET /search?query=test` returns results. |
| `test_get_frontmatter` | `GET /frontmatter/note.md` returns dict. |
| `test_update_frontmatter` | `PATCH /frontmatter/note.md` merges fields. |
| `test_path_error_returns_400` | Traversal path → 400. |
| `test_busy_returns_409` | Concurrent write → 409. |
| `test_vcs_commit` | `POST /vcs/commit` with message body. |

### Verification

```
devenv shell -- pytest tests/test_server.py -v   # all pass
devenv shell -- pytest tests/ -v                  # full suite green
```

---

## Step 11: Final Integration & Cleanup

### Work

1. Run full test suite with coverage report:
   ```
   devenv shell -- pytest tests/ --cov=obsidian_ops --cov-report=term-missing -v
   ```
2. Run linter and fix any issues:
   ```
   devenv shell -- ruff check src/ tests/ --fix
   devenv shell -- ruff format src/ tests/
   ```
3. Verify all public API exports match the spec.
4. Verify no unused imports, no dead code.
5. Update `README.md` with minimal usage example (only if requested).

### Verification — Acceptance Checklist

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Path sandbox blocks absolute, traversal, symlink escapes | `test_sandbox.py` all green |
| 2 | `read_file` / `write_file` / `delete_file` work correctly | `test_vault.py` all green |
| 3 | `list_files` returns matches, skips hidden | `test_search.py` all green |
| 4 | `search_files` is case-insensitive with snippets | `test_search.py` all green |
| 5 | `get_frontmatter` parses YAML correctly | `test_frontmatter.py` all green |
| 6 | `set/update/delete_frontmatter` work with shallow merge | `test_frontmatter.py` all green |
| 7 | `read_heading` / `write_heading` respect heading boundaries | `test_content.py` all green |
| 8 | `read_block` / `write_block` handle block refs | `test_content.py` all green |
| 9 | `commit` runs `jj describe` + `jj new` | `test_vcs.py` all green |
| 10 | `undo` runs `jj undo` | `test_vcs.py` all green |
| 11 | Mutation lock prevents concurrent writes | `test_lock.py` all green |
| 12 | HTTP server exposes all operations (if built) | `test_server.py` all green |
| 13 | ≥90% line coverage | `--cov-report` output |
| 14 | `ruff check` clean | Zero violations |

---

## File Creation Order Summary

```
Step 0:  pyproject.toml (update), __init__.py, conftest.py
Step 1:  src/obsidian_ops/errors.py
Step 2:  src/obsidian_ops/lock.py          tests/test_lock.py
Step 3:  src/obsidian_ops/sandbox.py       tests/test_sandbox.py
Step 4:  src/obsidian_ops/search.py        tests/test_search.py
Step 5:  src/obsidian_ops/vault.py         tests/test_vault.py
Step 6:  src/obsidian_ops/frontmatter.py   tests/test_frontmatter.py
Step 7:  src/obsidian_ops/content.py       tests/test_content.py
Step 8:  src/obsidian_ops/vcs.py           tests/test_vcs.py
Step 9:  src/obsidian_ops/__init__.py (finalize)
Step 10: src/obsidian_ops/server.py        tests/test_server.py
Step 11: (cleanup and final verification)
```

Each step is independently testable. Do not proceed to the next step until all tests for the current step pass.
