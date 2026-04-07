"""obsidian-ops package."""

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

__version__ = "0.1.0"

__all__ = [
    "__version__",
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
