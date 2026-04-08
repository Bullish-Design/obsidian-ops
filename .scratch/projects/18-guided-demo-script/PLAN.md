# Project 18 Plan: Guided Demo Script Mode

## ABSOLUTE RULE
NEVER use subagents. Do all work directly in this session.

## Goal
1. Create a new project template directory with standard tracking files.
2. Add a detailed `DEMO_SCRIPT.md` that documents each runtime demo step.
3. Add a new run mode in `scripts/live_vault_demo.py` that pauses after each step and waits for user key input.
4. Verify the flow through `devenv shell -- ...`.

## Implementation Steps
1. Initialize project tracking files (`PLAN`, `ASSUMPTIONS`, `DECISIONS`, `PROGRESS`, `CONTEXT`, `ISSUES`).
2. Create `DEMO_SCRIPT.md` with:
   - table of contents
   - step-by-step walkthrough aligned to script behavior
   - expected visible changes in the vault
3. Update `scripts/live_vault_demo.py`:
   - add run mode flag (`auto` vs `guided`)
   - pause after each step in guided mode
   - prompt user to press Enter to continue
4. Update docs in `demo/obsidian-ops/README.md`.
5. Verify with `devenv` commands.

## Acceptance Criteria
- New project template directory exists and is complete.
- `DEMO_SCRIPT.md` exists and matches runtime step order.
- Demo script supports guided pause mode.
- User can continue step-by-step with key presses.
- Demo behavior verified via `devenv` commands.

## ABSOLUTE RULE (Repeat)
NEVER use subagents.
