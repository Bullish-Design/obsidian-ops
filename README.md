# obsidian-ops

Local-first operations overlay for an Obsidian vault.

## Installation

Install the core library only:

```bash
pip install obsidian-ops
```

Install the optional HTTP server support:

```bash
pip install "obsidian-ops[server]"
```

Install the development and test dependencies:

```bash
devenv shell -- uv sync --extra dev
```

The `dev` install includes the optional server dependencies so the full test
suite and `obsidian-ops-server` entrypoint work in the default development
environment.
