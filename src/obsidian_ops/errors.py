"""Exception hierarchy for obsidian-ops."""


class VaultError(Exception):
    """Base exception for obsidian-ops errors."""


class PathError(VaultError):
    """Raised when a path fails sandbox validation."""


class FileTooLargeError(VaultError):
    """Raised when a file exceeds read size limits."""


class BusyError(VaultError):
    """Raised when a mutation lock cannot be acquired."""


class FrontmatterError(VaultError):
    """Raised when frontmatter cannot be parsed or manipulated."""


class ContentPatchError(VaultError):
    """Raised when heading or block patching fails."""


class VCSError(VaultError):
    """Raised when Jujutsu operations fail."""
