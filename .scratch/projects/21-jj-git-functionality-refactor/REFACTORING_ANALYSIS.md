# Refactoring Plan Analysis — Project 21

## Executive Summary

The intern's plan demonstrates solid understanding of the *desired outcome* but has
several significant issues: a breaking API change it claims not to make, architectural
decisions that conflict with the existing codebase's patterns, scope creep beyond what's
needed, and some outright unsafe defaults. Below is a detailed critique followed by a
recommended alternative approach.

---

## Issue-by-Issue Review

### CRITICAL: `vcs_status()` Is a Breaking Change

The plan lists as a non-goal: *"Changing the existing `vault.commit()` / `vault.undo_last_change()` contract."*

However, the plan **redefines `vcs_status()`** from its current signature:

```python
# Current (vault.py:216)
def vcs_status(self) -> str:        # returns raw `jj status` output
```

to:

```python
# Proposed
def vcs_status(self) -> VCSStatus:  # returns an enum (READY / MIGRATION_NEEDED / ERROR)
```

This is a silent breaking change. The existing `vcs_status()` is already part of the
public API — it's used by `server.py` (the `/vcs/status` endpoint returns it as a
string), and any downstream callers rely on getting raw jj output. The plan doesn't
acknowledge this conflict at all.

**Verdict:** The intern either didn't read the existing code or didn't consider backward
compatibility. This method needs a different name.

---

### CRITICAL: Auto-Migration Side Effect in a Status Check

The plan's migration table says that when `vcs_status()` detects "No `.git`, no `.jj`"
or "`.git` only, clean", it should **auto-run `jj git init --colocate`** and return
`READY`.

A method named `*_status()` should be **read-only**. Hiding repo initialization inside a
status check violates the principle of least surprise and makes the method non-idempotent
in a surprising way. If a caller runs `vcs_status()` twice, the first call mutates the
filesystem and the second is a no-op — that's a footgun.

**Verdict:** Separate the detection (`check`) from the action (`init`/`migrate`).

---

### MAJOR: Module Structure Doesn't Match Existing Patterns

The plan proposes `obsidian_ops.vcs.jj_commands` — a sub-package. But `vcs.py` is
currently a single file (`src/obsidian_ops/vcs.py`), not a package directory. Converting
it into `src/obsidian_ops/vcs/__init__.py` + `src/obsidian_ops/vcs/jj_commands.py` is a
gratuitous structural change that:

- Breaks every existing import of `from obsidian_ops.vcs import JJ, UndoResult`
- Adds package depth for no functional benefit
- Doesn't match the flat module pattern used everywhere else (`content.py`, `lock.py`,
  `frontmatter.py`, `sandbox.py`, etc.)

The existing `JJ` class already *is* the subprocess wrapper. The new commands should be
added as methods on the existing `JJ` class, not in a separate module.

**Verdict:** Extend `JJ`, don't restructure.

---

### MAJOR: Token-in-URL Is a Security Anti-Pattern

The plan proposes:
```python
# configure_remote(url, token):
# If token provided, embed in remote URL: https://{token}@github.com/...
```

Tokens embedded in URLs:
- Appear in `jj git remote list` output (visible to any process that can read it)
- May leak through process listing (`/proc/*/cmdline`)
- Get stored in `.jj/repo/store/git/config` in plaintext
- Can leak via HTTP Referer headers in some git implementations

jj inherits git's credential system. The correct approach is to configure a git
credential helper or use `GIT_ASKPASS` / environment variables. If the caller *must*
pass a token, it should be written to a short-lived credential helper script, not baked
into the remote URL.

**Verdict:** Use git's credential helper mechanism instead.

---

### MAJOR: In-Memory-Only Sync Status Is Insufficient

`SyncStatusInfo` is stored only in-memory on the `Vault` instance. This means:
- Status is lost on process restart
- Multiple Vault instances (e.g., server + CLI) can't share state
- There's no way to inspect sync history without keeping the process alive

