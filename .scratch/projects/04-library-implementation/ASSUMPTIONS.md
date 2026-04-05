# Library Implementation — Assumptions

## Audience

- Maintainers and contributors implementing `obsidian_ops` from the implementation guide.

## Scope

- Build the full library and tests exactly in the 15-step order from `.scratch/projects/03-implementation-guide/IMPLEMENTATION_GUIDE.md`.
- Keep architecture local-first, single-worker for v0, and Jujutsu-backed history.

## Technical Assumptions

- Python 3.13+
- `jj` and `kiln` are installed on PATH for runtime/integration tests.
- vLLM-compatible OpenAI Chat Completions endpoint is available for live agent runs.
- Vault is a local trusted workspace initialized with `.jj/`.
