# Decisions

## D-001: Use a dedicated runtime vault copy
- Status: accepted
- Rationale: lets the user open and observe changes safely without mutating the source demo vault.

## D-002: Implement demo orchestration in Python
- Status: accepted
- Rationale: direct access to `obsidian_ops.vault.Vault` APIs keeps the demo concise and faithful to library behavior.

## D-003: Add a `devenv.nix` script entrypoint
- Status: accepted
- Rationale: one stable command path for run/reset/cleanup improves ergonomics.
