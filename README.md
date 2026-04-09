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
