from __future__ import annotations

from pathlib import Path

from obsidian_ops.page_context import resolve_page_path


def test_root_resolves_to_index(tmp_path: Path) -> None:
    (tmp_path / "index.md").write_text("home", encoding="utf-8")

    assert resolve_page_path(tmp_path, "/") == "index.md"


def test_nested_path_resolves_to_md_file(tmp_path: Path) -> None:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "foo.md").write_text("content", encoding="utf-8")

    assert resolve_page_path(tmp_path, "/notes/foo/") == "notes/foo.md"


def test_nested_path_falls_back_to_index(tmp_path: Path) -> None:
    nested = tmp_path / "notes" / "foo"
    nested.mkdir(parents=True)
    (nested / "index.md").write_text("content", encoding="utf-8")

    assert resolve_page_path(tmp_path, "/notes/foo/") == "notes/foo/index.md"


def test_nonexistent_returns_none(tmp_path: Path) -> None:
    assert resolve_page_path(tmp_path, "/nonexistent") is None


def test_prefix_stripping(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.md").write_text("ok", encoding="utf-8")

    assert resolve_page_path(tmp_path, "/app/docs/page", prefix="/app/") == "docs/page.md"
