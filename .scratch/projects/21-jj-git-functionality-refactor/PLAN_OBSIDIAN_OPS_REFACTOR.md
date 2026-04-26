# Obsidian-Ops: jj Git Sync Refactor Plan

## Objective
Extend `obsidian-ops` to support jj-native GitHub sync via the jj git bridge. All VCS
logic — subprocess wrappers, migration detection, conflict handling, remote auth — lives
in `obsidian-ops`. The `obsidian-agent` boundary rule is absolute: the agent orchestrates
the `Vault` API but never owns raw VCS or filesystem mechanics.

Capabilities added:
- jj git bridge sync (fetch / rebase / push)
- GitHub token-auth remote configuration
- Hybrid migration from existing `.git` states
- Conflict bookmark creation on sync failure
- Sync status reporting via Vault API

## Non-Goals
- Reworking Forge UI/overlay behavior
- Changing the existing `vault.commit()` / `vault.undo_last_change()` contract
- Building host-specific deployment scripts
- Event-driven sync worker or background task scheduling (agent-side concern, out of scope)

## Desired End State
1. `Vault` exposes a sync surface that callers (agent, CLI, tests) can use:
   - `vault.vcs_status() -> VCSStatus` — preflight readiness check
   - `vault.sync_fetch()` — fetch from remote via jj git bridge
   - `vault.sync_push()` — push to remote via jj git bridge
   - `vault.sync() -> SyncResult` — full fetch+rebase+push cycle
   - `vault.create_conflict_bookmark(prefix) -> str` — snapshot current state on conflict
   - `vault.configure_remote(url, token)` — set/update GitHub remote with token auth
   - `vault.sync_status() -> SyncStatusInfo` — last sync result, conflict flag, timestamps
2. Migration detection returns a simple enum (`ready`, `migration_needed`, `error`) so
   callers can act without understanding internal VCS state.
3. Existing `vault.commit()` and `vault.undo_last_change()` remain stable and unchanged.

## API / Module Design

### 1) New Vault Methods

```python
class VCSStatus(Enum):
    READY = "ready"                     # jj + git bridge fully configured
    MIGRATION_NEEDED = "migration_needed"  # detected state needs manual intervention
    ERROR = "error"                     # fatal — cannot operate

@dataclass
class SyncResult:
    ok: bool
    fetched: bool
    pushed: bool
    conflict: bool
    conflict_bookmark: str | None       # e.g. "sync-conflict/2026-04-26T..."
    error: str | None

@dataclass
class SyncStatusInfo:
    enabled: bool
    vcs_status: VCSStatus
    last_sync_at: datetime | None
    last_sync_ok: bool | None
    conflict_active: bool
    conflict_bookmark: str | None
```

Methods on `Vault`:
- `vcs_status() -> VCSStatus` — detect current state, return readiness enum
- `configure_remote(url: str, token: str | None = None) -> None`
- `sync_fetch() -> None` — wraps `jj git fetch`
- `sync_push() -> None` — wraps `jj git push`
- `sync(conflict_prefix: str = "sync-conflict") -> SyncResult` — full cycle
- `create_conflict_bookmark(prefix: str) -> str` — create timestamped bookmark
- `sync_status() -> SyncStatusInfo` — query last sync state

### 2) Internal Migration State Machine

Detect and classify vault VCS state (internal to ops, not exposed as public API):

| Detected State       | `vcs_status()` returns | Auto-action              |
|----------------------|------------------------|--------------------------|
| No `.git`, no `.jj`  | `READY`               | `jj git init --colocate` |
| `.jj` present, configured | `READY`          | None                     |
| `.git` only, clean   | `READY`               | `jj git init --colocate` |
| `.git` only, dirty   | `MIGRATION_NEEDED`    | None (unsafe)            |
| Both `.git` + `.jj`, inconsistent | `MIGRATION_NEEDED` | None          |
| Unrecognized state   | `ERROR`               | None                     |

Rules:
- Auto-migrate only when safe (no uncommitted changes, no ambiguous state)
- Never mutate dirty or inconsistent states without explicit operator action
- Log detailed diagnostics for `MIGRATION_NEEDED` and `ERROR` states

### 3) jj Command Wrappers

Internal module (e.g. `obsidian_ops.vcs.jj_commands`):
- `jj_git_fetch(repo_path, *, timeout)` — fetch from configured remote
- `jj_git_push(repo_path, *, branch, timeout)` — push bookmark/branch
- `jj_rebase(repo_path, *, timeout)` — rebase working copy on fetched changes
- `jj_bookmark_create(repo_path, name, *, timeout)` — create named bookmark
- `jj_git_remote_set(repo_path, name, url, *, timeout)` — add/update remote
- `jj_status(repo_path, *, timeout)` — query repo status for conflict detection

