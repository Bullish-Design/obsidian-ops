# Context

User request completed:
- Created project template directory `.scratch/projects/18-guided-demo-script/` with all standard files.
- Added detailed walkthrough document:
  - `.scratch/projects/18-guided-demo-script/DEMO_SCRIPT.md`
- Added guided run mode in `scripts/live_vault_demo.py`:
  - `devenv shell -- ops-live-demo run --mode guided --delay 0 --no-reset`
  - pauses after each step and prompts for Enter to continue
- Updated demo docs in:
  - `demo/obsidian-ops/README.md`

Verification completed:
- `devenv shell -- uv sync --extra dev`
- `devenv shell -- ruff check scripts/live_vault_demo.py`
- `devenv shell -- ruff format --check scripts/live_vault_demo.py`
- `devenv shell -- ops-live-demo reset`
- `devenv shell -- ops-live-demo run --mode guided --delay 0 --no-reset` (TTY, Enter presses)
- `devenv shell -- ops-live-demo cleanup`
- `devenv shell -- ops-live-demo status` -> `Exists: False`

Note:
- User explicitly requested to keep existing deletions in `.scratch/projects/17-main-release-bump-tag/` as-is.
