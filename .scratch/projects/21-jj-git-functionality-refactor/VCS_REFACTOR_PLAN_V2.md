# Obsidian-Ops: jj Git Sync — V2 Implementation Plan

## Objective

Extend `obsidian-ops` with bidirectional GitHub sync via the jj git bridge. All VCS
logic — subprocess wrappers, readiness detection, conflict handling, remote
configuration — lives in `obsidian-ops`. The `obsidian-agent` boundary rule is absolute:
the agent orchestrates the `Vault` API but never owns raw VCS or filesystem mechanics.

### Capabilities Added

- Sync readiness detection (classify vault VCS state without side effects)
- Safe auto-initialization for clean vaults (`jj git init --colocate`)
- jj git bridge sync cycle (fetch → rebase → push)
- Conflict bookmark creation on rebase failure (non-blocking)
- Credential-helper-based remote auth (no tokens in URLs)
- Persistent sync state (survives restarts, multi-process visible)
- Server HTTP endpoints for all new operations

### Non-Goals

- Reworking Forge UI/overlay behavior
- Changing `vault.commit()`, `vault.undo_last_change()`, or `vault.vcs_status()`
- Building host-specific deployment scripts
- Event-driven sync worker or background scheduling (agent-side concern)
- Retry/backoff logic (caller's responsibility — document, don't implement)

### Design Principles

1. **Extend, don't restructure.** The codebase is clean and consistent. New code follows
   the same patterns: flat modules, thin `JJ` class wrappers, Vault methods that compose
   them, frozen dataclasses for results.
2. **Zero breaking changes.** Every existing method signature, import path, and public
   export remains unchanged.
3. **Read-only checks, explicit mutations.** Methods that inspect state never modify it.
   Methods that modify state have names that make the side effect obvious.
4. **Minimal public surface.** Only expose what callers need. Implementation details
   (conflict bookmark creation, sync state persistence) stay private.
5. **Caller owns retry policy.** The library reports failure; the caller decides whether
   and how to retry.

---

## API Design

### New Data Types

All defined in `vcs.py`, alongside the existing `UndoResult`:

```python
from enum import Enum

class VCSReadiness(Enum):
    """Whether the vault is ready for sync operations."""
    READY = "ready"                        # jj workspace present, git bridge functional
    MIGRATION_NEEDED = "migration_needed"  # unsafe state, manual intervention required
    ERROR = "error"                        # fatal, cannot determine state

@dataclass(frozen=True)
class ReadinessCheck:
    """Result of inspecting vault VCS state."""
    status: VCSReadiness
    detail: str | None = None              # diagnostic for non-READY states

@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync cycle."""
    ok: bool                               # True if full cycle completed without error
    conflict: bool = False                 # True if rebase produced conflicts
    conflict_bookmark: str | None = None   # bookmark name if conflict snapshot created
    error: str | None = None               # human-readable error if ok=False
```

Design notes:
- **`VCSReadiness`**, not `VCSStatus` — avoids collision with the existing
  `vault.vcs_status() -> str` method.
- **`SyncResult`** omits the V1 plan's `fetched`/`pushed` booleans — their semantics
  were ambiguous ("attempted" vs "succeeded"). The `ok` field covers the success case;
  `error` provides detail on failure. If finer granularity is needed later, add a
  `steps: list[StepResult]` field rather than ambiguous bools.
- All dataclasses are `frozen=True`, matching every existing dataclass in the codebase.

### New `JJ` Class Methods

Added directly to the existing `JJ` class in `vcs.py`. Each wraps `self._run()` —
identical pattern to `describe()`, `new()`, `undo()`, etc.

