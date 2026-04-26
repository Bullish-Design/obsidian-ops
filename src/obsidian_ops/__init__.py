"""obsidian-ops: Sandboxed operations on an Obsidian vault."""

from obsidian_ops.anchors import EnsureBlockResult
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
from obsidian_ops.structure import Block, Heading, StructureView
from obsidian_ops.templates import CreatePageResult, TemplateDefinition, TemplateField
from obsidian_ops.vault import Vault
from obsidian_ops.vcs import ReadinessCheck, SyncResult, UndoResult, VCSReadiness

__all__ = [
    "Vault",
    "SearchResult",
    "UndoResult",
    "VCSReadiness",
    "ReadinessCheck",
    "SyncResult",
    "Heading",
    "Block",
    "StructureView",
    "EnsureBlockResult",
    "TemplateField",
    "TemplateDefinition",
    "CreatePageResult",
    "VaultError",
    "PathError",
    "FileTooLargeError",
    "BusyError",
    "FrontmatterError",
    "ContentPatchError",
    "VCSError",
]
