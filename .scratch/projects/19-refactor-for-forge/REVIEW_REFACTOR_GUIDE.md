# obsidian-ops Review Refactor Guide

## Purpose

This document is an implementation guide for hardening `obsidian-ops` before the Forge architecture refactor proceeds.

It is written for a brand new intern. Follow the steps in order. Do not skip validation. Do not invent behavior that is not specified here. If actual code behavior conflicts with this guide, stop and document the discrepancy before proceeding.

Repository under implementation:

- `/home/andrew/Documents/Projects/obsidian-ops`

Related context documents:

- `/home/andrew/Documents/Projects/forge/.scratch/projects/06-forge-architecture-refactor/DEPENDENCY_LIBRARY_REVIEW.md`
- `/home/andrew/Documents/Projects/forge/.scratch/projects/06-forge-architecture-refactor/obsidian-ops/CONCEPT.md`
- `/home/andrew/Documents/Projects/forge/.scratch/projects/06-forge-architecture-refactor/obsidian-ops/SPEC.md`

## Mission

Make `obsidian-ops` a stable, library-first dependency boundary that:

- owns all vault file and version-control operations,
- is usable both as a Python library and an optional HTTP server,
- has a reproducible local development and test environment,
- exposes explicit, tested behavior for frontmatter patching, content patching, and VCS operations,
- can be safely consumed by `obsidian-agent` without requiring that package to shell out to `jj` or reimplement vault behavior.

## Non-Goals

Do not add any of the following to this repo:

- LLM logic
- prompt construction
- URL-to-file resolution for Forge pages
- UI-specific logic
- Forge-specific request envelopes

Those concerns belong elsewhere.

## Definition Of Done

This work is done only when all of the following are true:

1. `devenv shell -- pytest -q` runs cleanly in the repo's default environment.
2. The packaging story is internally consistent for core library vs optional server usage.
3. `Vault.update_frontmatter()` supports richer, explicit nested update behavior and that behavior is documented.
4. `Vault` exposes a single higher-level undo lifecycle suitable for upstream callers.
5. HTTP server behavior is explicit, typed, and fully testable.
6. README-level documentation is sufficient for a new developer to install, run tests, and use the main APIs.

## Current Repository Map

Primary implementation files:

- `pyproject.toml`
- `devenv.nix`
- `src/obsidian_ops/__init__.py`
- `src/obsidian_ops/vault.py`
- `src/obsidian_ops/sandbox.py`
- `src/obsidian_ops/frontmatter.py`
- `src/obsidian_ops/content.py`
- `src/obsidian_ops/search.py`
- `src/obsidian_ops/vcs.py`
- `src/obsidian_ops/lock.py`
- `src/obsidian_ops/server.py`
- `src/obsidian_ops/errors.py`

Primary test files:

- `tests/test_vault.py`
- `tests/test_frontmatter.py`
- `tests/test_content.py`
- `tests/test_search.py`
- `tests/test_lock.py`
- `tests/test_vcs.py`
- `tests/test_server.py`
- `tests/test_integration.py`
- `tests/test_sandbox.py`
- `tests/test_smoke.py`

Current known issue from the dependency review:

- full `pytest` in the default `devenv` fails during server-test collection because `fastapi` is not installed in the default environment.

## Working Rules

1. Work in small, reviewable commits.
2. Run the required tests after each step, not only at the end.
3. Update docs in the same step as behavior changes.
4. Do not break the library-first boundary to make the server easier.
5. Do not add hidden fallback behavior. If the package supports an install mode, document it and make it actually work.
6. If a behavior choice is ambiguous, write the decision down in the PR notes and in the docs.

## Step 0: Establish Baseline

### Objective

Capture the repo's current behavior before making changes.

### Tasks

1. Create a working branch in `obsidian-ops`.
2. Run the default full test command.
3. Run the known-good non-server test subset.
4. Record the outcome in your notes.
5. Read the current `pyproject.toml`, `devenv.nix`, and `README.md` before making any changes.

### Commands

```bash
devenv shell -- pytest -q
devenv shell -- pytest -q tests/test_vault.py tests/test_frontmatter.py tests/test_content.py tests/test_search.py tests/test_lock.py tests/test_vcs.py tests/test_integration.py tests/test_smoke.py tests/test_sandbox.py
```

### Expected Baseline

- The full suite currently fails during `tests/test_server.py` collection because `fastapi` is unavailable.
- The core library suite should pass.

