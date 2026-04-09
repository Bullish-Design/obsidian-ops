# Decisions

## Step 1: Keep Server Support Optional, But Include It In Dev Installs

- Decision: keep the package library-first and leave FastAPI/Uvicorn in the
  `server` extra.
- Implementation:
  - duplicate the server dependencies into the `dev` extra so
    `devenv shell -- uv sync --extra dev` installs a full test-ready
    environment,
  - lazy-load FastAPI and Uvicorn inside `src/obsidian_ops/server.py` so core
    library imports and `obsidian-ops-server --help` do not fail just because
    the server extra is missing.
- Rationale:
  - preserves the smaller dependency surface for library-only consumers,
  - makes the default documented development flow match the full repository test
    suite,
  - gives the CLI entrypoint an explicit server-install contract instead of a
    raw import failure.

## Step 2: Frontmatter Updates Merge Nested Mappings Recursively

- Decision: `Vault.update_frontmatter()` should deep-merge nested mappings.
- Contract:
  - top-level keys in the update payload still overwrite top-level scalars,
    sequences, or mappings when the target value is not also a mapping,
  - when both the existing value and the update value are mappings, merge them
    recursively,
  - unmentioned sibling keys remain intact,
  - if the file has no frontmatter, create a new frontmatter mapping from the
    update payload,
  - updating frontmatter never changes the markdown body,
  - delete semantics are explicitly out of scope for `update_frontmatter()`;
    callers must use dedicated delete operations instead.
- Rationale:
  - upstream callers need predictable partial updates to nested metadata without
    wiping unrelated keys,
  - keeping replacement semantics for non-mapping values preserves simple
    existing behavior.
