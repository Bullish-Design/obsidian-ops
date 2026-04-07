"""obsidian-ops: Sandboxed operations on an Obsidian vault."""

from obsidian_ops.errors import (
    BusyError,
    ContentPatchError,
    FileTooLargeError,
    FrontmatterError,
    PathError,
    VaultError,
    VCSError,
)
from obsidian_ops.search import SearchResult
from obsidian_ops.vault import Vault

__all__ = [
    "Vault",
    "SearchResult",
    "VaultError",
    "PathError",
    "FileTooLargeError",
    "BusyError",
    "FrontmatterError",
    "ContentPatchError",
    "VCSError",
]
