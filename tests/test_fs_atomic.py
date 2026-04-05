from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.fs_atomic import read_file_safe, validate_vault_path, write_file_atomic


def test_write_new_file_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "note.md"

    write_file_atomic(path, "hello")

    assert read_file_safe(path) == "hello"


def test_write_existing_file_replaces_contents(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("old", encoding="utf-8")

    write_file_atomic(path, "new")

    assert path.read_text(encoding="utf-8") == "new"


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "nested.md"

    write_file_atomic(path, "content")

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "content"


def test_read_file_rejects_above_one_mb(tmp_path: Path) -> None:
    path = tmp_path / "large.md"
    path.write_text("x" * ((1024 * 1024) + 1), encoding="utf-8")

    with pytest.raises(ValueError):
        read_file_safe(path)


def test_read_file_warns_above_256kb(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "large-ish.md"
    path.write_text("x" * ((256 * 1024) + 1), encoding="utf-8")

    with caplog.at_level("WARNING"):
        text = read_file_safe(path)

    assert len(text) == (256 * 1024) + 1
    assert "Reading large file" in caplog.text


def test_validate_vault_path_accepts_valid_relative_path(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    resolved = validate_vault_path(vault_root, Path("notes/example.md"))

    assert resolved == (vault_root / "notes" / "example.md").resolve()


@pytest.mark.parametrize("target", [Path("../escape.md"), Path("notes/../../escape.md")])
def test_validate_vault_path_rejects_dotdot(tmp_path: Path, target: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with pytest.raises(ValueError):
        validate_vault_path(vault_root, target)


@pytest.mark.parametrize(
    "target",
    [Path(".jj/oplog"), Path(".obsidian/workspace"), Path(".git/config"), Path("__pycache__/x.pyc")],
)
def test_validate_vault_path_rejects_protected_directories(tmp_path: Path, target: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with pytest.raises(ValueError):
        validate_vault_path(vault_root, target)


def test_validate_vault_path_rejects_absolute_outside_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    outside = tmp_path.parent / "outside.md"
    with pytest.raises(ValueError):
        validate_vault_path(vault_root, outside)
