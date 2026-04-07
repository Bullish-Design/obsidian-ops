# obsidian-ops: Concept Guide

## Status

- Status: Proposed
- Target: Standalone Python library for Obsidian vault interaction primitives
- Relationship: Imported by obsidian-agent; independently useful for scripts, CLI tools, and non-LLM workflows
- Audience: Implementers building the vault operations layer

---

## 1. One-Sentence Summary

obsidian-ops is a Python library that provides sandboxed, structured operations on an Obsidian vault — file CRUD, frontmatter manipulation, content patching by semantic anchors, search, and Jujutsu-based version control — usable both as an imported library and as an optional standalone HTTP server.

---

## 2. Why This Library Exists

### 2.1 The problem

Interacting with an Obsidian vault programmatically requires understanding several concerns simultaneously:

- **Path safety**: Vault operations must be sandboxed to prevent escaping the vault root via `..` traversal, absolute paths, or symlink attacks.
- **Obsidian-flavored Markdown**: Files contain YAML frontmatter, wikilinks (`[[...]]`), block references (`^block-id`), and heading-based structure that generic file operations don't understand.
- **Atomic mutations**: Concurrent writes to the same file can corrupt content. Operations need serialization guarantees.
- **Version control**: Changes should be committable and undoable via Jujutsu, providing a durable history of vault mutations.

Today, any tool that wants to interact with an Obsidian vault must reimplement all of these concerns from scratch. obsidian-ops solves this by providing a single, tested, reusable library.

### 2.2 Design principles

1. **Library-first**: The primary interface is Python classes and functions. The HTTP server is optional.
2. **No LLM dependency**: obsidian-ops knows nothing about language models, agents, or AI. It is a pure vault operations library.
3. **Standalone utility**: Scripts, CLI tools, CI pipelines, and non-agent workflows can use obsidian-ops directly without pulling in any AI framework.
4. **Safe by default**: All file operations are sandboxed within the vault root. Path validation is not optional.
5. **Obsidian-aware**: Operations understand frontmatter, headings, block references, and wikilinks as first-class concepts.

### 2.3 Relationship to obsidian-agent

obsidian-agent is an LLM-powered agent framework for Obsidian vaults. It imports obsidian-ops as a dependency for all vault interactions. obsidian-ops has no knowledge of obsidian-agent — the dependency is strictly one-directional:

```
obsidian-agent  ──imports──►  obsidian-ops  ──reads/writes──►  vault directory
```

This separation means:
- obsidian-ops can be versioned, tested, and released independently.
- Other agent frameworks or tools can use obsidian-ops without any obsidian-agent dependency.
- Changes to the LLM layer never affect vault operations, and vice versa.

---

## 3. Library Scope

### 3.1 What obsidian-ops owns

1. **File CRUD** — Read, write, create, and delete files within the vault, with path sandboxing.
2. **Frontmatter operations** — Read, write, and patch YAML frontmatter fields without rewriting the entire file. Support targeted field updates (set, delete, merge) including nested paths.
3. **Content patching** — Read and write content under a specific heading or block reference, without rewriting the full file.
4. **File listing** — List files matching glob patterns, with sensible defaults (skip dotfiles, hidden directories).
5. **Content search** — Search file contents with case-insensitive matching and contextual snippets.
6. **Version control** — Commit vault state, undo the last change, and query status via Jujutsu.
7. **Mutation lock** — Serialize all write operations with a global lock to prevent concurrent mutations.
8. **Path sandboxing** — Validate all paths to ensure they stay within the vault root, with symlink traversal protection.

### 3.2 What obsidian-ops does NOT own

- **LLM interaction** — No language model calls, no agent loops, no prompt engineering. That's obsidian-agent.
- **HTTP serving** — The library provides an optional server entrypoint, but the core is importable classes. It is not a server framework.
- **Tool schemas for LLMs** — obsidian-ops does not define tool schemas (JSON Schema for function calling). obsidian-agent wraps obsidian-ops operations into LLM tool definitions.
- **URL-to-file resolution** — obsidian-ops operates on vault-relative file paths, not web URLs. The caller (e.g., obsidian-agent or a web proxy) is responsible for resolving URLs to vault paths.
- **Site generation** — No HTML generation, no static site building, no template rendering.
- **Process orchestration** — No subprocess management, no configuration for external services.