### Acceptance Criteria

- Baseline commands were run and their actual output was recorded.
- No code was changed yet.

## Step 1: Fix Packaging And Environment Contract

### Why This Is First

There is no point changing behavior while the repo's own development environment does not match its package contract.

Right now the package claims to offer a server entrypoint, the repo contains server tests, but the default environment cannot run those tests. That must be fixed before doing behavioral work.

### Decision You Must Make

Pick one packaging model and implement it consistently.

Option A:
- server dependencies are part of the default package install.
- simplest to reason about.
- larger runtime dependency surface.

Option B:
- server dependencies remain optional.
- the server entrypoint must only be available in the documented server install path.
- imports must not break core-only usage.

Recommended choice:
- keep the library-first design and maintain server dependencies as optional,
- but make the development environment include server dependencies so the full suite runs locally.

### Files Likely To Change

- `pyproject.toml`
- `devenv.nix`
- `src/obsidian_ops/server.py`
- `README.md`

### Implementation Tasks

1. Update `devenv.nix` so the default development shell can run the full repository test suite, including server tests.
2. Ensure the chosen install story is reflected in `pyproject.toml`.
3. If server dependencies remain optional, make sure importing the core library does not require FastAPI.
4. Make sure the CLI entrypoint behavior is not misleading.
5. Write a short installation section in `README.md` covering:
   - core library install
   - server install
   - dev/test install

### Validation

Run:

```bash
devenv shell -- pytest -q
devenv shell -- pytest -q tests/test_server.py
devenv shell -- obsidian-ops-server --help
```

### Acceptance Criteria

- `devenv shell -- pytest -q` completes test collection without `fastapi` import errors.
- the documented install mode for the server actually works.
- README install instructions match the package behavior.

### Stop Conditions

Stop and ask for clarification if:

- the only way to make the server work is to force FastAPI into all installs and that conflicts with the desired library-first design,
- or if the current build tooling makes optional scripts impossible without a larger packaging redesign.

## Step 2: Implement Explicit Deep Frontmatter Patch Semantics

### Why This Matters

The current `update_frontmatter()` behavior is shallow. Nested mappings are replaced instead of merged. That is too weak for a stable editing substrate.

### Required Outcome

`Vault.update_frontmatter()` must support predictable nested updates.

Minimum required behavior:

1. top-level field updates continue to work.
2. nested dict updates merge into existing nested dicts instead of replacing them wholesale.
3. unchanged body content remains preserved.
4. simple previous call sites continue to work.

### Optional But Acceptable Extension

You may add dot-path updates if implemented carefully and documented clearly. Do not do this unless the behavior is fully tested.

### Files Likely To Change

- `src/obsidian_ops/frontmatter.py`
- `src/obsidian_ops/vault.py`
- `tests/test_frontmatter.py`
- `tests/test_vault.py`
- `README.md`

### Implementation Tasks

1. Define the merge contract in prose before writing code.
2. Implement a merge helper in `frontmatter.py` rather than burying logic inside `Vault.update_frontmatter()`.
3. Update `Vault.update_frontmatter()` to use the helper.
4. Preserve existing behavior for simple, shallow updates.
5. Document exact semantics with at least two examples in `README.md`.

### Required Tests To Add Or Update

Add tests for:

- nested merge into an existing dict
- preserving sibling nested keys during update
- creation of frontmatter when none exists
- preserving markdown body content after update
- backward compatibility for simple top-level updates

### Validation

Run:

```bash
devenv shell -- pytest -q tests/test_frontmatter.py
devenv shell -- pytest -q tests/test_vault.py
devenv shell -- pytest -q
```

### Acceptance Criteria

- nested updates no longer wipe unrelated nested fields.
- existing frontmatter tests still pass.
- body preservation remains true.
- README examples match actual behavior.

### Stop Conditions

Stop if delete semantics become necessary to finish the implementation. If delete-via-update is needed, document and decide that behavior explicitly before coding it.

## Step 3: Strengthen Content Patch Semantics

### Why This Matters

Heading and block patching already exists, but the API does not clearly communicate whether content was created or replaced. The behavior is still too implicit for a stable lower-layer library.

### Required Outcome

Make heading/block write behavior explicit and test-covered.

### Design Guidance

For headings:

- if the heading exists, the operation is a replace.
- if the heading does not exist, the operation is an append/create.

For blocks:

