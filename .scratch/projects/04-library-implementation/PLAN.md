# Library Implementation — Plan

## ABSOLUTE RULE

- NO SUBAGENTS. All implementation, testing, and verification stays in this session directly.

## Deliverable

- Complete `obsidian_ops` library implementation with static overlay assets and tests, aligned to the implementation guide.

## Ordered Steps

1. Implement `src/obsidian_ops/config.py`.
2. Implement `src/obsidian_ops/models.py`.
3. Implement `src/obsidian_ops/locks.py`.
4. Implement `src/obsidian_ops/fs_atomic.py`.
5. Implement `src/obsidian_ops/history_jj.py`.
6. Implement `src/obsidian_ops/rebuild.py`.
7. Implement `src/obsidian_ops/page_context.py`.
8. Implement `src/obsidian_ops/inject.py`.
9. Implement `src/obsidian_ops/tools.py`.
10. Implement `src/obsidian_ops/agent.py`.
11. Implement `src/obsidian_ops/queue.py`.
12. Implement `src/obsidian_ops/app.py` (+ entrypoint).
13. Implement `src/obsidian_ops/static/ops.css`.
14. Implement `src/obsidian_ops/static/ops.js`.
15. Implement tests in `tests/` and run verification.

## Execution Strategy

- Follow TDD where practical: write/adjust tests first for covered modules, then implement code to pass.
- Keep project tracking files current after each major chunk.
- Run tooling with `devenv shell -- ...`.

## Acceptance Targets

- Unit/integration tests pass.
- API, queue, and worker lifecycle behave per guide.
- Path safety and atomic writes enforced.
- Overlay is injected and usable.

## ABSOLUTE RULE

- NO SUBAGENTS. Continue until implementation is fully complete.
