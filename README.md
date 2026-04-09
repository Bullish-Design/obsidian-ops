# obsidian-ops

Local-first operations overlay for an Obsidian vault.

## Installation

Install the core library only:

```bash
pip install obsidian-ops
```

Install the optional HTTP server support:

```bash
pip install "obsidian-ops[server]"
```

Install the development and test dependencies:

```bash
devenv shell -- uv sync --extra dev
```

The `dev` install includes the optional server dependencies so the full test
suite and `obsidian-ops-server` entrypoint work in the default development
environment.

## Frontmatter Updates

`Vault.update_frontmatter()` preserves the markdown body and recursively merges
nested mapping updates. It does not support delete-via-update semantics.

Example: shallow top-level updates still work.

```python
vault.update_frontmatter("note.md", {"status": "published"})
```

Example: nested mappings merge instead of replacing the whole subtree.

```python
vault.update_frontmatter(
    "note.md",
    {
        "metadata": {
            "review": {"status": "done"},
        },
    },
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

the updated result is:

```yaml
metadata:
  created: 2024-01-15
  review:
    status: done
    assigned_to: Bob
```

## Content Patching

`Vault.write_heading(path, heading, content)` treats `content` as the section
body, not the heading line.

- If `heading` already exists, the section body is replaced in place.
- If `heading` is missing, a new section is appended at the end of the file.
- The written content is normalized to end with a newline so adjacent headings
  and repeated writes do not collapse together.

Example: replace an existing section body.

```python
vault.write_heading("note.md", "## Summary", "Updated summary.")
```

Example: create a missing section at the end of the file.

```python
vault.write_heading("note.md", "## Follow Up", "Next steps.")
```

`Vault.write_block(path, block_id, content)` is strict:

- it replaces the matching paragraph or list item when `block_id` exists,
- it raises `ContentPatchError` when the block anchor is missing,
- block writes also normalize the replacement content to end with a newline.

## Version Control

Use `Vault.commit()` to snapshot the current working copy into JJ.

For upstream undo behavior, prefer `Vault.undo_last_change()` over the lower
level `Vault.undo()` method.

- `Vault.undo()` runs only `jj undo`.
- `Vault.undo_last_change()` runs the full lifecycle:
  - `jj undo`
  - `jj restore --from @-`
- if the restore step fails after undo succeeds, `undo_last_change()` returns an
  `UndoResult` with `restored=False` and a warning string instead of raising.

Example:

```python
result = vault.undo_last_change()
if result.warning:
    print(result.warning)
```

## Server API

The optional HTTP server mirrors the library API with typed request and response
payloads.

- `GET /health` returns `{"ok": true, "status": "healthy"}`
- `PUT /files/{path}` expects `{"content": "..."}`
- `PATCH /frontmatter/{path}` expects a JSON object representing frontmatter
  fields to merge
- `PUT /content/heading/{path}` expects `{"heading": "## Summary", "content": "..."}`
- `PUT /content/block/{path}` expects `{"block_id": "^ref-block", "content": "..."}`
- `POST /vcs/commit` expects `{"message": "..."}`
- `POST /vcs/undo` returns `{"status": "ok", "restored": true|false, "warning": ...}`

Server error codes are stable:

- `400` for `PathError`
- `404` for missing files
- `409` for `BusyError`
- `413` for `FileTooLargeError`
- `422` for request validation errors, `FrontmatterError`, and `ContentPatchError`
- `424` for VCS precondition failures such as a missing `jj` binary or workspace
- `500` for other `VCSError` execution failures

## Search And File Matching

`list_files()` and `search_files()` apply globs to vault-relative paths, not just
the filename.

- `vault.list_files("Projects/*.md")` matches `Projects/Alpha.md`
- `vault.list_files("Alpha.md")` does not match `Projects/Alpha.md`
- `vault.search_files("alpha", glob="Projects/*.md")` searches only files under
  `Projects/`

Both operations skip hidden files and hidden directories, and `search_files()`
uses the same scoped file set as `list_files()`.