### 3.3 Optional extras (can ship later)

- A `fetch_url` utility for downloading web content into the vault.
- Dataview-compatible query support.
- Wikilink graph traversal (find backlinks, outgoing links).
- Batch operations (apply the same frontmatter change to many files).

---

## 4. Core API Design

### 4.1 Vault — Primary entry point

```python
from obsidian_ops import Vault

vault = Vault("/path/to/obsidian/vault")

# File operations
content = vault.read_file("Projects/Alpha.md")
vault.write_file("Projects/Alpha.md", content)
files = vault.list_files("*.md")
results = vault.search_files("meeting notes", glob="*.md")

# Frontmatter operations
fm = vault.get_frontmatter("Projects/Alpha.md")
vault.set_frontmatter("Projects/Alpha.md", {"status": "active", "tags": ["project"]})
vault.update_frontmatter("Projects/Alpha.md", {"status": "completed"})

# Content patching
section = vault.read_heading("Projects/Alpha.md", "## Summary")
vault.write_heading("Projects/Alpha.md", "## Summary", "Updated summary content.")
block = vault.read_block("Projects/Alpha.md", "^meeting-notes")
vault.write_block("Projects/Alpha.md", "^meeting-notes", "New block content.")

# Version control
vault.commit("Updated project status")
vault.undo()
status = vault.vcs_status()
```

### 4.2 Safety guarantees

Every operation goes through path validation before touching the filesystem:

- **No absolute paths**: `vault.read_file("/etc/passwd")` → error.
- **No traversal**: `vault.read_file("../../secrets.txt")` → error.
- **Symlink guard**: If a symlink inside the vault points outside the vault root, the operation is rejected.
- **Size limits**: Reads are capped at 512KB by default to prevent memory issues with large binary files.
- **Mutation lock**: All write operations (write_file, set_frontmatter, write_heading, commit, undo) acquire a global lock. If another write is in progress, the caller receives a "busy" error.

### 4.3 Frontmatter model

Frontmatter is represented as a Python dictionary parsed from the YAML block at the top of a markdown file:

```python
# Given a file with:
# ---
# title: My Note
# tags: [project, active]
# metadata:
#   created: 2024-01-15
# ---
# # Content here...

fm = vault.get_frontmatter("note.md")
# Returns: {"title": "My Note", "tags": ["project", "active"], "metadata": {"created": "2024-01-15"}}

# Targeted update — only changes specified fields, preserves everything else
vault.update_frontmatter("note.md", {"tags": ["project", "completed"]})

# Full replacement
vault.set_frontmatter("note.md", {"title": "New Title"})

# Delete a field
vault.delete_frontmatter_field("note.md", "metadata")
```

### 4.4 Content patching model

Content patching operates on semantic anchors within a markdown file:

```python
# Read content under a heading (includes all content until the next heading of equal or higher level)
section = vault.read_heading("note.md", "## Summary")

# Replace content under a heading
vault.write_heading("note.md", "## Summary", "This is the new summary.\n\nWith multiple paragraphs.")

# Read content associated with a block reference
block = vault.read_block("note.md", "^important-note")

# Replace content associated with a block reference
vault.write_block("note.md", "^important-note", "Updated block content. ^important-note")
```

### 4.5 Version control model

```python
# Commit current vault state with a message
vault.commit("ops: Updated project status to completed")

# Undo the last Jujutsu operation
vault.undo()

# Get current status
status = vault.vcs_status()  # Returns string output of `jj status`
```

### 4.6 Optional HTTP server

obsidian-ops ships a server entrypoint that exposes the library API over HTTP:

```bash
python -m obsidian_ops.server --vault /path/to/vault --port 9200
```

The server maps library methods to HTTP endpoints. This allows non-Python tools to interact with the vault through a stable API. The exact endpoint design follows from the library interface.