```python
class JJ:
    # ... existing methods unchanged ...

    def git_init_colocate(self) -> str:
        """Initialize a colocated jj+git workspace."""
        return self._run("git", "init", "--colocate")

    def git_fetch(self, *, remote: str = "origin") -> str:
        """Fetch from a git remote."""
        return self._run("git", "fetch", "--remote", remote)

    def git_push(self, *, remote: str = "origin", bookmark: str | None = None,
                 allow_new: bool = False) -> str:
        """Push to a git remote.

        Args:
            remote: Remote name (default "origin").
            bookmark: Specific bookmark to push. If None, pushes all
                      tracked bookmarks (jj default behavior).
            allow_new: If True, allow creating new remote bookmarks.
        """
        args = ["git", "push", "--remote", remote]
        if bookmark:
            args.extend(["-b", bookmark])
        if allow_new:
            args.append("--allow-new")
        return self._run(*args)

    def rebase(self, *, destination: str = "trunk()") -> str:
        """Rebase the current change onto a destination revision."""
        return self._run("rebase", "-d", destination)

    def bookmark_create(self, name: str, *, revision: str = "@") -> str:
        """Create a bookmark at the given revision."""
        return self._run("bookmark", "create", name, "-r", revision)

    def bookmark_list(self) -> str:
        """List all bookmarks."""
        return self._run("bookmark", "list")

    def git_remote_add(self, name: str, url: str) -> str:
        """Add a git remote."""
        return self._run("git", "remote", "add", name, url)

    def git_remote_set_url(self, name: str, url: str) -> str:
        """Update an existing git remote URL."""
        # jj doesn't have set-url; remove + re-add
        self._run("git", "remote", "remove", name)
        return self._run("git", "remote", "add", name, url)

    def git_remote_list(self) -> str:
        """List configured git remotes."""
        return self._run("git", "remote", "list")

    def log(self, *, revset: str = "@", template: str = "builtin_log_oneline",
            no_graph: bool = True) -> str:
        """Query the jj log."""
        args = ["log", "-r", revset, "-T", template]
        if no_graph:
            args.append("--no-graph")
        return self._run(*args)
```

### New Vault Methods

All additive — no existing method signatures change.

```python
class Vault:
    # ... existing methods unchanged ...

    def check_sync_readiness(self) -> ReadinessCheck:
        """Inspect VCS state and return readiness for sync. Read-only — never mutates."""

    def ensure_sync_ready(self) -> ReadinessCheck:
        """Ensure the vault is ready for sync, auto-initializing if safe.

        Safe auto-init cases:
        - No .git, no .jj → runs jj git init --colocate
        - .git only, clean working tree → runs jj git init --colocate

        Unsafe cases (returns MIGRATION_NEEDED, no mutation):
        - .git only, dirty working tree
        - .git + .jj both present but inconsistent

        Fatal cases (returns ERROR):
        - Unrecognized VCS state
        """

    def configure_sync_remote(self, url: str, *, token: str | None = None,
                               remote: str = "origin") -> None:
        """Configure (or update) a git remote for sync.

        If token is provided, installs a credential helper script at
        .forge/git-credentials.sh that supplies the token via GIT_ASKPASS.
        The credential helper is scoped to this vault only.

        Args:
            url: Remote URL (e.g. "https://github.com/user/repo.git").
            token: GitHub personal access token. If None, relies on
                   ambient git credential configuration.
            remote: Remote name (default "origin").
        """

    def sync_fetch(self, *, remote: str = "origin") -> None:
        """Fetch from the configured git remote via jj git bridge."""

    def sync_push(self, *, remote: str = "origin") -> None:
        """Push tracked bookmarks to the git remote via jj git bridge."""

    def sync(self, *, remote: str = "origin",
             conflict_prefix: str = "sync-conflict") -> SyncResult:
        """Run a full sync cycle: fetch → rebase → push.

        On rebase conflict:
        1. Creates a bookmark: {prefix}/{ISO-timestamp}
        2. Persists conflict state to .forge/sync-state.json
        3. Returns SyncResult(conflict=True, ...) — does NOT raise

        The vault remains fully usable for reads and writes after a conflict.
        """

    def sync_status(self) -> dict[str, Any]:
        """Return the persisted sync state from .forge/sync-state.json.

        Returns an empty dict if no sync has been performed yet.
        """
```

### Credential Handling

Instead of embedding tokens in remote URLs (security anti-pattern — tokens leak via
process listings, git config, referer headers), use git's credential helper mechanism:

1. `configure_sync_remote()` writes a minimal script to `.forge/git-credential.sh`:
   ```bash
   #!/bin/sh
   echo "password=${TOKEN}"
   echo "username=x-access-token"
   ```
