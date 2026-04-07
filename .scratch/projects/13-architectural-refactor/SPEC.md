# obsidian-ops: Technical Specification

## 1. Overview

obsidian-ops is a Python library providing sandboxed, structured operations on an Obsidian vault. This document specifies the complete library API, data types, error handling, safety properties, and testing requirements.

**Read CONCEPT.md first** for motivation and high-level design decisions.

---

## 2. Public API

### 2.1 `Vault` class

The primary entry point. All operations go through this class.

```python
class Vault:
    def __init__(self, root: str | Path, *, jj_bin: str = "jj", jj_timeout: int = 120) -> None:
        """
        Initialize a Vault instance.

        Args:
            root: Absolute path to the Obsidian vault directory. Must exist and be a directory.
            jj_bin: Path to the Jujutsu binary. Default: "jj".
            jj_timeout: Timeout in seconds for Jujutsu subprocess calls. Default: 120.

        Raises:
            VaultError: If root does not exist or is not a directory.
        """
```

**Thread safety**: The `Vault` instance is thread-safe. Write operations are serialized by the internal mutation lock. Read operations can proceed concurrently.

---

### 2.2 File operations

#### `read_file`

```python
def read_file(self, path: str) -> str:
    """
    Read a vault-relative file and return its contents as a string.

    Args:
        path: Vault-relative file path (e.g., "Projects/Alpha.md").

    Returns:
        The file contents as a UTF-8 string.

    Raises:
        PathError: If the path is absolute, contains "..", or escapes the vault via symlink.
        FileNotFoundError: If the file does not exist.
        FileTooLargeError: If the file exceeds MAX_READ_SIZE (512 KB).
    """
```

#### `write_file`

```python
def write_file(self, path: str, content: str) -> None:
    """
    Write content to a vault-relative file. Creates the file and parent directories if needed.
    Overwrites existing content.

    Acquires the mutation lock. Raises BusyError if another write operation is in progress.

    Args:
        path: Vault-relative file path.
        content: The full file content to write (UTF-8).

    Raises:
        PathError: If the path fails sandbox validation.
        BusyError: If the mutation lock is held by another operation.
    """
```

#### `delete_file`

```python
def delete_file(self, path: str) -> None:
    """
    Delete a vault-relative file.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.

    Raises:
        PathError: If the path fails sandbox validation.
        FileNotFoundError: If the file does not exist.
        BusyError: If the mutation lock is held.
    """
```

#### `list_files`

```python
def list_files(self, pattern: str = "*.md", *, max_results: int = 200) -> list[str]:
    """
    List vault-relative file paths matching a filename glob pattern.

    Skips:
    - Files and directories starting with "." (dotfiles)
    - Files and directories starting with "_hidden_"

    The glob pattern matches against the filename only (not the full path).

    Args:
        pattern: Filename glob (e.g., "*.md", "*.canvas"). Default: "*.md".
        max_results: Maximum number of results to return. Default: 200.

    Returns:
        A sorted list of vault-relative file paths.

    Raises:
        PathError: If the pattern is invalid.
    """
```

#### `search_files`

```python
def search_files(
    self, query: str, *, glob: str = "*.md", max_results: int = 50
) -> list[SearchResult]:
    """
    Search file contents for a case-insensitive query string.

    Args:
        query: The search string (case-insensitive).
        glob: Filename glob to filter the search scope. Default: "*.md".
        max_results: Maximum number of matching files to return. Default: 50.

    Returns:
        A list of SearchResult objects, each containing:
        - path: vault-relative file path
        - snippet: ~160-character context around the first match
    """
```

---

### 2.3 Frontmatter operations

All frontmatter methods operate on the YAML block delimited by `---` at the top of a markdown file.

#### `get_frontmatter`

```python
def get_frontmatter(self, path: str) -> dict[str, Any] | None:
    """
    Parse and return the YAML frontmatter from a file.

    Args:
        path: Vault-relative file path.

    Returns:
        A dictionary of frontmatter fields, or None if the file has no frontmatter.

    Raises:
        PathError: If the path fails sandbox validation.
        FileNotFoundError: If the file does not exist.
        FrontmatterError: If the frontmatter YAML is malformed.
    """
```

#### `set_frontmatter`

