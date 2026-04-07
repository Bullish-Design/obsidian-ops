# Decisions

1. Keep `demo/` untouched so reference/demo assets remain available.
   - Rationale: user explicitly asked to keep demo files.
2. Keep root environment/config files untouched.
   - Rationale: user explicitly called out retaining scaffold files like `devenv.nix` and `pyproject.toml`.
3. Preserve directory structure using `.gitkeep` in `src/obsidian_ops/`, `src/obsidian_ops/static/`, and `tests/`.
   - Rationale: maintain a clean scaffold for rewrite without retaining implementation code.
