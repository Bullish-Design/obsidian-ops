# Demo Scaffold — Decisions

1. Added console script as `ops-demo` (not `demo`).
   - Rationale: repository has a top-level `demo/` directory; `demo` command name collisions in shell caused execution failures.
2. Demo runtime uses a copied vault under `.scratch/projects/06-demo-scaffold/generated/runtime-vault`.
   - Rationale: keeps tracked sample vault immutable while still allowing `jj` workspace initialization and mutation during demo sessions.
