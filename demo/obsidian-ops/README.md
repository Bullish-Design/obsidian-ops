# Obsidian Ops Demo

This demo provides a realistic Obsidian-style vault and a one-command local run flow for `obsidian-ops`.

## What it does

- Creates an isolated runtime copy of `demo/obsidian-ops/vault`.
- Initializes that runtime vault as a Jujutsu workspace (`jj git init`).
- Starts `obsidian-ops` with:
  - `OPS_VAULT_DIR` set to the runtime vault
  - `OPS_SITE_DIR` set to `gen/obsidian-ops/site`
- On startup, the app performs an initial Kiln build and injects overlay assets.
- Uses vLLM backend defaults for this environment:
  - base URL: `http://remora-server:8000/v1`
  - model: auto-selected from `GET /v1/models` unless provided explicitly

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

`run_demo.sh` supports env overrides:

```bash
VLLM_BASE_URL="http://remora-server:8000/v1" \
VLLM_MODEL="Qwen/Qwen3-4B-Instruct-2507-FP8" \
VLLM_API_KEY="" \
demo/obsidian-ops/run_demo.sh
```

Or with CLI flags directly:

```bash
devenv shell -- ops-demo run \
  --vllm-base-url http://remora-server:8000/v1 \
  --vllm-model Qwen/Qwen3-4B-Instruct-2507-FP8
```

## Live Vault Mutation Demo

Use this when you want to open a vault in Obsidian and watch scripted file mutations happen in real time.

The script works against a runtime copy of the demo vault:

- Source vault: `demo/obsidian-ops/vault`
- Runtime vault: `.scratch/projects/16-live-demo-script/generated/vault`

### Reset runtime vault

```bash
devenv shell -- ops-live-demo reset
```

### Run step-by-step mutation demo

```bash
devenv shell -- ops-live-demo run
```

Optional flags:

```bash
# Faster run with no pause between steps
devenv shell -- ops-live-demo run --delay 0

# Reuse current runtime state without auto-reset
devenv shell -- ops-live-demo run --no-reset

# Guided mode: pause after each step and press Enter to continue
devenv shell -- ops-live-demo run --mode guided --delay 0 --no-reset
```

Guided walkthrough reference:

- `.scratch/projects/18-guided-demo-script/DEMO_SCRIPT.md`

### Inspect or cleanup

```bash
devenv shell -- ops-live-demo status
devenv shell -- ops-live-demo cleanup
```

## Cleanup generated demo artifacts

```bash
devenv shell -- ops-demo cleanup
```

Generated runtime files are written to:

- `.scratch/projects/06-demo-scaffold/generated/`
- `gen/obsidian-ops/`

## Troubleshooting

- `requested model ... is unavailable`:
  - Run `curl -s http://remora-server:8000/v1/models` and choose a valid `id`.
- `failed to query vLLM models ...`:
  - Verify host/network reachability to `remora-server:8000`.
  - Try overriding with `--vllm-base-url`.
