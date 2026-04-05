# Library Implementation — Decisions

## Decision Log

1. Added `pydantic-settings` as a direct dependency in `pyproject.toml`.
   - Rationale: the implementation guide requires `pydantic_settings.BaseSettings`; importing through `pydantic` alone is insufficient.
