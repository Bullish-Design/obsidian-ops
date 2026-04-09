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
