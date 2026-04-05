# Demo Scaffold — Context

- Task: replicate `ssg-gen`-style demo scaffold in `obsidian-ops` with functional run flow.
- Completed:
  - Created `demo/obsidian-ops/` scaffold with README, run script, and rich sample vault.
  - Implemented `src/obsidian_ops/demo_cli.py` (`run`, `serve`, `cleanup`).
  - Added console script entrypoint `ops-demo` in `pyproject.toml`.
- Verification:
  - `devenv shell -- uv sync --extra dev` succeeded.
  - `devenv shell -- ops-demo --help` succeeded.
  - `devenv shell -- timeout 25s ops-demo run --host 127.0.0.1 --port 18080` reached successful startup (`Application startup complete`).
  - `devenv shell -- ops-demo cleanup` removed generated demo runtime/artifacts.
- Next: commit and push changes.
