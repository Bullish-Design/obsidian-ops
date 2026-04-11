# Context

Date: 2026-04-11
Project: `20-additional-functionality-refactor`

## Completed

Phase 0.1 and Phase 0.2 are implemented in source:
- Added `src/obsidian_ops/structure.py` and `Vault.list_structure()`.
- Added `src/obsidian_ops/anchors.py` and `Vault.ensure_block_id()`.
- Exported all new Phase 0.1/0.2 model types via package root.
- Added `tests/test_structure.py` and `tests/test_anchors.py`.

## Verification run

- `devenv shell -- pytest tests/test_structure.py -v` passed.
- `devenv shell -- pytest tests/test_vault.py tests/test_sandbox.py -q` passed.
- `devenv shell -- pytest tests/test_anchors.py -v` passed.
- `devenv shell -- pytest tests/test_content.py tests/test_vault.py -q` passed.

## Next

Implement Phase 0.3 templates (`templates.py`, `Vault.list_templates`,
`Vault.create_from_template`, exports, and tests), then run phase gate and commit.
