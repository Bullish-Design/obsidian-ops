from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

MAX_FILE_SIZE_BYTES = 1024 * 1024
WARN_FILE_SIZE_BYTES = 256 * 1024
PROTECTED_DIRS = {".jj", ".obsidian", ".git", "__pycache__"}

LOGGER = logging.getLogger(__name__)


def read_file_safe(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large to read safely (>1MB): {path}")
    if size > WARN_FILE_SIZE_BYTES:
        LOGGER.warning("Reading large file (%d bytes): %s", size, path)
    return path.read_text(encoding="utf-8")


def write_file_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def validate_vault_path(vault_root: Path, target: Path) -> Path:
    vault_resolved = vault_root.expanduser().resolve()
    target_path = Path(target)

    if ".." in target_path.parts:
        raise ValueError("Path traversal is not allowed")
    if any(part in PROTECTED_DIRS for part in target_path.parts):
        raise ValueError("Protected directories are not writable")

    candidate = target_path if target_path.is_absolute() else vault_resolved / target_path
    candidate_resolved = candidate.expanduser().resolve()

    if not candidate_resolved.is_relative_to(vault_resolved):
        raise ValueError("Path is outside the vault")

    relative_parts = candidate_resolved.relative_to(vault_resolved).parts
    if any(part in PROTECTED_DIRS for part in relative_parts):
        raise ValueError("Protected directories are not writable")

    return candidate_resolved
