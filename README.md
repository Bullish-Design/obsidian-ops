# obsidian-ops

Sandboxed, library-first operations for an Obsidian vault.

## Contents

1. What `obsidian-ops` is and is not
   Explains the package boundary, supported responsibilities, and explicit non-goals.
2. Installation
   Covers core library installs, optional server installs, and the dev/test environment.
3. Development setup
   Shows the repo-local workflow for contributors using `devenv`.
4. Running tests
   Lists the default and focused validation commands used in this repo.
5. Library usage examples
   Demonstrates the main `Vault` APIs for files, frontmatter, content patches, search, and VCS.
6. Server usage examples
   Describes the optional HTTP server, request shapes, responses, and error codes.
7. VCS prerequisites and expectations
   Explains the JJ dependency, commit flow, and the supported undo lifecycle.
8. Error model
   Summarizes the exception types callers should handle.
9. Integration notes for `obsidian-agent`
   Documents the intended lower-layer contract for upstream consumers.

## What `obsidian-ops` Is And Is Not

`obsidian-ops` is the low-level vault operations layer for:

- sandboxed file CRUD inside a vault root
- YAML frontmatter reads, replacement, deep merge updates, and field deletion
- markdown content patching by heading or block reference
- file listing and content search
- JJ-backed commit, status, and undo operations
- an optional FastAPI server that mirrors the library API

`obsidian-ops` is not responsible for:

- LLM calls or prompt construction
- Forge-specific request envelopes or UI behavior
- URL-to-file resolution
- app-level orchestration outside the vault operations boundary

## Installation

Install the core library only:

```bash
pip install obsidian-ops
```

Install the optional HTTP server support:

```bash
pip install "obsidian-ops[server]"
```

Set up the full development and test environment in this repo:

```bash
devenv shell -- uv sync --extra dev
```

The `dev` extra includes the optional server dependencies so the full test suite
and `obsidian-ops-server` entrypoint work in the default development flow.

## Development Setup

This repository uses `devenv` for its local toolchain.

1. Enter commands through `devenv shell -- ...`.
2. Before the first test run in a session, sync dependencies:

```bash
devenv shell -- uv sync --extra dev
```

3. Use the checked-in source directly while iterating:

```bash
devenv shell -- pytest -q
devenv shell -- ruff check src tests
```

## Running Tests

Run the full repository suite:

```bash
devenv shell -- pytest -q
```

Focused suites used during development:

```bash
devenv shell -- pytest -q tests/test_frontmatter.py
devenv shell -- pytest -q tests/test_content.py
devenv shell -- pytest -q tests/test_vcs.py
devenv shell -- pytest -q tests/test_server.py
devenv shell -- pytest -q tests/test_search.py
devenv shell -- pytest -q tests/test_integration.py
```

Optional repo checks:

```bash
devenv shell -- ruff check src tests
devenv shell -- ruff format --check src tests
```

## Library Usage Examples

Create a vault client:

```python
from obsidian_ops import Vault

vault = Vault("/path/to/vault")
```

Read and write files:

```python
content = vault.read_file("Projects/Alpha.md")
vault.write_file("Projects/Alpha.md", content + "\nUpdated.\n")
vault.delete_file("Scratch/Todo.md")
```

Frontmatter updates are deep merges for nested mappings and preserve the markdown
body:

```python
vault.update_frontmatter("note.md", {"status": "published"})
vault.update_frontmatter(
    "note.md",
    {"metadata": {"review": {"status": "done"}}},
)
```

If the existing frontmatter contains:

```yaml
metadata:
  created: 2024-01-15
  review:
    status: pending
    assigned_to: Bob
```

the result becomes:

```yaml
metadata:
  created: 2024-01-15
  review:
    status: done
    assigned_to: Bob
```

Content patching is explicit:

- `write_heading(path, heading, content)` replaces the existing section body when
  the heading exists, or appends a new section at EOF when it does not.
- `write_block(path, block_id, content)` is strict and raises
  `ContentPatchError` if the block anchor is missing.
- heading and block writes normalize the replacement content to end with a
  newline.

Examples:

```python
section = vault.read_heading("note.md", "## Summary")
vault.write_heading("note.md", "## Summary", "Updated summary.")

block = vault.read_block("note.md", "^ref-block")
vault.write_block("note.md", "^ref-block", "Updated paragraph. ^ref-block")
```

File listing and search use vault-relative-path globs:

```python
vault.list_files("Projects/*.md")
vault.search_files("alpha", glob="Projects/*.md")
```

`"Projects/*.md"` matches `Projects/Alpha.md`, while `"Alpha.md"` does not.
Hidden files and hidden directories are skipped by both operations.

## Server Usage Examples

Start the optional HTTP server:

```bash
obsidian-ops-server --vault /path/to/vault --host 127.0.0.1 --port 9200
```

Representative routes:

- `GET /health` returns `{"ok": true, "status": "healthy"}`
- `PUT /files/{path}` expects `{"content": "..."}`
- `PATCH /frontmatter/{path}` expects a JSON object of frontmatter fields to merge
- `PUT /content/heading/{path}` expects `{"heading": "## Summary", "content": "..."}`
- `PUT /content/block/{path}` expects `{"block_id": "^ref-block", "content": "..."}`
- `POST /vcs/commit` expects `{"message": "..."}`
- `POST /vcs/undo` returns `{"status": "ok", "restored": true|false, "warning": ...}`

Example requests:

```bash
curl -s http://127.0.0.1:9200/health
curl -s -X PUT http://127.0.0.1:9200/files/Projects/Alpha.md \
  -H 'content-type: application/json' \
  -d '{"content":"# Alpha\n\nUpdated.\n"}'
curl -s -X PUT http://127.0.0.1:9200/content/heading/note.md \
  -H 'content-type: application/json' \
  -d '{"heading":"## Summary","content":"Updated summary."}'
```

Stable server error codes:

- `400` for `PathError`
- `404` for missing files
- `409` for `BusyError`
- `413` for `FileTooLargeError`
- `422` for request validation errors, `FrontmatterError`, and `ContentPatchError`
- `424` for VCS precondition failures such as a missing `jj` binary or workspace
- `500` for other `VCSError` execution failures

## VCS Prerequisites And Expectations

VCS features require:

- `jj` to be installed and available on `PATH`
- the vault directory to be inside a JJ workspace

Core vault operations still work without JJ. VCS methods raise `VCSError` when
those prerequisites are missing.

Commit flow:

```python
vault.commit("ops: update note")
```

This snapshots the current working copy by running:

```text
jj describe -m "<message>"
jj new
```

Undo expectations:

- `vault.undo()` is the low-level wrapper around `jj undo`
- `vault.undo_last_change()` is the supported upstream undo API
- `undo_last_change()` runs `jj undo` and then `jj restore --from @-`
- if restore fails after undo succeeds, the method returns `UndoResult` with
  `restored=False` and a warning instead of raising

Example:

```python
result = vault.undo_last_change()
if result.warning:
    print(result.warning)
```

## Error Model

Primary exception types:

- `PathError` for path traversal, absolute-path, or symlink escape violations
- `FileTooLargeError` for reads beyond the configured size limit
- `BusyError` when the mutation lock is already held
- `FrontmatterError` for malformed or unsupported frontmatter states
- `ContentPatchError` for invalid heading/block patch operations
- `VCSError` for JJ command failures
- `VaultError` as the common base class

Typical caller behavior is:

- treat `PathError`, `FrontmatterError`, and `ContentPatchError` as user-fixable
  request issues
- treat `BusyError` as retryable
- treat `VCSError` as an environment or repository-state problem

## Integration Notes For `obsidian-agent`

`obsidian-ops` is the stable lower-layer dependency boundary for
`obsidian-agent`.

Upstream callers should:

- use `Vault` directly instead of shelling out to `jj`
- treat direct `jj` subprocess usage outside `obsidian-ops` as a boundary violation
- use `undo_last_change()` for user-visible undo flows
- rely on `update_frontmatter()` for nested metadata patches instead of
  rewriting entire files
- rely on the explicit heading/block patch contracts documented above

`obsidian-ops` intentionally does not include any agent-specific logic, prompt
construction, or Forge-specific path resolution.