2. Sets the `GIT_ASKPASS` environment variable when running jj git commands that need
   auth (fetch, push). This is done by extending `JJ._run()` to accept an optional
   `env` dict merged onto `os.environ`.
3. The credential script has `0700` permissions (owner-only).
4. The token never appears in remote URLs, git config, or process arguments.

Alternative: if the caller has already configured `git credential-store` or a system
keychain, `token=None` skips credential helper setup entirely and jj uses ambient auth.

### Sync State Persistence

Sync metadata persists to `.forge/sync-state.json` inside the vault:

```json
{
  "last_sync_at": "2026-04-26T12:34:56+00:00",
  "last_sync_ok": true,
  "conflict_active": false,
  "conflict_bookmark": null
}
```

- Written atomically after every `sync()` call (write to temp file, then rename).
- Read by `sync_status()` — returns the raw dict, no special data type.
- Survives process restarts and is visible to other Vault instances.
- Lives under `.forge/` (the existing convention for ops metadata, matching
  `.forge/templates/`).

### Bookmark Push Semantics

The `sync()` cycle must be explicit about what gets pushed. The default jj behavior
(push all tracked bookmarks) is correct for our use case:

- `ensure_sync_ready()` creates a colocated workspace where jj tracks the `main`
  bookmark by default.
- `commit()` (existing) creates changes on the working copy; `jj new` advances the
  working copy, leaving the committed change behind.
- `sync_push()` pushes the tracked `main` bookmark, which includes all finalized
  changes.
- If there are no tracked bookmarks (e.g., fresh repo with no commits), `git_push()`
  uses `--allow-new` to create the remote bookmark.

For the conflict bookmark case, the conflict bookmark is pushed explicitly by name
with `--allow-new` so the remote has a record of the conflict snapshot.

---

## Readiness Detection Logic

`check_sync_readiness()` — pure filesystem inspection, never mutates:

| Detected State                     | Returns                | Detail Message                     |
|------------------------------------|------------------------|------------------------------------|
| `.jj/` present, git remote configured | `READY`             | `None`                             |
| `.jj/` present, no git remote     | `READY`               | `"no remote configured"`           |
| No `.git/`, no `.jj/`             | `MIGRATION_NEEDED`     | `"no vcs initialized"`             |
| `.git/` only, clean working tree  | `MIGRATION_NEEDED`     | `"git-only, safe to colocate"`     |
| `.git/` only, dirty working tree  | `MIGRATION_NEEDED`     | `"git-only with uncommitted changes"` |
| `.git/` + `.jj/` both present     | `MIGRATION_NEEDED`     | `"colocated state needs verification"` |
| Detection error                    | `ERROR`               | Error message from exception       |

`ensure_sync_ready()` — acts on the detection result:

| `check_sync_readiness()` result    | `ensure_sync_ready()` action           | Returns        |
|------------------------------------|----------------------------------------|----------------|
| `READY`                            | No-op                                  | `READY`        |
| `"no vcs initialized"`            | `jj git init --colocate`               | `READY`        |
| `"git-only, safe to colocate"`    | `jj git init --colocate`               | `READY`        |
| `"git-only with uncommitted..."`  | No-op (unsafe)                         | `MIGRATION_NEEDED` |
| `"colocated state needs..."`      | No-op (ambiguous)                      | `MIGRATION_NEEDED` |
| `ERROR`                            | No-op                                  | `ERROR`        |

Rules:
- Auto-migrate **only** when provably safe (no uncommitted changes, no ambiguous state).
- Never mutate dirty or inconsistent states without explicit operator action.
- Log detailed diagnostics for `MIGRATION_NEEDED` and `ERROR` via stdlib `logging`.

---

## Conflict Policy

On rebase conflict during `sync()`:

1. Detect conflict via `jj log` checking for conflict markers in the working copy.
2. Create bookmark: `{conflict_prefix}/{ISO-timestamp}` at the current change.
3. Persist conflict metadata to `.forge/sync-state.json`.
4. Return `SyncResult(ok=False, conflict=True, conflict_bookmark="sync-conflict/2026-04-26T12:34:56")`.
5. Do **not** raise or block — the vault remains usable for reads and writes.