- current strict behavior is acceptable if kept explicit and documented,
- or you may add an opt-in create mode, but only if the semantics are deterministic and documented.

Recommended approach:

- keep `write_block()` strict for now,
- strengthen tests and documentation,
- add richer result signaling internally or through a small result model if that can be done without destabilizing existing callers.

### Files Likely To Change

- `src/obsidian_ops/content.py`
- `src/obsidian_ops/vault.py`
- `tests/test_content.py`
- `tests/test_vault.py`
- `README.md`

### Implementation Tasks

1. Decide whether to add a small result type or to keep the existing void-return API and only improve docs/tests.
2. If you add result signaling, keep backward compatibility unless a deliberate breaking change is approved.
3. Make heading creation behavior explicit in docs.
4. Make block-not-found behavior explicit in docs and tests.
5. Add idempotence-oriented tests where appropriate.

### Required Tests To Add Or Update

- heading replace existing section
- heading create missing section
- block replace existing block
- block missing anchor behavior
- repeat-write behavior does not corrupt surrounding content

### Validation

Run:

```bash
devenv shell -- pytest -q tests/test_content.py
devenv shell -- pytest -q tests/test_vault.py
devenv shell -- pytest -q
```

### Acceptance Criteria

- content patch behavior is no longer implicit.
- tests cover both success and missing-anchor cases.
- docs state exactly what happens for missing headings and missing blocks.

## Step 4: Consolidate Full VCS Undo Lifecycle Inside `obsidian-ops`

### Why This Matters

Downstream packages must not shell out to `jj` directly for undo/restore semantics. `obsidian-ops` must own the complete VCS lifecycle.

### Required Outcome

Expose one higher-level vault operation that performs the full undo lifecycle needed by upstream callers.

Recommended shape:

- add a method such as `undo_last_change()` or `revert_last_mutation()` to `Vault`,
- implement the full logic there,
- keep lower-level methods only if still useful and clearly documented.

### Files Likely To Change

- `src/obsidian_ops/vcs.py`
- `src/obsidian_ops/vault.py`
- `src/obsidian_ops/errors.py`
- `tests/test_vcs.py`
- `tests/test_integration.py`
- `README.md`

### Implementation Tasks

1. Decide the exact high-level method name and keep it consistent everywhere.
2. Put subprocess details in `vcs.py`, not in `vault.py` or future callers.
3. Ensure lock behavior remains correct while VCS operations run.
4. Return or raise errors in a way that upstream packages can handle deterministically.
5. Document the method as the preferred upstream undo API.

### Required Tests To Add Or Update

- success path for full undo lifecycle
- failure path when `jj undo` fails
- failure path when follow-up restore step fails
- lock behavior during VCS operations
- integration test proving a modified file returns to its original content after the high-level undo method

### Validation

Run:

```bash
devenv shell -- pytest -q tests/test_vcs.py
devenv shell -- pytest -q tests/test_integration.py
devenv shell -- pytest -q
```

### Acceptance Criteria

- one `Vault` method now represents the supported upstream undo lifecycle.
- downstream packages no longer need raw `jj` subprocess calls.
- VCS error behavior is explicit and test-covered.

### Stop Conditions

Stop if implementing this cleanly requires changing Jujutsu assumptions that are also embedded elsewhere. In that case, document the exact incompatibility before proceeding.

## Step 5: Harden HTTP Server Contract

### Why This Matters

The server exists, but it currently uses loose `dict` payloads and has a slightly inconsistent response contract compared to the rest of the stack.

### Required Outcome

The server should remain optional, but its request and response contract must be explicit and typed.

### Files Likely To Change

- `src/obsidian_ops/server.py`
- `tests/test_server.py`
- `README.md`

### Implementation Tasks

1. Add Pydantic request models for payload-heavy routes.
2. Add Pydantic response models where that improves clarity.
3. Normalize health response shape. Recommended response:
   - `{"ok": true, "status": "healthy"}`
4. Keep current HTTP status mappings unless there is a clear reason to change them.
5. Document route payloads and error codes.

### Required Tests To Add Or Update

- health response shape
- typed validation errors for malformed request bodies
- existing route success cases after model changes
- error-mapping tests for `PathError`, `BusyError`, `FrontmatterError`, `ContentPatchError`, and `VCSError`

### Validation

Run:

```bash
devenv shell -- pytest -q tests/test_server.py
devenv shell -- pytest -q
```

### Acceptance Criteria

