# vLLM Backend Integration — Context

- User requested project setup for running with vLLM backend at `remora-server:8000`.
- Analysis completed:
  - Core agent already supports OpenAI-compatible vLLM via settings.
  - Current defaults/demo wiring are not remora-aligned (base URL/model).
  - Verified remora backend model list is reachable at `/v1/models`.
- PLAN.md has been expanded with full implementation sequence, tests, risks, and acceptance criteria.
- Implemented first backend wiring step in `src/obsidian_ops/demo_cli.py`:
  - Added `--vllm-base-url`, `--vllm-model`, `--vllm-api-key` options to `run` and `serve`.
  - Added base URL normalization to ensure `/v1`.
  - Added model discovery preflight against `<base_url>/models` with auto-selection.
  - Wired resolved settings into `OPS_VLLM_*` env vars for server startup.
- Smoke verification:
  - `devenv shell -- timeout 20s ops-demo run --host 127.0.0.1 --port 18081 --cleanup`
  - Successfully auto-selected model from remora backend and reached app startup.
- Next action: update docs/scripts and add automated tests.