The caller (agent or CLI) decides how to handle the conflict: notify the user, attempt
resolution, or simply record it for later.

---

## Server Endpoints

New routes in `server.py`, following the existing pattern of Pydantic request/response
models and exception handlers:

| Method | Path                   | Vault Method              | Request Body          | Response                |
|--------|------------------------|---------------------------|-----------------------|-------------------------|
| GET    | `/vcs/sync/readiness`  | `check_sync_readiness()`  | —                     | `{status, detail}`      |
| POST   | `/vcs/sync/ensure`     | `ensure_sync_ready()`     | —                     | `{status, detail}`      |
| PUT    | `/vcs/sync/remote`     | `configure_sync_remote()` | `{url, token?, remote?}` | `{status: "ok"}`     |
| POST   | `/vcs/sync/fetch`      | `sync_fetch()`            | `{remote?}`           | `{status: "ok"}`        |
| POST   | `/vcs/sync/push`       | `sync_push()`             | `{remote?}`           | `{status: "ok"}`        |
| POST   | `/vcs/sync`            | `sync()`                  | `{remote?, conflict_prefix?}` | `SyncResult` fields |
| GET    | `/vcs/sync/status`     | `sync_status()`           | —                     | sync-state.json content |

All existing endpoints remain unchanged. New endpoints are nested under `/vcs/sync/` to
clearly scope the sync surface.

---

## Public API Exports

New additions to `__init__.py` `__all__`:

```python
# New exports
"VCSReadiness",       # Enum: READY / MIGRATION_NEEDED / ERROR
"ReadinessCheck",     # Dataclass: status + detail
"SyncResult",         # Dataclass: ok + conflict + error
```

Not exported (internal):
- Credential helper logic
- Sync state file read/write
- Conflict bookmark creation

---

## Implementation Phases

### Phase 1: JJ Class Extensions + Data Types

**Goal:** All new subprocess wrappers and data types in place, fully tested.

Changes:
- Add `VCSReadiness`, `ReadinessCheck`, `SyncResult` to `vcs.py`
- Add all new `JJ` methods: `git_init_colocate`, `git_fetch`, `git_push`, `rebase`,
  `bookmark_create`, `bookmark_list`, `git_remote_add`, `git_remote_set_url`,
  `git_remote_list`, `log`
- Export new types from `__init__.py`

Tests (`test_vcs.py`):
- Each new `JJ` method tested with mocked `subprocess.run` (existing pattern)
- Verify correct argument construction, return values, error propagation

Impact: Zero — no existing behavior changes.

### Phase 2: Readiness Detection + Auto-Init

**Goal:** `check_sync_readiness()` and `ensure_sync_ready()` fully operational.

Changes:
- Implement `check_sync_readiness()` on `Vault` — pure filesystem inspection
- Implement `ensure_sync_ready()` on `Vault` — calls `jj git init --colocate` for safe
  states only
- Add `_is_git_dirty(path)` helper (runs `git status --porcelain` or inspects index)

Tests (`test_vcs.py`):
- Temp dir with no `.git`/`.jj` → `MIGRATION_NEEDED` (check) → `READY` (ensure)
- Temp dir with `.jj` present → `READY` (both)
- Temp dir with `.git` only, clean → `MIGRATION_NEEDED` (check) → `READY` (ensure)
- Temp dir with `.git` only, dirty → `MIGRATION_NEEDED` (both, ensure does not mutate)
- Temp dir with `.git` + `.jj` → `MIGRATION_NEEDED` (both)
- Verify `check_sync_readiness()` never creates `.jj/` directory
- Verify `ensure_sync_ready()` creates `.jj/` only in safe cases

Impact: Zero — no existing behavior changes.

### Phase 3: Sync Operations

**Goal:** Full fetch → rebase → push cycle with conflict handling.

Changes:
- Implement `configure_sync_remote()` with credential helper approach
  - Write `.forge/git-credential.sh` with token
  - Extend `JJ._run()` to accept optional `env` dict
  - Validate URL format before writing
