"""Path sandbox validation helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from obsidian_ops.errors import PathError

_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _is_traversal(cleaned_path: str) -> bool:
    return (
        cleaned_path == ".."
        or cleaned_path.startswith("../")
        or cleaned_path.startswith("..\\")
        or cleaned_path.startswith(f"..{os.sep}")
    )


def validate_path(root: Path, user_path: str) -> Path:
    """Validate a vault-relative path and return an absolute safe path."""
    if not user_path:
        raise PathError("path cannot be empty")

    cleaned_path = os.path.normpath(user_path)
    if cleaned_path in {"", "."}:
        raise PathError("path cannot resolve to vault root")

    if os.path.isabs(cleaned_path) or _DRIVE_LETTER_RE.match(cleaned_path):
        raise PathError("absolute paths are not allowed")

    if _is_traversal(cleaned_path):
        raise PathError("path traversal is not allowed")

    resolved_root = Path(os.path.realpath(root))
    candidate = resolved_root / cleaned_path

    if candidate.exists():
        resolved_candidate = Path(os.path.realpath(candidate))
        if not _is_within(resolved_candidate, resolved_root):
            raise PathError("path escapes vault root via symlink")
        return resolved_candidate

    resolved_parent = Path(os.path.realpath(candidate.parent))
    if not _is_within(resolved_parent, resolved_root):
        raise PathError("path parent escapes vault root")

    return candidate
