# vLLM Backend Integration — Plan

## ABSOLUTE RULE

- NO SUBAGENTS.

## Current Library Analysis

1. Backend wiring exists in core runtime:
   - `src/obsidian_ops/config.py` exposes `OPS_VLLM_BASE_URL`, `OPS_VLLM_MODEL`, `OPS_VLLM_API_KEY`.
   - `src/obsidian_ops/agent.py` uses `openai.AsyncOpenAI(base_url=..., api_key=...)` and `model=settings.vllm_model`.
2. Current defaults are not aligned with the active remora backend:
   - `vllm_base_url` default is `http://127.0.0.1:8000/v1`.
   - `vllm_model` default is `local-model`.
3. Demo path currently does not configure backend values:
   - `src/obsidian_ops/demo_cli.py` sets vault/site/host/port env only.
   - `demo/obsidian-ops/README.md` has no remora backend configuration guidance.
4. Backend reachability check confirms live vLLM endpoint:
   - `curl http://remora-server:8000/v1/models` returns model list including `Qwen/Qwen3-4B-Instruct-2507-FP8`.

## Implementation Goal

Make the project run reliably with vLLM at `remora-server:8000` (OpenAI-compatible API), especially through the demo workflow, without regressing existing local configuration flexibility.

## Scope

1. Ensure demo/runtime uses remora backend by default.
2. Ensure model selection is valid for the running vLLM instance.
3. Keep explicit env override behavior for advanced users.
4. Add regression tests and docs for the new backend flow.

## Non-Goals

1. Redesigning the agent/tool loop.
2. Adding authentication frameworks or multi-backend routing.
3. Changing queue/worker architecture.

## Detailed Implementation Plan

1. Decide defaulting strategy (design decision checkpoint).
   - Preferred: keep core library defaults in `config.py` unchanged for generic use, and set remora defaults in demo CLI.
   - Alternative (only if requested): change global defaults in `config.py` to remora host/model.
   - Record decision in `DECISIONS.md`.

2. Add vLLM options to demo CLI (`src/obsidian_ops/demo_cli.py`).
   - Add `run`/`serve` options:
     - `--vllm-base-url` default `http://remora-server:8000/v1`
     - `--vllm-model` default empty/auto
     - `--vllm-api-key` default empty
   - Set env vars in `_run_server`:
     - `OPS_VLLM_BASE_URL`
     - `OPS_VLLM_MODEL` (resolved)
     - `OPS_VLLM_API_KEY` (if provided)

3. Add model discovery/preflight in demo CLI.
   - Add helper to query `<base_url>/models` (or `/v1/models` fallback normalization).
   - If `--vllm-model` is provided, validate it exists and fail fast with clear message if not.
   - If `--vllm-model` is omitted, auto-select first available model ID and print selection.
   - Provide clear error text for connectivity issues (DNS, timeout, non-200, bad JSON).

4. Normalize and validate base URL handling.
   - In demo CLI, accept `http://remora-server:8000` and normalize to `.../v1`.
   - Optionally add a `config.py` validator for `vllm_base_url` normalization if we want this behavior globally.
   - Ensure normalization does not break explicit custom paths.

5. Update demo docs.
   - `demo/obsidian-ops/README.md`:
     - Document remora default backend behavior.
     - Document override flags (`--vllm-base-url`, `--vllm-model`, `--vllm-api-key`).
     - Add troubleshooting section for “model not found” and “cannot connect”.
   - `demo/obsidian-ops/run_demo.sh`:
     - Optionally plumb env passthrough (`VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`) to CLI flags.

6. Add tests (TDD-first for new logic).
   - New `tests/test_demo_cli.py` with mocked subprocess/network:
     - Base URL normalization behavior.
     - Auto model selection from `/v1/models`.
     - Explicit model validation success/failure paths.
     - Env wiring passed to uvicorn invocation.
   - Extend `tests/test_config.py` only if global normalization/defaults change.

7. Verification workflow (against real remora backend).
   - `devenv shell -- uv sync --extra dev`
   - `devenv shell -- ops-demo --help`
   - `devenv shell -- ops-demo run --host 127.0.0.1 --port 8080` (or bounded timeout smoke run)
   - Submit a real `/api/jobs` request and confirm:
     - agent starts
     - at least one tool call occurs
     - job reaches terminal success/failure with meaningful summary/error
   - Run full tests: `devenv shell -- pytest tests/ -q`

## Acceptance Criteria

1. `ops-demo run` works out of the box in this environment with `remora-server:8000` backend.
2. Backend model mismatch is detected early with actionable errors.
3. Users can override backend URL/model/api key without code changes.
4. Automated tests cover demo backend selection/wiring behavior.
5. Documentation clearly describes backend defaults and overrides.

## Risks and Mitigations

1. Risk: vLLM model list endpoint shape differs.
   - Mitigation: robust parsing and explicit validation error paths.
2. Risk: network hostname unavailable in some environments.
   - Mitigation: fallback/override flags + clear diagnostics.
3. Risk: changing global defaults could break existing users.
   - Mitigation: prefer demo-scoped defaults unless explicitly requested.

## Rollout Order

1. Implement and test demo CLI backend options/model discovery.
2. Update demo docs/scripts.
3. Run integration verification against remora server.
4. Run full tests and finalize.

## ABSOLUTE RULE

- NO SUBAGENTS.
