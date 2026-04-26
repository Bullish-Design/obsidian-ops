# Context

Date: 2026-04-26
Project: `21-jj-git-functionality-refactor`

## Current State

- Created branch: `21-jj-git-functionality-refactor`.
- Loaded and analyzed `VCS_REFACTOR_PLAN_V2.md`.
- Inspected current `vcs.py`, `vault.py`, `server.py`, `__init__.py`, and test suites.
- Initialized project tracking files for this project.
- Completed Phase 1:
  - Added `VCSReadiness`, `ReadinessCheck`, and `SyncResult` in `vcs.py`
  - Extended `JJ` with git bridge, rebase, bookmark, remote, and log wrapper methods
  - Extended `JJ._run()` to accept optional env overrides (merged onto process env)
  - Updated `__init__.py` exports
  - Added unit tests for new `JJ` methods and env pass-through in `tests/test_vcs.py`
  - Verified with `devenv shell -- pytest tests/test_vcs.py -q`
- Completed Phase 2:
  - Added `Vault._is_git_dirty()`, `Vault.check_sync_readiness()`, and `Vault.ensure_sync_ready()`
  - Implemented safe auto-init policy and non-mutating readiness checks
  - Added readiness matrix tests for no-vcs, git-only clean/dirty, jj-only, and colocated states
  - Verified with `devenv shell -- pytest tests/test_vcs.py -q`
- Completed Phase 3:
  - Added sync remote configuration to `Vault.configure_sync_remote()` with URL validation
  - Added token-backed credential helper management at `.forge/git-credential.sh` (0700)
  - Added persisted sync state read/write via `.forge/sync-state.json` with atomic writes
  - Added `sync_fetch()`, `sync_push()`, `sync()`, `sync_status()`, and conflict bookmark helper
  - Added unit tests for happy path, conflict path, fetch failure, credential helper behavior
  - Verified with `devenv shell -- pytest tests/test_vcs.py -q`

## Next

Implement Phase 4:
- add `/vcs/sync/*` server models and endpoints
- add server endpoint tests for readiness/ensure/remote/fetch/push/sync/status
- run focused server tests, commit, and push