```python
def set_frontmatter(self, path: str, data: dict[str, Any]) -> None:
    """
    Replace the entire frontmatter block with the given data.
    If the file has no frontmatter, a new block is prepended.
    The body content after the frontmatter is preserved unchanged.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.
        data: Dictionary to serialize as YAML frontmatter.

    Raises:
        PathError, BusyError, FileNotFoundError.
    """
```

#### `update_frontmatter`

```python
def update_frontmatter(self, path: str, updates: dict[str, Any]) -> None:
    """
    Merge updates into existing frontmatter. Only specified fields are changed;
    all other fields are preserved. Supports nested paths via dot notation
    or nested dicts.

    If the file has no frontmatter, creates one with the given fields.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.
        updates: Dictionary of fields to add or update.

    Examples:
        # Set a top-level field
        vault.update_frontmatter("note.md", {"status": "active"})

        # Set a nested field
        vault.update_frontmatter("note.md", {"metadata": {"reviewed": True}})
    """
```

#### `delete_frontmatter_field`

```python
def delete_frontmatter_field(self, path: str, field: str) -> None:
    """
    Remove a single top-level field from the frontmatter.
    No-op if the field does not exist.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.
        field: The top-level field name to remove.
    """
```

---

### 2.4 Content patching operations

These methods operate on semantic anchors within markdown files.

#### `read_heading`

```python
def read_heading(self, path: str, heading: str) -> str | None:
    """
    Read the content under a heading.

    Returns all content from immediately after the heading line up to (but not including)
    the next heading of equal or higher level, or end of file.

    Args:
        path: Vault-relative file path.
        heading: The full heading line including the "#" prefix (e.g., "## Summary").

    Returns:
        The content under the heading as a string, or None if the heading is not found.

    Raises:
        PathError, FileNotFoundError.
    """
```

#### `write_heading`

```python
def write_heading(self, path: str, heading: str, content: str) -> None:
    """
    Replace the content under a heading.

    Replaces everything from immediately after the heading line up to (but not including)
    the next heading of equal or higher level, or end of file. The heading line itself
    is preserved.

    If the heading does not exist, it is appended to the end of the file with the given content.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.
        heading: The full heading line (e.g., "## Summary").
        content: The replacement content (without the heading line).
    """
```

#### `read_block`

```python
def read_block(self, path: str, block_id: str) -> str | None:
    """
    Read the content associated with a block reference.

    In Obsidian, a block reference is a `^block-id` marker at the end of a paragraph
    or list item. This method returns the full paragraph or list item containing the marker.

    Args:
        path: Vault-relative file path.
        block_id: The block identifier including the "^" prefix (e.g., "^meeting-notes").

    Returns:
        The paragraph/block containing the reference, or None if not found.
    """
```

#### `write_block`

```python
def write_block(self, path: str, block_id: str, content: str) -> None:
    """
    Replace the content associated with a block reference.

    Replaces the entire paragraph or list item that contains the `^block-id` marker.
    The block_id marker should be included in the replacement content if you want
    it to remain referenceable.

    Acquires the mutation lock.

    Args:
        path: Vault-relative file path.
        block_id: The block identifier (e.g., "^meeting-notes").
        content: The replacement content.
    """
```

---

### 2.5 Version control operations

All VCS methods require Jujutsu (`jj`) to be installed and the vault directory to be within a Jujutsu workspace. If `jj` is not available, these methods raise `VCSError`.

#### `commit`

```python
def commit(self, message: str) -> None:
    """
    Snapshot the current working-copy state and create a fresh Jujutsu change.

    Equivalent to:
        jj describe -m "<message>"
        jj new

    Acquires the mutation lock.

    Args:
        message: The commit message.

    Raises:
        VCSError: If jj commands fail.
        BusyError: If the mutation lock is held.
    """
```

#### `undo`

```python
def undo(self) -> None:
    """
    Revert the last Jujutsu operation.

    Equivalent to:
        jj undo

    Acquires the mutation lock.

    Raises:
        VCSError: If jj undo fails.
        BusyError: If the mutation lock is held.
    """
```

#### `vcs_status`

```python
def vcs_status(self) -> str:
    """
    Return the current Jujutsu workspace status.

    Equivalent to:
        jj status

    This is a read operation and does NOT acquire the mutation lock.

    Returns:
        The string output of `jj status`.

    Raises:
        VCSError: If jj is not available or the command fails.
    """
```

---

### 2.6 Lock inspection