- Implement `sync_fetch()` — wraps `JJ.git_fetch()`
- Implement `sync_push()` — wraps `JJ.git_push()`
- Implement `sync()` — full cycle:
  1. `git_fetch()`
  2. `rebase(destination="trunk()")`
  3. Check for conflicts via `log()`
  4. If conflict: `_create_conflict_bookmark()`, write sync state, return conflict result
  5. If clean: `git_push()`, write sync state, return success result
- Implement `_create_conflict_bookmark()` — private, creates timestamped bookmark
- Implement `_write_sync_state()` / `_read_sync_state()` — atomic JSON file I/O
- Implement `sync_status()` — reads `.forge/sync-state.json`

Tests (`test_vcs.py`):
- `sync()` happy path: mock JJ methods, verify call order and result
- `sync()` fetch failure: verify `SyncResult(ok=False, error=...)`
- `sync()` rebase conflict: verify bookmark created, result has conflict info
- `sync()` push failure after successful rebase: verify error reported
- `configure_sync_remote()`: verify credential helper written with correct permissions
- `configure_sync_remote()` with `token=None`: verify no credential helper
- `sync_status()` with no prior sync: verify empty dict
- `sync_status()` after sync: verify persisted state matches

Impact: Zero — no existing behavior changes.

### Phase 4: Server Endpoints + Integration Tests

**Goal:** HTTP surface for all sync operations; end-to-end validation.

Changes to `server.py`:
- Add request/response models for sync endpoints
- Add all routes from the Server Endpoints table above
- Reuse existing exception handler for `VCSError`

Tests (`test_server.py`):
- Each new endpoint tested (status codes, response shapes, error cases)

Integration tests (`test_integration.py`):
- Full round-trip with real jj + git:
  1. Create temp vault → `ensure_sync_ready()` → verify `.jj/` created
  2. Create bare git repo as remote → `configure_sync_remote()`
  3. Write file → `commit()` → `sync()` → verify commit in remote
  4. Push change to remote from outside → `sync()` → verify change in vault
- Conflict scenario:
  1. Diverge remote and local → `sync()` → verify conflict bookmark exists
  2. Verify `sync_status()` shows `conflict_active: true`
- Verify existing operations (`commit`, `undo_last_change`, `vcs_status`) unchanged

Final:
- Update `__init__.py` exports
- Bump version
- Changelog entry

---

## Test Matrix

| Scenario | Expected Outcome | Test Location |
|---|---|---|
| Empty vault, no VCS | `check_sync_readiness()` → `MIGRATION_NEEDED` | `test_vcs.py` |
| Empty vault → `ensure_sync_ready()` | Auto-inits jj, returns `READY` | `test_vcs.py` |
| `.jj` present, remote configured | `check_sync_readiness()` → `READY` | `test_vcs.py` |
| `.jj` present, no remote | `check_sync_readiness()` → `READY` w/ detail | `test_vcs.py` |
| `.git` only, clean | `check_sync_readiness()` → `MIGRATION_NEEDED` | `test_vcs.py` |
| `.git` only, clean → `ensure` | Auto-colocates, returns `READY` | `test_vcs.py` |
| `.git` only, dirty | Both check and ensure → `MIGRATION_NEEDED` | `test_vcs.py` |
| `.git` + `.jj` inconsistent | Both → `MIGRATION_NEEDED` | `test_vcs.py` |
| `check_sync_readiness()` never mutates | No `.jj/` created in any check-only call | `test_vcs.py` |
| `sync()` happy path | `SyncResult(ok=True)`, sync state persisted | `test_vcs.py` |
| `sync()` with remote divergence | Conflict bookmark created, `ok=False, conflict=True` | `test_vcs.py` |
| `sync()` with network failure | `SyncResult(ok=False, error=...)` | `test_vcs.py` |
| `sync()` with auth failure | `SyncResult(ok=False, error=...)`, clear message | `test_vcs.py` |
| `sync_fetch()` ok, `sync_push()` fails | `SyncResult(ok=False, error=...)` | `test_vcs.py` |
| `configure_sync_remote()` with token | Credential helper written, 0700 perms | `test_vcs.py` |
| `configure_sync_remote()` without token | No credential helper, ambient auth | `test_vcs.py` |
| `sync_status()` with no prior sync | Returns `{}` | `test_vcs.py` |
| `sync_status()` after success | Correct timestamp, `last_sync_ok: true` | `test_vcs.py` |
| `sync_status()` after conflict | `conflict_active: true`, bookmark set | `test_vcs.py` |
| `commit()` unchanged | Existing test suite passes, no regressions | `test_vcs.py` |
| `undo_last_change()` unchanged | Existing test suite passes, no regressions | `test_vcs.py` |
| `vcs_status()` unchanged | Returns raw string, same as before | `test_vcs.py` |
| Full sync round-trip (real repos) | init → configure → write → commit → sync → verify | `test_integration.py` |
| Conflict round-trip (real repos) | Diverge → sync → bookmark exists → status correct | `test_integration.py` |
| Server sync endpoints | Correct status codes, response shapes | `test_server.py` |

