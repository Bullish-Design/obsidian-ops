# Obsidian Ops Demo

This demo provides a realistic Obsidian-style vault and a one-command local run flow for `obsidian-ops`.

## What it does

- Creates an isolated runtime copy of `demo/obsidian-ops/vault`.
- Initializes that runtime vault as a Jujutsu workspace (`jj git init`).
- Starts `obsidian-ops` with:
  - `OPS_VAULT_DIR` set to the runtime vault
  - `OPS_SITE_DIR` set to `gen/obsidian-ops/site`
- On startup, the app performs an initial Kiln build and injects overlay assets.

## Run

```bash
devenv shell -- uv sync --extra dev
devenv shell -- ops-demo run
```

Then open:

- `http://127.0.0.1:8080/`

## Alternate entrypoint

```bash
demo/obsidian-ops/run_demo.sh
```

## Cleanup generated demo artifacts

```bash
devenv shell -- ops-demo cleanup
```

Generated runtime files are written to:

- `.scratch/projects/06-demo-scaffold/generated/`
- `gen/obsidian-ops/`