```python
def is_busy(self) -> bool:
    """
    Check whether the mutation lock is currently held.

    Returns:
        True if a write operation is in progress, False otherwise.
    """
```

---

## 3. Data Types

### 3.1 `SearchResult`

```python
@dataclass(frozen=True)
class SearchResult:
    path: str       # Vault-relative file path
    snippet: str    # ~160-character context around the first match
```

### 3.2 Exception hierarchy

```python
class VaultError(Exception):
    """Base exception for all obsidian-ops errors."""

class PathError(VaultError):
    """Raised when a path fails sandbox validation."""

class FileTooLargeError(VaultError):
    """Raised when a file exceeds the read size limit."""

class BusyError(VaultError):
    """Raised when the mutation lock is held by another operation."""

class FrontmatterError(VaultError):
    """Raised when YAML frontmatter is malformed or cannot be parsed."""

class ContentPatchError(VaultError):
    """Raised when a heading or block reference operation fails."""

class VCSError(VaultError):
    """Raised when a Jujutsu operation fails or jj is not available."""
```

---

## 4. Constants

```python
MAX_READ_SIZE = 512 * 1024      # 512 KB — maximum file size for read operations
MAX_LIST_RESULTS = 200           # Default cap for list_files results
MAX_SEARCH_RESULTS = 50          # Default cap for search_files results
SNIPPET_CONTEXT = 80             # Characters of context on each side of a search match
```

---

## 5. Path Sandboxing — Detailed Specification

The path sandbox is the most security-critical component. Every file operation (read, write, delete, frontmatter, content patch) must pass through validation before accessing the filesystem.

### 5.1 Validation rules

Given a vault root `/vault` and a user-provided path `path`:

1. **Clean the path**: Apply `os.path.normpath` equivalent to collapse redundant separators and `.` components.
2. **Reject absolute paths**: If the cleaned path starts with `/` (or a drive letter on Windows), raise `PathError`.
3. **Reject traversal**: If the cleaned path starts with `..`, raise `PathError`.
4. **Construct absolute path**: Join the vault root and cleaned path.
5. **Symlink check** (for existing paths only): If the path exists on disk, resolve symlinks via `os.path.realpath` and verify the resolved path is within the vault root (also resolved). If not, raise `PathError`.

### 5.2 Edge cases

| Input | Expected |
|-------|----------|
| `"Projects/Alpha.md"` | Valid — `{vault}/Projects/Alpha.md` |
| `"/etc/passwd"` | `PathError` — absolute path |
| `"../../secrets.txt"` | `PathError` — traversal |
| `"Projects/../Alpha.md"` | Valid — normalizes to `{vault}/Alpha.md` |
| `"symlink_to_outside"` (symlink → `/tmp/bad`) | `PathError` — escapes vault via symlink |
| `""` (empty string) | `PathError` — invalid path |
| `"Projects/New File.md"` (spaces) | Valid |
| `"Projects/日本語.md"` (unicode) | Valid |

### 5.3 Implementation notes

