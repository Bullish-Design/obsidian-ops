# obsidian-ops Code Review

**Date**: 2026-04-07
**Branch**: `refactor`
**Scope**: Full review of `src/obsidian_ops/` and `tests/` against the REFACTOR_GUIDE.md spec

---

## Executive Summary

The refactored codebase is well-structured, clean, and closely follows the architectural guide. All 108 tests pass, ruff reports zero lint violations, and line coverage sits at exactly 90% — the stated target. The implementation correctly addresses the 11 binding design decisions. Below are findings organized by severity.

---

## Test & Quality Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests passing | 108/108 | All pass | PASS |
| Line coverage | 90% | >= 90% | PASS |
| Ruff lint | 0 violations | 0 | PASS |
| Modules covered | 10/10 | All | PASS |

### Coverage Breakdown

| Module | Coverage | Uncovered Lines |
|--------|----------|-----------------|
| `__init__.py` | 100% | — |
| `errors.py` | 100% | — |
| `lock.py` | 100% | — |
| `vcs.py` | 100% | — |
| `content.py` | 96% | 43, 77 |
| `sandbox.py` | 94% | 38, 57 |
| `search.py` | 94% | 22, 50, 58 |
| `vault.py` | 97% | 110, 122, 133, 146 |
| `frontmatter.py` | 89% | 35, 41, 53, 55 |
| `server.py` | 73% | 20–23, 40, 48, 52, 56, 91–92, 101–102, ... |

