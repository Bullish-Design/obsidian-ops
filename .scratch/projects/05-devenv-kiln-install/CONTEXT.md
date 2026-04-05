# Devenv Kiln Install — Context

- Requested change: use the same kiln installation method as `ssg-gen`.
- Applied kiln setup from `ssg-gen`:
  - `devenv.yaml` now includes `inputs.kiln` (`github:otaleghani/kiln/v0.9.5`).
  - `devenv.nix` now installs kiln via `inputs.kiln.packages.${pkgs.system}.default.overrideAttrs` with matching `vendorHash` and `doCheck = false`.
- Verification:
  - `devenv shell -- kiln version` succeeded.
  - Note: kiln CLI in this env uses `kiln version` command, not `kiln --version`.