- Symlink resolution only applies to paths that already exist on disk. For new files (write_file to a path that doesn't exist yet), validate the parent directory instead.
- The vault root itself should be resolved via `os.path.realpath` once during `Vault.__init__` and cached. All subsequent comparisons use the resolved root.

---

## 6. Frontmatter Parsing — Detailed Specification

### 6.1 Format

Obsidian frontmatter is a YAML block at the very beginning of a file, delimited by `---`:

```markdown
---
title: My Note
tags: [project, active]
---

# Content starts here
```

### 6.2 Parsing rules

1. The file must start with `---` (optionally preceded by whitespace/BOM).
2. The closing `---` must appear on its own line.
3. Content between the delimiters is parsed as YAML.
4. If the file has no frontmatter (does not start with `---`), `get_frontmatter` returns `None`.
5. If the YAML is malformed, raise `FrontmatterError`.

### 6.3 Modification rules

When modifying frontmatter (`set_frontmatter`, `update_frontmatter`, `delete_frontmatter_field`):

1. Parse the existing file into frontmatter + body.
2. Apply the modification to the frontmatter dictionary.
3. Serialize the modified dictionary back to YAML.
4. Reconstruct the file: `---\n{yaml}\n---\n{body}`.
5. Write the file atomically.

**Preservation goals** (best-effort, not strict requirements):
- Preserve key ordering where possible.
- Use the same YAML formatting style as the original (e.g., flow sequences `[a, b]` vs. block sequences).
- Preserve the body content byte-for-byte.

### 6.4 `update_frontmatter` merge semantics

`update_frontmatter` performs a **shallow merge** at the top level:
- Keys present in `updates` are set to the new value (overwriting if they exist).
- Keys NOT present in `updates` are preserved unchanged.
- To delete a key, use `delete_frontmatter_field` instead.

For nested values, the entire nested structure is replaced:

```python
# Given frontmatter: {"metadata": {"created": "2024-01-15", "author": "Alice"}}
vault.update_frontmatter("note.md", {"metadata": {"reviewed": True}})
# Result: {"metadata": {"reviewed": True}}  ← entire "metadata" replaced
```

If deep merge is needed in the future, it can be added as a separate method.

---

## 7. Content Patching — Detailed Specification

### 7.1 Heading boundaries

A heading section spans from the heading line to the next heading of **equal or higher level** (fewer `#` characters), or end of file.

Example:
```markdown
# Title
Intro paragraph.

## Summary
Summary content here.
More summary.

### Details
Detail content.

## Next Section
```

- `read_heading("## Summary")` returns `"Summary content here.\nMore summary.\n\n### Details\nDetail content.\n"`
- `write_heading("## Summary", "New summary.")` replaces everything between `## Summary` and `## Next Section`.

### 7.2 Heading matching

- Match is **exact** on the heading line after stripping trailing whitespace.
- The heading parameter should include the `#` prefix: `"## Summary"`, not `"Summary"`.
- If multiple headings have the same text, the **first match** is used.

### 7.3 Block reference boundaries

Obsidian block references appear at the end of a paragraph or list item:

```markdown
This is an important paragraph that I want to reference later. ^important-note

- List item one
- List item with reference ^list-ref
```

A "block" in Obsidian is the paragraph (or list item) containing the `^block-id`. The block extends from the preceding blank line (or start of file) to the line containing the marker.

### 7.4 Block matching

- Search for `^block-id` as a standalone token (preceded by space or start of line).
- The block ID parameter should include the `^` prefix: `"^important-note"`.
- If the block reference is not found, `read_block` returns `None` and `write_block` raises `ContentPatchError`.

---

## 8. Jujutsu VCS — Detailed Specification

### 8.1 Prerequisites

- The `jj` binary must be available at the configured path (default: `"jj"` on PATH).
- The vault directory must be within a Jujutsu workspace (has a `.jj/` directory at or above the vault root).
- If `jj` is not found or the workspace is not initialized, VCS methods raise `VCSError` with a clear message.

### 8.2 Commit operation

`commit(message)` performs two steps:

1. `jj describe -m "<message>"` — Set the description of the current working-copy commit.
2. `jj new` — Create a new empty change on top, making the just-described commit immutable.

Both commands run with `cwd` set to the vault directory and use the configured timeout.

### 8.3 Undo operation

`undo()` runs `jj undo`, which reverts the last Jujutsu operation. This restores the previous state of the working copy.

### 8.4 Timeout handling

All `jj` subprocess calls have a configurable timeout (default: 120 seconds). If the timeout is exceeded, the subprocess is killed and `VCSError` is raised.

### 8.5 Error reporting

If a `jj` command exits with a non-zero status, capture both stdout and stderr and include them in the `VCSError` message.

---

## 9. Mutation Lock — Detailed Specification

### 9.1 Behavior

The mutation lock is a non-reentrant try-lock:

- **Acquire**: If the lock is free, mark it as held and return. If already held, immediately raise `BusyError` (do not block/wait).
- **Release**: Mark the lock as free.

### 9.2 Which operations acquire the lock

| Operation | Lock? |
|-----------|-------|
| `read_file` | No |
| `write_file` | **Yes** |
| `delete_file` | **Yes** |
| `list_files` | No |
| `search_files` | No |
| `get_frontmatter` | No |
| `set_frontmatter` | **Yes** |
| `update_frontmatter` | **Yes** |
| `delete_frontmatter_field` | **Yes** |
| `read_heading` | No |
| `write_heading` | **Yes** |
| `read_block` | No |
| `write_block` | **Yes** |
| `commit` | **Yes** |
| `undo` | **Yes** |
| `vcs_status` | No |
| `is_busy` | No |

### 9.3 Implementation

Use a `threading.Lock` with non-blocking acquire (`acquire(blocking=False)`). The lock should be managed as a context manager internally to ensure release even on exceptions.

---

## 10. File Structure

```
obsidian-ops/
├── pyproject.toml
├── src/
│   └── obsidian_ops/
│       ├── __init__.py           # Public exports: Vault, exceptions, SearchResult
│       ├── vault.py              # Vault class implementation
│       ├── sandbox.py            # validate_path(root, path) → absolute path
│       ├── frontmatter.py        # parse_frontmatter(text) → (dict, body)
│       │                         # serialize_frontmatter(data, body) → text
│       ├── content.py            # find_heading(text, heading) → (start, end)
│       │                         # find_block(text, block_id) → (start, end)
│       ├── search.py             # walk_vault(root, pattern) → list[str]
│       │                         # search_content(root, query, files) → list[SearchResult]
│       ├── vcs.py                # JJ class wrapping jj subprocess calls
│       ├── lock.py               # MutationLock class
│       ├── errors.py             # Exception hierarchy
│       └── server.py             # Optional: FastAPI app exposing Vault methods
├── tests/
│   ├── conftest.py               # Fixtures: tmp_vault (tempdir with sample files)
│   ├── test_vault.py             # Integration tests using Vault class
│   ├── test_sandbox.py           # Path validation: absolute, traversal, symlink, unicode, spaces
│   ├── test_frontmatter.py       # Parse, set, update, delete frontmatter
│   ├── test_content.py           # Heading and block reference operations
│   ├── test_search.py            # list_files, search_files
│   ├── test_vcs.py               # JJ wrapper (mock subprocess or real jj)
│   └── test_lock.py              # Concurrent access, BusyError
└── README.md                     # Optional: brief usage examples
```

---

## 11. Dependencies

### 11.1 `pyproject.toml`

```toml
[project]
name = "obsidian-ops"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pyyaml>=6.0",
]

[project.optional-dependencies]
server = [
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",
]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
obsidian-ops-server = "obsidian_ops.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/obsidian_ops"]
```

---

## 12. Optional HTTP Server

The HTTP server is a thin wrapper that exposes `Vault` methods over HTTP. It is intended for standalone use by non-Python tools.

### 12.1 Design principle

The server mirrors the library API 1:1. Every public method on `Vault` maps to an endpoint. Request/response bodies are JSON.

### 12.2 Example endpoints (illustrative, not exhaustive)

```
GET  /files/{path:path}                    → read_file
PUT  /files/{path:path}                    → write_file (body: {"content": "..."})
DELETE /files/{path:path}                  → delete_file
GET  /files?pattern=*.md&max_results=200   → list_files
GET  /search?query=meeting&glob=*.md       → search_files

GET  /frontmatter/{path:path}              → get_frontmatter
PUT  /frontmatter/{path:path}              → set_frontmatter (body: frontmatter dict)
PATCH /frontmatter/{path:path}             → update_frontmatter (body: partial dict)
DELETE /frontmatter/{path:path}/{field}    → delete_frontmatter_field

GET  /content/heading/{path:path}?heading=## Summary     → read_heading
PUT  /content/heading/{path:path}?heading=## Summary     → write_heading (body: {"content": "..."})
GET  /content/block/{path:path}?block_id=^ref            → read_block
PUT  /content/block/{path:path}?block_id=^ref            → write_block (body: {"content": "..."})

POST /vcs/commit                           → commit (body: {"message": "..."})
POST /vcs/undo                             → undo
GET  /vcs/status                           → vcs_status

GET  /health                               → {"status": "ok"}
```

### 12.3 Error responses

All errors return a JSON body with `{"error": "<message>"}` and an appropriate HTTP status code:

| Exception | HTTP Status |
|-----------|-------------|
| `PathError` | 400 Bad Request |
| `FileNotFoundError` | 404 Not Found |
| `FileTooLargeError` | 413 Content Too Large |
| `BusyError` | 409 Conflict |
| `FrontmatterError` | 422 Unprocessable Entity |
| `ContentPatchError` | 422 Unprocessable Entity |
| `VCSError` | 500 Internal Server Error |

### 12.4 Server configuration

```bash
python -m obsidian_ops.server \
    --vault /path/to/vault \
    --host 127.0.0.1 \
    --port 9200 \
    --jj-bin jj \
    --jj-timeout 120
```

All arguments are optional except `--vault`.

---

## 13. Testing Specification

### 13.1 Test fixtures

The primary fixture is a temporary vault directory (`tmp_vault`) containing:

```
tmp_vault/
├── note.md                # Simple note with frontmatter and headings
├── no-frontmatter.md      # Note without frontmatter
├── Projects/
│   ├── Alpha.md           # Note with frontmatter, headings, block references
│   └── Beta.md            # Another project note
├── .hidden/
│   └── secret.md          # Should be skipped by list_files
├── _hidden_dir/
│   └── internal.md        # Should be skipped by list_files
└── symlink_escape         # Symlink pointing outside the vault (for sandbox tests)
```

Sample `note.md`:
```markdown
---
title: Test Note
tags: [test, sample]
status: draft
---

# Test Note

Introduction paragraph.

## Summary

This is the summary section.
It has multiple lines.

### Details

Some details here.

## References

A paragraph with a block reference. ^ref-block

- List item one
- Important list item ^list-ref
```

### 13.2 Test categories

#### Path sandbox tests (`test_sandbox.py`)
- Valid paths: simple, nested, with spaces, with unicode
- Absolute path rejection
- Traversal rejection (`..`, `foo/../../bar`)
- Symlink escape rejection
- Empty string rejection
- Path normalization (redundant separators, `.` components)

#### File operation tests (`test_vault.py`)
- Read existing file
- Read non-existent file → FileNotFoundError
- Read file exceeding size limit → FileTooLargeError
- Write new file (creates parent dirs)
- Write over existing file
- Delete existing file
- Delete non-existent file → FileNotFoundError
- List files with various glob patterns
- List files skips dotfiles and _hidden_ directories
- List files respects max_results cap
- Search files returns matching files with snippets
- Search is case-insensitive
- Search respects glob filter
- Search respects max_results cap

#### Frontmatter tests (`test_frontmatter.py`)
- Parse frontmatter from well-formed file
- Parse file with no frontmatter → None
- Parse malformed YAML → FrontmatterError
- Set frontmatter (replace entirely)
- Set frontmatter on file with no existing frontmatter (prepend)
- Update frontmatter (merge fields)
- Update preserves unmentioned fields
- Delete frontmatter field
- Delete non-existent field (no-op)
- Body content is preserved byte-for-byte after frontmatter modifications

#### Content patching tests (`test_content.py`)
- Read heading at various levels (h1, h2, h3)
- Read heading includes sub-headings
- Read heading stops at same-level heading
- Read heading stops at higher-level heading
- Read heading at end of file (content extends to EOF)
- Read non-existent heading → None
- Write heading replaces content correctly
- Write non-existent heading appends to file
- Read block reference
- Read non-existent block → None
- Write block reference replaces paragraph
- Block reference in list item

#### VCS tests (`test_vcs.py`)
- Commit runs correct jj commands in correct order
- Commit with cwd set to vault directory
- Undo runs jj undo
- Status returns jj status output
- Timeout kills subprocess and raises VCSError
- Non-zero exit code raises VCSError with output

#### Lock tests (`test_lock.py`)
- Write operation acquires and releases lock
- Concurrent write raises BusyError
- Lock is released on exception
- Read operations do not acquire lock
- `is_busy` reflects lock state

### 13.3 Test execution

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=obsidian_ops --cov-report=term-missing
```

---

## 14. Implementation Priorities

### Phase 1: Core file operations + sandbox
1. `sandbox.py` — Path validation (most security-critical)
2. `lock.py` — Mutation lock
3. `errors.py` — Exception hierarchy
4. `vault.py` — `read_file`, `write_file`, `delete_file`, `list_files`, `search_files`
5. Tests for all of the above

### Phase 2: Frontmatter
1. `frontmatter.py` — Parse and serialize
2. Vault methods: `get_frontmatter`, `set_frontmatter`, `update_frontmatter`, `delete_frontmatter_field`
3. Tests

### Phase 3: Content patching
1. `content.py` — Heading and block reference finding
2. Vault methods: `read_heading`, `write_heading`, `read_block`, `write_block`
3. Tests

### Phase 4: Version control
1. `vcs.py` — JJ wrapper
2. Vault methods: `commit`, `undo`, `vcs_status`
3. Tests

### Phase 5: Optional HTTP server
1. `server.py` — FastAPI app
2. Integration tests
