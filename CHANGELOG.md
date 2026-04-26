# Changelog

## 0.7.0 - 2026-04-26

- Added jj git sync capability in `Vault`: readiness checks, safe sync initialization, remote configuration, fetch/push helpers, and full sync lifecycle.
- Added persistent sync metadata at `.forge/sync-state.json` and token-backed credential helper support at `.forge/git-credential.sh`.
- Added conflict-handling workflow with conflict bookmark creation and conflict state reporting.
- Added HTTP API surface under `/vcs/sync/*` for readiness, ensure, remote config, fetch, push, sync, and sync status.
- Added/expanded unit and integration tests for new VCS sync behaviors, including real jj/git local-remote round-trip coverage.
