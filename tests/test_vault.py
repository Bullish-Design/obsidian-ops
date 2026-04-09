from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.errors import FileTooLargeError, PathError, VaultError
from obsidian_ops.vault import MAX_READ_SIZE, Vault


def test_init_valid_root(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.root == tmp_vault.resolve()


def test_init_invalid_root(tmp_path: Path) -> None:
    with pytest.raises(VaultError):
        Vault(tmp_path / "missing")


def test_init_file_not_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(VaultError):
        Vault(file_path)


def test_read_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    content = vault.read_file("note.md")
    assert "# Test Note" in content


def test_read_file_not_found(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(FileNotFoundError):
        vault.read_file("missing.md")


def test_read_file_too_large(tmp_vault: Path) -> None:
    big = tmp_vault / "large.md"
    big.write_text("A" * (MAX_READ_SIZE + 1), encoding="utf-8")

    vault = Vault(tmp_vault)
    with pytest.raises(FileTooLargeError):
        vault.read_file("large.md")


def test_read_file_path_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.read_file("../secrets.md")


def test_write_file_new(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_file("New/Note.md", "hello")

    assert (tmp_vault / "New/Note.md").read_text(encoding="utf-8") == "hello"


def test_write_file_overwrite(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_file("note.md", "changed")

    assert (tmp_vault / "note.md").read_text(encoding="utf-8") == "changed"


def test_write_file_path_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.write_file("../bad.md", "x")


def test_delete_file(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.delete_file("Projects/Beta.md")
    assert not (tmp_vault / "Projects/Beta.md").exists()


def test_delete_file_not_found(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(FileNotFoundError):
        vault.delete_file("Projects/Missing.md")


def test_list_files_default(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    results = vault.list_files()
    assert "note.md" in results


def test_list_files_glob_pattern(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    results = vault.list_files("Projects/*.md")
    assert results == ["Projects/Alpha.md", "Projects/Beta.md"]


def test_list_files_skips_hidden(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    results = vault.list_files("*.md")
    assert ".hidden/secret.md" not in results
    assert "_hidden_dir/internal.md" not in results


def test_search_files_basic(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    results = vault.search_files("summary")
    assert any(r.path == "note.md" for r in results)


def test_is_busy(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    def fake_write(path: str, content: str) -> None:
        assert vault.is_busy() is True

    monkeypatch.setattr(vault, "_unsafe_write_file", fake_write)
    assert vault.is_busy() is False

    vault.write_file("ignored.md", "ignored")
    assert vault.is_busy() is False


def test_update_frontmatter_nested_merge_preserves_body(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.set_frontmatter(
        "note.md",
        {
            "title": "Test Note",
            "metadata": {
                "created": "2024-01-15",
                "review": {"status": "pending", "owner": "Alice"},
            },
        },
    )
    before_body = vault.read_file("note.md").split("---\n", maxsplit=2)[2]

    vault.update_frontmatter("note.md", {"metadata": {"review": {"status": "approved"}}})

    updated = vault.get_frontmatter("note.md")
    assert updated == {
        "title": "Test Note",
        "metadata": {
            "created": "2024-01-15",
            "review": {"status": "approved", "owner": "Alice"},
        },
    }
    after_body = vault.read_file("note.md").split("---\n", maxsplit=2)[2]
    assert after_body == before_body


def test_write_heading_missing_section_repeat_write_keeps_single_heading(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    vault.write_heading("no-frontmatter.md", "## Added", "First pass.")
    vault.write_heading("no-frontmatter.md", "## Added", "Second pass.")

    text = vault.read_file("no-frontmatter.md")
    assert text.count("## Added\n") == 1
    assert text.endswith("\n\n## Added\nSecond pass.\n")