All wrappers:
- Use existing `jj_bin` and `jj_timeout` from Vault config
- Raise `VCSError` on non-zero exit with stderr context
- Run via `subprocess.run()` with timeout enforcement

### 4) Conflict Policy

On rebase conflict during `sync()`:
1. Create bookmark: `{prefix}/{ISO-timestamp}-{short-change-id}`
2. Record conflict metadata in `SyncStatusInfo` (in-memory, queryable)
3. Return `SyncResult(conflict=True, conflict_bookmark=...)` — caller decides what to do
4. Do NOT block or raise — the vault remains usable for reads and writes

### 5) Remote Auth

`configure_remote(url, token)`:
- If token provided, embed in remote URL: `https://{token}@github.com/...`
- Update existing remote if already configured, add if not
- Validate URL format before writing

## Implementation Phases

### Phase A: Foundations
1. Add `VCSStatus`, `SyncResult`, `SyncStatusInfo` data types.
2. Add `vcs_status()` stub that returns `READY` if `.jj` exists, `ERROR` otherwise.
3. Add `sync()`, `sync_fetch()`, `sync_push()` stubs that raise `NotImplementedError`.
4. Add `sync_status()` returning disabled state.
5. Bump minor version. Ensure existing tests pass unchanged.

### Phase B: Migration Engine
1. Implement full `vcs_status()` detection logic (`.git`/`.jj` presence, dirty checks).
2. Implement auto-migration for safe states (`jj git init --colocate`).
3. Return `MIGRATION_NEEDED` for unsafe states with diagnostic logging.
4. Unit tests for every detection case (use temp dirs with synthetic `.git`/`.jj` states).

### Phase C: jj Sync Engine
1. Implement jj command wrapper module.
2. Implement `configure_remote()`.
3. Implement `sync_fetch()` and `sync_push()`.
4. Implement `sync()` full cycle: fetch → rebase → push, with conflict detection.
5. Implement `create_conflict_bookmark()`.
6. Add retry/backoff policy for transient failures (network timeouts).
7. Unit tests with mocked subprocess calls.

### Phase D: Integration & Status
1. Wire `sync_status()` to track last sync result in-memory.
2. Add integration tests using temporary git repos as remotes.
3. Test full cycle: init → configure remote → write file → commit → sync → verify remote.
4. Test conflict path: diverge remote → sync → verify bookmark created.

## Test Matrix

| Scenario                                  | Expected Outcome                        |
|-------------------------------------------|-----------------------------------------|
| Empty vault, no VCS                       | `vcs_status()` → `READY`, auto-inits jj |
| `.jj` present and configured              | `vcs_status()` → `READY`, no-op         |
| `.git` only, clean working tree           | `vcs_status()` → `READY`, auto-colocate |
| `.git` only, dirty working tree           | `vcs_status()` → `MIGRATION_NEEDED`     |
| `.git` + `.jj` inconsistent               | `vcs_status()` → `MIGRATION_NEEDED`     |
| `sync()` with token auth                  | Push succeeds, `SyncResult.ok=True`     |
| `sync()` with remote divergence           | Conflict bookmark created, non-blocking  |
| `sync()` with network failure             | `SyncResult.ok=False`, error message     |
| `sync()` with auth failure                | `SyncResult.ok=False`, clear auth error  |
| `sync_fetch()` succeeds, `sync_push()` fails | Partial failure reported correctly   |
| `commit()` + `undo_last_change()` unchanged | Existing behavior unaffected          |
| `sync_status()` after successful sync     | Timestamps and ok flag correct           |
| `sync_status()` after conflict            | `conflict_active=True`, bookmark set     |

## Rollout Strategy
1. Ship behind `vcs_status()` gating — callers check readiness before calling `sync()`.
2. Agent-side feature flag (`AGENT_SYNC_ENABLED`) controls whether agent calls sync at all.
3. Validate in staging with known clean vault + test remote.
4. Graduate to default-on after rollout evidence.

## Deliverables
- `obsidian_ops.vcs.jj_commands` — subprocess wrapper module
- `Vault` sync methods — public API additions
- Migration detection logic — internal to Vault init / `vcs_status()`
- Data types — `VCSStatus`, `SyncResult`, `SyncStatusInfo`
- Unit tests — migration states, command wrappers (mocked), sync cycle
- Integration tests — temp repos, full sync round-trip
- Changelog entry with migration notes
