# Library Implementation — Decisions

## Decision Log

1. Added `pydantic-settings` as a direct dependency in `pyproject.toml`.
   - Rationale: the implementation guide requires `pydantic_settings.BaseSettings`; importing through `pydantic` alone is insufficient.
2. Implemented undo as a queued special job (`is_undo=True`) instead of inline execution.
   - Rationale: preserves single serialized mutation flow and avoids undo racing with normal agent jobs.