---

## Files Modified

| File | Nature of Change |
|---|---|
| `src/obsidian_ops/vcs.py` | Add `VCSReadiness`, `ReadinessCheck`, `SyncResult` types; add new `JJ` methods |
| `src/obsidian_ops/vault.py` | Add `check_sync_readiness`, `ensure_sync_ready`, `configure_sync_remote`, `sync_fetch`, `sync_push`, `sync`, `sync_status`; add private helpers |
| `src/obsidian_ops/errors.py` | No changes needed — `VCSError` already covers sync failures |
| `src/obsidian_ops/server.py` | Add sync endpoint routes and Pydantic models |
| `src/obsidian_ops/__init__.py` | Export `VCSReadiness`, `ReadinessCheck`, `SyncResult` |
| `tests/test_vcs.py` | Unit tests for all new JJ methods, readiness detection, sync operations |
| `tests/test_server.py` | Tests for new HTTP endpoints |
| `tests/test_integration.py` | End-to-end sync round-trip and conflict tests |

No new source files created. No existing files restructured or renamed.

---

## Rollout Strategy

1. **Readiness gating** — callers call `check_sync_readiness()` before attempting
   `sync()`. If not `READY`, they call `ensure_sync_ready()` or inform the user.
2. **Agent-side feature flag** — `AGENT_SYNC_ENABLED` (agent config, out of scope for
   this plan) controls whether the agent invokes sync at all.
3. **Staging validation** — test with known clean vault + test remote before enabling
   in production.
4. **Graduate to default-on** — after successful staging evidence.

---

## What This Plan Explicitly Does NOT Do

- Restructure `vcs.py` into a package (unnecessary, breaks imports)
- Change the `vcs_status() -> str` signature (backward-incompatible)
- Embed tokens in remote URLs (security risk)
- Add retry/backoff logic (caller's responsibility)
- Expose `create_conflict_bookmark()` publicly (implementation detail)
- Ship stub methods that raise `NotImplementedError` (dead code)
- Store sync state only in memory (lost on restart)

---

## Deliverables Checklist

- [ ] `VCSReadiness` enum, `ReadinessCheck` and `SyncResult` frozen dataclasses
- [ ] New `JJ` methods (10 methods, all wrapping `_run()`)
- [ ] `Vault.check_sync_readiness()` — read-only VCS state inspection
- [ ] `Vault.ensure_sync_ready()` — safe auto-initialization
- [ ] `Vault.configure_sync_remote()` — credential-helper-based remote setup
- [ ] `Vault.sync_fetch()` / `Vault.sync_push()` — individual sync steps
- [ ] `Vault.sync()` — full cycle with conflict handling
- [ ] `Vault.sync_status()` — persisted sync state reader
- [ ] `.forge/sync-state.json` atomic persistence
- [ ] `.forge/git-credential.sh` credential helper (when token provided)
- [ ] Server endpoints (7 new routes under `/vcs/sync/`)
- [ ] Unit tests for every new method and detection case
- [ ] Integration tests with real temp repos
- [ ] `__init__.py` export updates
- [ ] Version bump
- [ ] Changelog entry
