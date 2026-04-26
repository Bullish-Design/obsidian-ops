# Project 21: jj Git Functionality Refactor

## ABSOLUTE RULE

NO SUBAGENTS. All work in this project is completed directly in the main agent session.

## Goal

Implement `VCS_REFACTOR_PLAN_V2.md` in full for `obsidian-ops`:
- additive jj sync capabilities in core library
- readiness detection and safe auto-init
- persistent sync state and credential helper wiring
- HTTP API endpoints
- unit + server + integration tests
- version bump and release note entry

## Ordered Steps

1. Phase 1: Add new VCS data types and JJ wrapper methods (`vcs.py` + exports + tests).
2. Phase 2: Add readiness detection and safe ensure logic on `Vault` + tests.
3. Phase 3: Add sync remote/config/state/conflict lifecycle on `Vault` + tests.
4. Phase 4: Add server sync endpoints + tests.
5. Add integration tests for sync happy path and conflict path.
6. Final validation and release updates (version bump + project changelog note).
7. Commit/push after each completed step.

## Acceptance Criteria

- All deliverables from `VCS_REFACTOR_PLAN_V2.md` are implemented.
- Existing behavior (`commit`, `undo_last_change`, `vcs_status`) remains unchanged.
- New tests for all added methods and edge cases pass.
- Full repo test + lint validation passes in `devenv shell -- ...`.

## ABSOLUTE RULE (REPEATED)

NO SUBAGENTS. All work in this project is completed directly in the main agent session.