- server request/response shapes are explicit.
- server tests pass in default dev environment.
- README documents the server API clearly enough for a first-time user.

## Step 6: Clarify File-Matching And Search Contract

### Why This Matters

The spec language and implementation can be read differently. The docs must match actual behavior.

### Required Outcome

State clearly whether glob matching operates on:

- filename only,
- or vault-relative path.

Recommended choice:

- keep current relative-path matching if that is the implementation you retain,
- then update docs/spec/tests to match it exactly.

### Files Likely To Change

- `src/obsidian_ops/search.py`
- `src/obsidian_ops/vault.py`
- `tests/test_search.py`
- `tests/test_vault.py`
- `README.md`

### Implementation Tasks

1. Decide the contract.
2. Ensure implementation matches the contract.
3. Update tests to reflect the contract explicitly.
4. Add examples in docs.

### Required Tests To Add Or Update

- relative-path glob matching example
- hidden-file skipping
- result limit behavior
- interaction between `list_files()` and `search_files()` scope

### Validation

Run:

```bash
devenv shell -- pytest -q tests/test_search.py
devenv shell -- pytest -q tests/test_vault.py
devenv shell -- pytest -q
```

### Acceptance Criteria

- no drift remains between docs, tests, and implementation.
- a new developer can predict how glob matching works without reading source code.

## Step 7: Replace Placeholder README With Real Developer Documentation

### Why This Matters

The repo-level `README.md` is effectively empty. That is not acceptable for a foundational dependency package.

### Files Likely To Change

- `README.md`
- optionally `pyproject.toml` if docs reveal packaging ambiguity still exists

### Required Sections

Write at least the following sections:

1. What `obsidian-ops` is and is not
2. Installation
3. Development setup
4. Running tests
5. Library usage examples
6. Server usage examples
7. VCS prerequisites and expectations
8. Error model
9. Integration notes for `obsidian-agent`

### Validation

Manually confirm that a new contributor could answer these questions from the README alone:

- How do I install the library?
- How do I run the server?
- How do I run the tests?
- Which layer owns undo behavior?
- Does this package do anything with LLMs?

### Acceptance Criteria

- README is sufficient for an intern to set up and use the repo.
- docs match actual package behavior.

## Step 8: Final Full Validation Pass

### Required Command Matrix

Run all of the following before considering the work done:

```bash
devenv shell -- pytest -q tests/test_frontmatter.py
devenv shell -- pytest -q tests/test_content.py
devenv shell -- pytest -q tests/test_vcs.py
devenv shell -- pytest -q tests/test_server.py
devenv shell -- pytest -q tests/test_integration.py
devenv shell -- pytest -q
```

If formatting/linting is already configured, also run:

```bash
devenv shell -- ruff check src tests
devenv shell -- ruff format --check src tests
```

### Manual Verification

Also manually verify:

1. the documented install commands work,
2. the server entrypoint starts in the documented install mode,
3. the README and the package metadata say the same thing.

### Final Acceptance Criteria

- all required test commands pass,
- docs match implementation,
- `obsidian-agent` now has a stable lower-layer API to consume.

## Recommended Commit Sequence

Use this sequence so regressions are attributable:

1. packaging and dev environment
2. frontmatter semantics
3. content patch semantics
4. VCS lifecycle consolidation
5. server contract typing
6. glob/search contract clarification
7. README and final polish

Do not combine all steps into one large commit.

## Critical Cautions

1. Do not introduce `obsidian-agent`-specific logic into this package.
2. Do not keep ambiguous dual behavior for packaging. Pick one model and document it.
3. Do not change multiple public contracts in one step without updating tests and docs immediately.
4. Do not implement deep merge semantics without writing explicit tests first.
5. Do not move VCS subprocess logic into random places. Keep it centralized in the VCS layer.
6. Do not hold locks longer than necessary unless the operation must be serialized end-to-end.
7. Do not declare the work complete if only the non-server test subset passes.

## Handoff Checklist

Before handing this work back for review, confirm all boxes are true:

- [ ] default dev environment runs full test suite
- [ ] server install story is consistent
- [ ] nested frontmatter patch behavior is implemented and documented
- [ ] content patch behavior is explicit and tested
- [ ] high-level undo lifecycle exists in `Vault`
- [ ] server request/response models are typed
- [ ] glob semantics are explicit and documented
- [ ] README is complete and accurate
- [ ] full test matrix passes
