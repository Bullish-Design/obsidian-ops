# Context

User requested a detailed demo script callable from `devenv.nix`, using a demo vault with
real-time observable mutations and reset/cleanup behavior.

Implemented:
- Added `scripts/live_vault_demo.py` with subcommands:
  - `run` (detailed, step-by-step vault mutation sequence)
  - `reset` (recreate runtime vault from demo source)
  - `cleanup` (remove generated runtime data)
  - `status` (show source/runtime paths and state)
- Wired new `devenv` script entrypoint in `devenv.nix`:
  - `ops-live-demo`
- Updated `demo/obsidian-ops/README.md` with usage instructions for the new live mutation demo.

Runtime paths:
- Source vault: `demo/obsidian-ops/vault`
- Runtime root: `.scratch/projects/16-live-demo-script/generated`
- Runtime vault: `.scratch/projects/16-live-demo-script/generated/vault`

Verification completed:
- `python scripts/live_vault_demo.py --help`
- `.devenv/state/venv/bin/python scripts/live_vault_demo.py reset`
- `.devenv/state/venv/bin/python scripts/live_vault_demo.py status`
- `.devenv/state/venv/bin/python scripts/live_vault_demo.py run --delay 0 --no-reset`
- `.devenv/state/venv/bin/python scripts/live_vault_demo.py cleanup`
- `.devenv/state/venv/bin/ruff check scripts/live_vault_demo.py`
- `.devenv/state/venv/bin/ruff format --check scripts/live_vault_demo.py`

Note:
- `devenv shell -- ...` command validation encountered long-running nix evaluation in this session.
  The `ops-live-demo` entrypoint is wired in `devenv.nix`, and the underlying script behavior is verified.
