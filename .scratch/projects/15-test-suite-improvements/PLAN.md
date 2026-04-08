# Project 15 Plan: Test Suite Improvements

## Absolute Rule
Do all work directly in this session. Never use subagents.

## Ordered Steps
1. Step 0: Fix BUG-1 in `find_block` regex and add regression test.
2. Step 1: Build integration test infrastructure (`tests/test_integration.py`).
3. Step 2: Add file operation integration tests.
4. Step 3: Add frontmatter integration tests.
5. Step 4: Add content patching integration tests.
6. Step 5: Add error handling integration tests.
7. Step 6: Add missing server endpoint and error mapping tests.
8. Step 7: Add edge-case unit tests for uncovered lines.
9. Step 8: Add integration report generation.
10. Step 9: Run full verification (tests, coverage, lint, report checks).

## Workflow Rules
- Run `devenv shell -- uv sync --extra dev` before the first test run in this session.
- For each step: implement only that step, run required tests, confirm passing, update tracking docs, commit, and push.
- Keep snapshot/report artifacts under `.scratch/projects/15-test-suite-improvements/`.

## Completion Criteria
- All guide steps complete.
- Step-specific checks pass at each step.
- Final suite, coverage, and lint checks pass.
- Tracking docs reflect final status and outcomes.

## Absolute Rule (Repeat)
Never use subagents.
