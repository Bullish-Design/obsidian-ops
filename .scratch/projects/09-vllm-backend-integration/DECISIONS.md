# vLLM Backend Integration — Decisions

1. Keep core `config.py` defaults unchanged; apply remora defaults in demo CLI.
   - Rationale: preserves generic library behavior while making the demo path work out-of-the-box for this environment.
2. Add runtime model preflight in demo CLI via `/v1/models` before starting server.
   - Rationale: fail fast on model mismatch/connectivity issues and avoid opaque runtime failures during first job execution.
