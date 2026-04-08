# Project 16 Plan: Live Demo Script

## Goal
Create a detailed demo runner that mutates a demo vault in real time, callable from a `devenv.nix` script entrypoint, with reset/cleanup support.

## Steps
1. Add project tracking files for this task.
2. Implement a CLI demo script with subcommands:
   - `run`
   - `reset`
   - `cleanup`
   - `status`
3. Wire the script to a `devenv.nix` script entrypoint.
4. Document usage in demo docs.
5. Verify command flow via `devenv shell -- ...`.

## Constraints
- No subagents.
- Keep demo vault easy to open in parallel and observe file changes.
- Provide deterministic reset behavior.
