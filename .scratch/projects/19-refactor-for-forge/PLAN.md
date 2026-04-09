# Project 19: Refactor For Forge

## Goal

Implement the refactoring guide in `REVIEW_REFACTOR_GUIDE.md` so `obsidian-ops`
becomes a stable library-first boundary for vault, content, frontmatter, VCS,
search, and optional server operations.

## Ordered Steps

1. Establish baseline behavior and record current failures/successes.
2. Fix packaging and development environment contract.
3. Implement explicit deep frontmatter patch semantics.
4. Strengthen content patch semantics and documentation.
5. Consolidate the full VCS undo lifecycle behind a high-level `Vault` API.
6. Harden the optional HTTP server contract with typed models.
7. Clarify file-matching/search contract.
8. Replace the placeholder README with complete developer documentation.
9. Run the final validation matrix.

## Constraints

- No subagents.
- Keep commits small and attributable by step.
- Run project tooling through `devenv shell -- ...`.
- Sync dependencies before the first test run with
  `devenv shell -- uv sync --extra dev`.
- Update docs in the same step as behavior changes.

## Acceptance Criteria

- Full `devenv shell -- pytest -q` passes.
- Optional server packaging remains consistent with library-first use.
- Frontmatter, content, VCS, server, and search contracts are explicit,
  documented, and test-covered.
- README is sufficient for a new contributor and an upstream consumer.
