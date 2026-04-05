from __future__ import annotations

from pathlib import Path


def resolve_page_path(vault_dir: Path, url_path: str, prefix: str = "/") -> str | None:
    normalized = url_path
    if prefix and normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]

    normalized = normalized.strip("/")
    candidates = ["index.md"] if normalized == "" else [f"{normalized}.md", f"{normalized}/index.md"]

    for candidate in candidates:
        target = (vault_dir / candidate).resolve()
        if target.exists() and target.is_file():
            return target.relative_to(vault_dir.resolve()).as_posix()
    return None