The `server.py` at 73% is the primary drag on coverage. Many exception handlers and content-patch endpoints lack dedicated test paths (they're tested only via monkeypatched error injection, not through real exercise of the code paths).

---

## Bugs

### BUG-1: `find_block` regex boundary assertions are non-functional (content.py:62)

**Severity**: Medium
**File**: `src/obsidian_ops/content.py`, line 62

```python
token_re = re.compile(rf"(?<!\\S){re.escape(block_id)}(?!\\S)")
```

Inside an `rf"..."` string, `\\S` produces the literal two-character sequence `\S` in the regex source. However, this is inside a lookbehind `(?<!...)` and lookahead `(?!...)`, so the regex engine interprets this as:

- `(?<!\\S)` → "not preceded by a literal backslash followed by `S`"
- `(?!\\S)` → "not followed by a literal backslash followed by `S`"

The **intended** behavior was almost certainly:

- `(?<!\S)` → "not preceded by a non-whitespace character" (i.e., must be at word boundary / start)
- `(?!\S)` → "not followed by a non-whitespace character" (i.e., must be at end / before whitespace)

**Why tests still pass**: Block IDs like `^ref-block` are typically found at end-of-line after a space, so `token_re.search()` still finds the match. The boundary guards are simply inert — they never reject anything, but they also never cause false negatives with the current test data.

**Impact**: If a block ID substring appears within a longer word (e.g., `^ref` appearing inside `some^reference`), `find_block` would incorrectly match it. This violates the spec's intent of matching only standalone block references.

**Fix**:
```python
token_re = re.compile(rf"(?<!\S){re.escape(block_id)}(?!\S)")
```

---

### BUG-2: `_heading_level` returns `None` for non-heading lines matched by exact string (content.py:42-43)

**Severity**: Low
**File**: `src/obsidian_ops/content.py`, lines 42-43

```python
current_level = _heading_level(normalized)
if current_level is None:
    continue
```

`find_heading` first checks `normalized != target` and then verifies the match is actually a heading via `_heading_level`. This means if the user passes a `heading` string that doesn't start with `#` (e.g., just `"Summary"`), it will never match, silently returning `None`. This is correct defensive behavior, but it's an undocumented implicit contract — the caller must include the `#` prefix in the heading string. The spec says "exact match on heading line after stripping trailing whitespace" which implies the `#` prefix is part of the heading parameter. This is fine but worth documenting.

---

## Design Concerns

### DESIGN-1: Duplicate constants between `search.py` and `vault.py`

**Severity**: Low
**Files**: `src/obsidian_ops/search.py` (lines 9-10), `src/obsidian_ops/vault.py` (lines 17-20)

Both modules define:
```python
MAX_READ_SIZE = 512 * 1024
SNIPPET_CONTEXT = 80
```

`vault.py` imports the functions from `search.py` but not the constants; it re-declares its own copies. If these values ever diverge, `search_content` would use one threshold while `Vault.read_file` uses another, creating confusing behavior (a file could be readable via `read_file` but skipped by `search_files`, or vice versa).

**Recommendation**: Define constants in one canonical location (e.g., `vault.py` or a shared `_constants.py`) and import them in `search.py`. Alternatively, have `search_content` accept `max_read_size` as a parameter rather than using a module-level constant.

---

### DESIGN-2: `sandbox.py` re-resolves root on every call (sandbox.py:46)

**Severity**: Low
**File**: `src/obsidian_ops/sandbox.py`, line 46

```python
resolved_root = Path(os.path.realpath(root))
```

`Vault.__init__` already resolves root via `os.path.realpath` and stores it in `self.root`. But `validate_path` calls `os.path.realpath(root)` again on every invocation. Since `self.root` is already resolved, this is redundant work. Not a correctness issue — just unnecessary I/O on each path validation call.

---

### DESIGN-3: `server.py` VCSError status heuristic is fragile (server.py:19-23)

**Severity**: Medium
**File**: `src/obsidian_ops/server.py`, lines 19-23

```python
def _status_for_vcs_error(exc: VCSError) -> int:
    message = str(exc).lower()
    if "not found" in message or "workspace" in message:
        return 424
    return 500
```

Per Decision #11 in the refactor guide: "Precondition failures (missing binary, no workspace) → 424 Failed Dependency. Execution failures → 500."

The current string-matching heuristic is:
- "not found" could match any error message that happens to contain those words (e.g., `"jj command failed: ... stdout: commit not found"` would get 424 instead of 500)
- "workspace" is equally broad

**Recommendation**: Introduce a `VCSPreconditionError(VCSError)` subclass for precondition failures (raised in `JJ._run` for `FileNotFoundError` and in a new workspace check). The server would then check `isinstance(exc, VCSPreconditionError)` instead of parsing message strings.

---

### DESIGN-4: Sync `Vault` methods called from `async` server handlers (server.py)

**Severity**: Low
**File**: `src/obsidian_ops/server.py`

All FastAPI route handlers are declared `async` but call synchronous `Vault` methods directly (file I/O, subprocess calls). In FastAPI, calling blocking I/O from an `async def` handler blocks the event loop. FastAPI does handle this for `def` (non-async) handlers by running them in a threadpool, but for `async def` handlers, blocking calls run directly on the event loop thread.

For the current use case (single-user MCP-style tool server), this is unlikely to cause issues. But it's architecturally incorrect for any concurrent usage.

**Recommendation**: Either (a) change all handlers from `async def` to plain `def` so FastAPI auto-offloads them to the threadpool, or (b) use `asyncio.to_thread()` to wrap the blocking vault calls.

---

## Spec Compliance

### Checklist: Design Decisions from REFACTOR_GUIDE.md

| # | Decision | Compliant | Notes |
|---|----------|-----------|-------|
| 1 | Shallow merge for frontmatter update | YES | `vault.py:100` uses `dict.update()` — shallow by definition |
| 2 | Best-effort YAML preservation | YES | Body preserved byte-for-byte; uses `pyyaml` `safe_dump` with `sort_keys=False` |
| 3 | Wikilinks not in v1 | YES | No wikilink-related code exists |
| 4 | Heading boundary: next heading level <= current | YES | `content.py:51`: `follow_level <= current_level` |
| 5 | Lock: public acquires, `_unsafe_*` does not | YES | All public mutating methods use `with self._lock`; `_unsafe_write_file`/`_unsafe_delete_file` do not |
| 6 | Path sandbox TOCTOU accepted | YES | `sandbox.py` uses `os.path.realpath` at call time, no attempt at atomic check-and-use |
| 7 | Block ref: simple paragraphs and single-line list items only | YES | `content.py` `find_block` handles paragraphs and list items; no multi-line block logic |
| 8 | `search_files` skips files > MAX_READ_SIZE | YES | `search.py:59`: `path.stat().st_size > MAX_READ_SIZE` → skip |
| 9 | `list_files` uses full relative-path glob | YES | `search.py:34`: `fnmatch(rel_path_str, pattern)` on full relative posix path |
| 10 | HTTP heading/block params via JSON body | YES | `server.py:104-120`: POST/PUT endpoints use `payload` dict from JSON body |
| 11 | VCS precondition → 424, execution → 500 | PARTIAL | String heuristic, not type-based (see DESIGN-3) |

### Checklist: Step Implementation from REFACTOR_GUIDE.md

| Step | Module | Status | Notes |
|------|--------|--------|-------|
| 0 | Project scaffold | DONE | `pyproject.toml` matches spec. `conftest.py` has `tmp_vault` fixture. |
| 1 | `errors.py` | DONE | All 7 exception classes present and exported. |
| 2 | `lock.py` | DONE | `MutationLock` with acquire/release/context manager/`is_held`. 6 tests. |
| 3 | `sandbox.py` | DONE | `validate_path` with all spec'd checks. 12 tests. |
| 4 | `search.py` | DONE | `walk_vault` + `search_content` + `SearchResult`. 12 tests. |
| 5 | `vault.py` | DONE | `Vault` class with all core file ops. 17 tests. |
| 6 | `frontmatter.py` | DONE | Parse/serialize + Vault methods. 18 tests. |
| 7 | `content.py` | DONE | `find_heading`/`find_block` + Vault methods. 19 tests. BUG-1 in `find_block` regex. |
| 8 | `vcs.py` | DONE | `JJ` class + Vault VCS methods. 11 tests. |
| 9 | `__init__.py` | DONE | All public API exports match spec. |
| 10 | `server.py` | DONE | All endpoints present. 12 tests. |
| 11 | Final cleanup | DONE | 108 tests pass, 90% coverage, ruff clean. |

---

## Test Quality Assessment

### Strengths

- **Good coverage of core paths**: Each module has a dedicated test file with clear, well-named tests.
- **Fixture design**: `tmp_vault` in `conftest.py` creates a realistic vault structure with frontmatter, headings, block refs, hidden dirs, and symlink escapes.
- **VCS mocking**: `test_vcs.py` correctly mocks `subprocess.run` to avoid requiring a real `jj` installation. Tests verify both command construction and error mapping.
- **Lock concurrency test**: `test_lock.py::test_concurrent_threads` uses a real background thread to verify cross-thread contention behavior.
- **Edge cases covered**: Empty paths, traversal attacks, symlink escapes, BOM-prefixed frontmatter, unicode filenames.

### Gaps

| Gap | Severity | Description |
|-----|----------|-------------|
| `find_block` boundary behavior | Medium | No test where the block ID is a substring of a larger token. Current tests always have block IDs at line boundaries, so BUG-1 is invisible. |
| `server.py` endpoint coverage | Medium | Only 73% coverage. Missing real-exercise tests for: `set_frontmatter` (PUT), `delete_frontmatter_field` (DELETE), `read_heading` (POST), `write_heading` (PUT), `read_block` (POST), `write_block` (PUT), `vcs_undo`, `vcs_status`, `FileTooLargeError` → 413, `FrontmatterError` → 422, `ContentPatchError` → 422, `VCSError` → 424/500 error paths. |
| `frontmatter.py` uncovered lines | Low | Lines 35, 41, 53, 55 — the `\r\n` body separator path (line 41), `loaded is None` path (line 53), and non-dict frontmatter (line 55) are not tested through the Vault interface (only via unit tests). BOM handling (line 35) untested via Vault methods. |
| `content.py` uncovered lines | Low | Line 43 (`_heading_level` returns `None` for matched non-heading) and line 77 (paragraph walk-back for non-list-item blocks where start_line > 0 traversal condition exits at line 0) — minor edge cases. |
| No integration test for write contention | Low | `test_is_busy` in `test_vault.py` verifies the lock is held during `_unsafe_write_file` via monkeypatch, but no test actually attempts two concurrent writes to verify `BusyError` propagation end-to-end. |
| `delete_file` for missing file via Vault | Low | `test_vault.py::test_delete_file_not_found` tests this, but `test_server.py` does not test `DELETE /files/missing.md` → 404. |
| `search_content` with empty or edge inputs | Low | No test for `search_content` with empty query string or `max_results=0`. The early-return guard (line 49) is uncovered. |

---

## Code Quality Observations

### Positive

1. **Clean module boundaries**: Each module has a single responsibility. `vault.py` delegates to focused helpers (`sandbox.py`, `frontmatter.py`, `content.py`, `search.py`, `vcs.py`).

2. **Lock discipline**: The "public methods acquire lock; `_unsafe_*` helpers don't" pattern from Decision #5 is consistently applied. No public mutating method calls another public mutating method.

3. **Minimal dependencies**: Core library requires only `pyyaml`. FastAPI/uvicorn are properly isolated as optional extras.

4. **YAML timestamp stripping**: `_NoTimestampSafeLoader` is a clever solution to prevent PyYAML from auto-converting date-like strings to `datetime.date` objects, which would break round-trip fidelity for frontmatter values like `2024-01-15`.

5. **`from __future__ import annotations`**: Consistently used across all modules for PEP 604 union syntax and forward references.

6. **Frozen dataclass**: `SearchResult` is `frozen=True`, making it properly immutable.

### Minor Observations

1. **`__init__.py` version string missing**: The refactor guide (Step 0) mentions "placeholder docstring and version" in `__init__.py`, but no `__version__` is defined. The version lives only in `pyproject.toml`. This is fine for modern Python packaging (`importlib.metadata.version("obsidian-ops")` works), but differs from the guide's instruction.

2. **`walk_vault` sorting**: Results are sorted alphabetically via `matches.sort()`, which is correct per spec. However, for very large vaults, this collects all matches before sorting and truncating. A heap-based approach (or early termination) would be more memory-efficient, though this is a minor concern for the expected vault sizes.

3. **`write_block` trailing newline normalization**: `vault.py:157` ensures the replacement content ends with `\n`. This is good defensive behavior for maintaining file structure, but is an implicit contract not documented in the method signature.

4. **`server.py` module-level imports**: `import uvicorn` and `from fastapi import ...` at the top level means `import obsidian_ops.server` will fail if the `server` extra isn't installed. This is acceptable since the module is explicitly optional, but it means the console script entry point `obsidian-ops-server` will crash with an `ImportError` rather than a helpful error message if FastAPI is missing.

5. **`pyproject.toml` includes `httpx` in dev deps**: The refactor guide says to remove `httpx`, but it's still present. It's likely needed as a `TestClient` transport backend (FastAPI's `TestClient` uses `httpx` internally), so this is a justified deviation.

---

## Recommendations Summary

### Must Fix

| # | Item | Effort |
|---|------|--------|
| 1 | Fix `find_block` regex boundary assertions (BUG-1) | 1 line |
| 2 | Add test for block ID substring false-positive | ~5 lines |

### Should Fix

| # | Item | Effort |
|---|------|--------|
| 3 | Add server tests for uncovered endpoints (heading, block, VCS status/undo, delete frontmatter field) | ~60 lines |
| 4 | Replace VCSError string heuristic with subclass-based dispatch (DESIGN-3) | ~15 lines |
| 5 | Deduplicate `MAX_READ_SIZE` / `SNIPPET_CONTEXT` constants (DESIGN-1) | ~5 lines |

### Nice to Have

| # | Item | Effort |
|---|------|--------|
| 6 | Change `async def` handlers to `def` for correct threadpool offloading (DESIGN-4) | ~20 lines (mechanical) |
| 7 | Remove redundant `realpath` in `validate_path` (DESIGN-2) | ~2 lines |
| 8 | Add `__version__` to `__init__.py` per refactor guide Step 0 | ~3 lines |

---

## File-by-File Summary

| File | Lines | Status | Issues |
|------|-------|--------|--------|
| `errors.py` | 29 | Clean | — |
| `lock.py` | 37 | Clean | — |
| `sandbox.py` | 59 | Clean | Minor: redundant `realpath` |
| `search.py` | 71 | Clean | Minor: duplicate constants |
| `frontmatter.py` | 63 | Clean | — |
| `content.py` | 83 | **BUG** | BUG-1: `find_block` regex |
| `vault.py` | 176 | Clean | Minor: duplicate constants |
| `vcs.py` | 52 | Clean | — |
| `server.py` | 154 | Adequate | DESIGN-3, DESIGN-4; low test coverage |
| `__init__.py` | 25 | Clean | Missing `__version__` |
| `pyproject.toml` | 70 | Clean | `httpx` retained (justified) |
| `conftest.py` | 71 | Clean | Good fixture design |
| Tests (8 files) | ~803 | Good | Gaps in server endpoint coverage |

---

## Conclusion

The refactored library is in solid shape. The architecture faithfully follows the refactor guide's module decomposition, locking strategy, and design decisions. Code is clean, idiomatic, and well-tested for a v1. The one real bug (`find_block` regex) is unlikely to cause issues with typical Obsidian block references but should be fixed before any production use. The server coverage gap and VCS error heuristic are the main items worth addressing in a follow-up pass.
