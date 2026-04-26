# Assumptions

- `obsidian-ops` is the owner of VCS mechanics; callers orchestrate only via `Vault`.
- Existing public API behavior must remain backward-compatible.
- jj is available in environments running integration VCS tests; tests should skip when absent.
- Sync readiness checks must be non-mutating.
- Retry/backoff policy is intentionally out of scope and remains caller-owned.
