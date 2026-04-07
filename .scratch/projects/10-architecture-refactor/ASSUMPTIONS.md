# ASSUMPTIONS

- This refactor is for a private tailnet MVP with one primary operator.
- Simplicity and delivery speed are prioritized over advanced UX (e.g., live streaming progress).
- Existing monolith modules are the source of truth for behavior to preserve unless explicitly simplified.
- Architecture split target is three repos: Forge, obsidian-agent, obsidian-ops.
