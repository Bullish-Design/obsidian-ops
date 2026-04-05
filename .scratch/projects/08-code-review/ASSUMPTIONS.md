# Code Review — Assumptions

- Review targets the full codebase at HEAD (`8c46e29`, `main` branch).
- This is a local-first tool, not deployed to public infrastructure. Security findings are calibrated accordingly (SSRF is still critical because the LLM can be prompt-injected via vault content).
- The "OpenAI" dependency targets a local vLLM instance, not the OpenAI cloud API.
- Kiln is an external static site generator that consumes an Obsidian vault and produces HTML.
- Jujutsu (jj) is used instead of git for vault versioning; it provides simpler undo semantics.
- The app is single-worker (`workers: int = 1` default) — concurrency concerns are future-facing.
- The demo scaffold is not production code; lower bar for quality.
- `.scratch/` directories contain project tracking docs, not deployed artifacts.
