from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.errors import PathError
from obsidian_ops.sandbox import validate_path


def test_valid_simple(tmp_vault: Path) -> None:
    assert validate_path(tmp_vault, "note.md") == tmp_vault / "note.md"


def test_valid_nested(tmp_vault: Path) -> None:
    assert validate_path(tmp_vault, "Projects/Alpha.md") == tmp_vault / "Projects/Alpha.md"


def test_valid_spaces(tmp_vault: Path) -> None:
    path = validate_path(tmp_vault, "My Notes/file name.md")
    assert path == tmp_vault / "My Notes/file name.md"


def test_valid_unicode(tmp_vault: Path) -> None:
    path = validate_path(tmp_vault, "日本語/ノート.md")
    assert path == tmp_vault / "日本語/ノート.md"


def test_valid_normalization(tmp_vault: Path) -> None:
    path = validate_path(tmp_vault, "Projects/../Alpha.md")
    assert path == tmp_vault / "Alpha.md"


def test_reject_absolute(tmp_vault: Path) -> None:
    with pytest.raises(PathError):
        validate_path(tmp_vault, "/etc/passwd")


def test_reject_traversal(tmp_vault: Path) -> None:
    with pytest.raises(PathError):
        validate_path(tmp_vault, "../../secrets.txt")


def test_reject_sneaky_traversal(tmp_vault: Path) -> None:
    with pytest.raises(PathError):
        validate_path(tmp_vault, "a/b/../../../etc/passwd")


def test_reject_empty(tmp_vault: Path) -> None:
    with pytest.raises(PathError):
        validate_path(tmp_vault, "")


def test_validate_path_dot_resolves_to_root(tmp_vault: Path) -> None:
    with pytest.raises(PathError, match="vault root"):
        validate_path(tmp_vault, "./")


def test_reject_symlink_escape(tmp_vault: Path) -> None:
    symlink_path = tmp_vault / "symlink_escape"
    if not symlink_path.is_symlink():
        pytest.skip("symlink unsupported in this environment")

    with pytest.raises(PathError):
        validate_path(tmp_vault, "symlink_escape")


def test_new_file_validates_parent(tmp_vault: Path) -> None:
    path = validate_path(tmp_vault, "Projects/New.md")
    assert path == tmp_vault / "Projects/New.md"


def test_new_file_in_nonexistent_parent(tmp_vault: Path) -> None:
    path = validate_path(tmp_vault, "Future/Folder/New.md")
    assert path == tmp_vault / "Future/Folder/New.md"


def test_validate_path_new_file_parent_escape(tmp_vault: Path) -> None:
    symlink_path = tmp_vault / "symlink_escape"
    if not symlink_path.is_symlink():
        pytest.skip("symlink unsupported in this environment")

    with pytest.raises(PathError, match="parent escapes"):
        validate_path(tmp_vault, "symlink_escape/secret.md")