---

## 5. Project Structure

```
obsidian-ops/
  pyproject.toml
  src/
    obsidian_ops/
      __init__.py           # Public API: Vault class, exceptions
      vault.py              # Vault class — primary entry point
      sandbox.py            # Path validation and sandboxing
      frontmatter.py        # YAML frontmatter parsing and patching
      content.py            # Heading/block content patching
      search.py             # File listing and content search
      vcs.py                # Jujutsu wrapper (commit, undo, status)
      lock.py               # Global mutation lock
      errors.py             # Exception hierarchy
      server.py             # Optional HTTP server entrypoint
  tests/
    test_vault.py           # Integration tests for Vault class
    test_sandbox.py         # Path validation edge cases
    test_frontmatter.py     # Frontmatter parsing and patching
    test_content.py         # Heading/block content patching
    test_search.py          # File listing and search
    test_vcs.py             # Jujutsu wrapper tests
    test_lock.py            # Mutation lock tests
    conftest.py             # Shared fixtures (temp vault directories)
```

### 5.1 Dependencies

Core (minimal):
- `pyyaml` — YAML frontmatter parsing
- Standard library only for everything else (pathlib, os, subprocess, threading)

Optional (for HTTP server):
- `fastapi` + `uvicorn`

No LLM SDKs. No heavy frameworks. The core library should have exactly one external dependency (pyyaml).

---

## 6. Key Design Decisions

### 6.1 Synchronous API

The library API is synchronous (not async). Vault operations are filesystem I/O and subprocess calls — there is no benefit to async here, and a sync API is simpler to use from any context (scripts, CLI tools, sync web frameworks, or async frameworks via `run_in_executor`).

### 6.2 No URL resolution

obsidian-ops operates exclusively on vault-relative file paths (e.g., `Projects/Alpha.md`). It does not understand web URLs, URL routing, or how a static site generator maps URLs to files. The caller is responsible for resolving URLs to vault paths before calling obsidian-ops.

### 6.3 Frontmatter preservation

When modifying frontmatter, obsidian-ops should preserve:
- YAML key ordering (as much as possible)
- Comment blocks within frontmatter
- The exact delimiter style (`---`)
- Existing formatting/quoting preferences

This avoids noisy diffs when only one field changes.

### 6.4 Jujutsu is required for VCS features, optional otherwise

If Jujutsu (`jj`) is not installed, the VCS methods (commit, undo, vcs_status) raise a clear error. All other operations (file CRUD, frontmatter, content patching, search) work without Jujutsu. This allows obsidian-ops to be used in environments where version control is not needed.

---

## 7. Acceptance Criteria (v1)

The library is correct when:

1. All file operations are sandboxed — no absolute paths, no `..` traversal, no symlink escapes.
2. `read_file` / `write_file` work correctly for vault-relative paths, with parent directory creation on write.
3. `list_files` returns vault-relative paths matching a glob, skipping dotfiles and hidden directories.
4. `search_files` returns files containing a case-insensitive query with contextual snippets.
5. `get_frontmatter` correctly parses YAML frontmatter from markdown files.
6. `set_frontmatter` replaces frontmatter entirely; `update_frontmatter` merges fields; `delete_frontmatter_field` removes specific fields.
7. `read_heading` / `write_heading` correctly identify heading boundaries and extract/replace content.
8. `read_block` / `write_block` correctly find block references and extract/replace associated content.
9. `commit` runs `jj describe -m <message>` + `jj new` successfully.
10. `undo` runs `jj undo` successfully.
11. The mutation lock prevents concurrent write operations.
12. The optional HTTP server exposes all library operations over HTTP.
13. Comprehensive test coverage for all operations, especially path sandboxing edge cases.

---

## 8. Explicit Non-Goals for v1

- LLM interaction or agent logic
- Tool schema definitions for function calling
- URL-to-file resolution
- Site generation or HTML rendering
- Wikilink graph analysis
- Dataview query support
- Multi-vault support
- Authentication or access control
- File watching or change notification