The existing codebase has no persistent state mechanism, which is fine for the current
feature set (it's all file-based). But sync status is inherently temporal metadata. At
minimum, it should be written to a simple JSON file inside `.forge/` or `.jj/` so it
survives restarts and is inspectable.

**Verdict:** Persist sync state to a file, or acknowledge this as a known limitation with
a plan to address it.

---

### MODERATE: Retry/Backoff Adds Unnecessary Complexity

Phase C item 6: *"Add retry/backoff policy for transient failures (network timeouts)."*

The existing codebase has zero retry logic anywhere. Every operation is fire-once with a
timeout. Adding retry/backoff:
- Introduces a new cross-cutting concern with no existing pattern to follow
- Multiplies the timeout window (3 retries × 120s = 6 minutes blocking the lock)
- Makes debugging harder (was it the first attempt that failed, or the third?)
- Belongs in the *caller*, not the library (the agent can decide whether to retry)

**Verdict:** Remove from scope. Let the caller handle retries. Document that sync
operations may fail transiently and callers should implement their own retry policy.

---

### MODERATE: `create_conflict_bookmark()` Shouldn't Be Public API

The plan exposes `create_conflict_bookmark(prefix)` as a public Vault method. But this
is an implementation detail of the `sync()` conflict-handling flow. No external caller
should need to create conflict bookmarks independently — they'd call `sync()` and
inspect the `SyncResult`.

Exposing it publicly:
- Widens the API surface for no user-facing benefit
- Creates a maintenance burden (can't change bookmark naming without breaking callers)
- Invites misuse (callers creating bookmarks outside the sync flow)

**Verdict:** Keep as a private method (`_create_conflict_bookmark`). If a real need
emerges later, promote it then.

---

### MODERATE: Phase A "NotImplementedError Stubs" Is Anti-Pattern

Phase A proposes shipping `sync()`, `sync_fetch()`, `sync_push()` as stubs that raise
`NotImplementedError`. This means:
- Published API methods that don't work
- Any caller who discovers them gets a runtime crash
- The version bump (Phase A step 5) ships a broken surface

There's no value in shipping dead methods. Either implement them or don't add them yet.

**Verdict:** Remove the stub phase. Implement the methods when they're ready.

---

### MODERATE: Missing Server-Side Changes

The plan's deliverables don't mention updating `server.py`. Every new Vault method needs
corresponding HTTP endpoints, request/response models, and error handling. The plan adds
7 new Vault methods but says nothing about the server surface. This is a significant
oversight for a plan that claims to enumerate deliverables.

**Verdict:** Add server endpoint design to the plan, or explicitly defer it.

---

### MINOR: `SyncResult.fetched` / `SyncResult.pushed` Booleans Are Ambiguous

Do these mean "attempted" or "succeeded"? If `fetched=True` and `ok=False`, does that
mean the fetch succeeded but something else failed? The semantics aren't defined. A
cleaner design would be a single status enum or individual step results.

---

### MINOR: Test Matrix Lists Scenarios but Not Locations

The test matrix is a good checklist, but the plan doesn't specify which test module(s)
the tests go in. Following the existing pattern (`test_vcs.py` for VCS unit tests,
`test_integration.py` for end-to-end), this should be explicit.

---

### MINOR: No Discussion of `jj git push` Bookmark Semantics

`jj git push` requires specifying *what* to push. By default, jj pushes tracked
bookmarks. The plan doesn't discuss:
- Which bookmark(s) get pushed
- How to handle the main/master bookmark tracking
- What happens when there are no bookmarks to push
- The difference between `jj git push --all` vs `jj git push -b <name>`

This is critical for correctness — pushing the wrong thing (or nothing) silently is a
real risk.

---

## What the Plan Gets Right

To be fair, several aspects are solid:

1. **Boundary discipline** — keeping VCS logic in `obsidian-ops` and out of the agent is
   the correct separation of concerns.
2. **Conflict-as-data pattern** — returning `SyncResult` with conflict info instead of
   raising/blocking is the right design. The vault stays usable.
3. **Migration detection concept** — classifying VCS state into an enum is genuinely
   useful, even if the implementation details need work.
4. **Test matrix coverage** — the scenarios are comprehensive and well-thought-out.
5. **Phased rollout with `vcs_status()` gating** — letting callers check readiness
   before attempting sync is a good safety pattern.

---

## Recommended Alternative Approach

Here's how I'd actually implement bidirectional git sync via jj, respecting the existing
codebase patterns.

### Principle: Extend, Don't Restructure

The codebase is clean and consistent. New functionality should follow the same patterns:
flat modules, thin `JJ` class wrappers, Vault methods that compose them, frozen
dataclasses for results.

### 1. Extend the `JJ` Class with New Commands

Add methods to the existing `JJ` class in `vcs.py`:

```python
# New methods on JJ (vcs.py)
def git_fetch(self, *, remote: str = "origin") -> str
def git_push(self, *, remote: str = "origin", allow_new: bool = False) -> str
def rebase(self, *, destination: str = "trunk()") -> str
def bookmark_create(self, name: str, *, revision: str = "@") -> str
def git_remote_set_url(self, name: str, url: str) -> str
def git_remote_add(self, name: str, url: str) -> str
def git_init_colocate(self) -> str
def log(self, *, revset: str = "@", template: str = "builtin_log_oneline") -> str
```

All follow the existing `_run()` pattern. No new module, no new class.

### 2. New Data Types (in `vcs.py`, alongside `UndoResult`)

```python
class VCSReadiness(Enum):
    """Result of checking whether the vault is ready for sync operations."""
    READY = "ready"
    MIGRATION_NEEDED = "migration_needed"
    ERROR = "error"

@dataclass(frozen=True)
class ReadinessCheck:
    status: VCSReadiness
    detail: str | None = None       # diagnostic message for non-READY states

@dataclass(frozen=True)
class SyncResult:
    ok: bool
    conflict: bool = False
    conflict_bookmark: str | None = None
    error: str | None = None
```

Note: **`VCSReadiness`**, not `VCSStatus` — avoids colliding with the existing
`vcs_status()` method name. Simpler `SyncResult` without ambiguous boolean fields.

### 3. New Vault Methods (Non-Breaking)

```python
# New methods on Vault — none shadow existing methods
def check_sync_readiness(self) -> ReadinessCheck      # READ-ONLY, no side effects
def ensure_sync_ready(self) -> ReadinessCheck          # auto-migrates if safe
def configure_sync_remote(url: str, *, token: str | None = None) -> None
def sync(self, *, conflict_prefix: str = "sync-conflict") -> SyncResult
def sync_fetch(self) -> None
def sync_push(self) -> None
```

Key differences from the intern's plan:
- **`check_sync_readiness()`** is read-only — only inspects `.git`/`.jj` state
- **`ensure_sync_ready()`** is the one that may auto-init — name makes the side effect
  obvious
- **`configure_sync_remote()`** uses a credential helper, not token-in-URL
- No `create_conflict_bookmark()` in the public API
- No `sync_status()` / `SyncStatusInfo` initially — add it when there's a real consumer
  that needs persistent state
- Existing `vcs_status() -> str` remains untouched

### 4. Sync State Persistence (Simple)

Write a minimal JSON file at `.forge/sync-state.json`:

```json
{
  "last_sync_at": "2026-04-26T12:00:00Z",
  "last_sync_ok": true,
  "conflict_active": false,
  "conflict_bookmark": null
}
```

Read/write via a small private helper. No new public data types needed initially — the
`SyncResult` returned from `sync()` is the primary interface. The file is just for
crash-recovery and multi-process visibility.

### 5. Implementation Order

**Step 1: JJ class extensions + data types**
- Add the new `JJ` methods
- Add `VCSReadiness`, `ReadinessCheck`, `SyncResult`
- Unit tests with mocked subprocess (follows `test_vcs.py` pattern)
- Zero impact on existing functionality

**Step 2: Readiness detection**
- Implement `check_sync_readiness()` — pure filesystem inspection
- Implement `ensure_sync_ready()` — calls `jj git init --colocate` when safe
- Unit tests with temp dirs containing synthetic `.git`/`.jj` states
- Zero impact on existing functionality

**Step 3: Sync operations**
- Implement `sync_fetch()`, `sync_push()`, `sync()` with conflict handling
- Implement `configure_sync_remote()` with credential helper
- Implement private `_create_conflict_bookmark()` and `_write_sync_state()`
- Unit tests with mocked JJ methods
- Zero impact on existing functionality

**Step 4: Server endpoints + integration tests**
- Add `/vcs/sync`, `/vcs/sync/fetch`, `/vcs/sync/push`, `/vcs/sync/readiness`,
  `/vcs/sync/remote` endpoints
- Integration tests with real temp git repos as remotes
- Full round-trip: init → configure → write → commit → sync → verify remote

### 6. What NOT to Do

- Don't restructure `vcs.py` into a package
- Don't rename or change `vcs_status()` signature
- Don't embed tokens in URLs
- Don't add retry/backoff (caller's responsibility)
- Don't ship stub methods that raise `NotImplementedError`
- Don't add `create_conflict_bookmark()` to the public API
- Don't store sync state only in memory

---

## Summary Scorecard

| Aspect                          | Intern Plan | Recommended |
|---------------------------------|-------------|-------------|
| Breaking changes                | Yes (`vcs_status()`) | None |
| Module restructuring needed     | Yes (vcs → package) | No |
| Security (token handling)       | Token-in-URL | Credential helper |
| Side effects in status checks   | Yes (auto-init) | Separated |
| Sync state persistence          | In-memory only | File-backed |
| Unnecessary complexity          | Retry/backoff, public bookmark API | Minimal surface |
| Server endpoint coverage        | Not mentioned | Included |
| Existing test patterns followed | Partially | Fully |
| Stub/dead-code phases           | Yes (Phase A) | No |
| Backward compatibility          | Broken | Preserved |
