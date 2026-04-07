from __future__ import annotations

from pathlib import Path

from obsidian_ops.search import MAX_READ_SIZE, search_content, walk_vault


def test_walk_default_glob(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "*.md", max_results=200)

    assert "note.md" in results
    assert "no-frontmatter.md" in results
    assert "Projects/Alpha.md" in results
    assert "Projects/Beta.md" in results


def test_walk_subdirectory_glob(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "Projects/*.md", max_results=200)
    assert results == ["Projects/Alpha.md", "Projects/Beta.md"]


def test_walk_skips_dotfiles(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "*.md", max_results=200)
    assert ".hidden/secret.md" not in results


def test_walk_skips_hidden_prefix(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "*.md", max_results=200)
    assert "_hidden_dir/internal.md" not in results


def test_walk_max_results(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "*.md", max_results=2)
    assert len(results) == 2


def test_walk_sorted(tmp_vault: Path) -> None:
    results = walk_vault(tmp_vault, "*.md", max_results=200)
    assert results == sorted(results)


def test_search_finds_match(tmp_vault: Path) -> None:
    files = walk_vault(tmp_vault, "*.md", max_results=200)
    results = search_content(tmp_vault, "summary", files, max_results=50)

    assert any(result.path == "note.md" for result in results)


def test_search_case_insensitive(tmp_vault: Path) -> None:
    files = walk_vault(tmp_vault, "*.md", max_results=200)
    lower = search_content(tmp_vault, "summary", files, max_results=50)
    upper = search_content(tmp_vault, "SUMMARY", files, max_results=50)

    assert [r.path for r in lower] == [r.path for r in upper]


def test_search_snippet_context(tmp_vault: Path) -> None:
    files = walk_vault(tmp_vault, "note.md", max_results=200)
    results = search_content(tmp_vault, "Introduction", files, max_results=50)

    assert len(results) == 1
    assert "Introduction paragraph" in results[0].snippet


def test_search_respects_glob(tmp_vault: Path) -> None:
    files = walk_vault(tmp_vault, "Projects/*.md", max_results=200)
    results = search_content(tmp_vault, "summary", files, max_results=50)

    assert all(result.path.startswith("Projects/") for result in results)


def test_search_max_results(tmp_vault: Path) -> None:
    files = walk_vault(tmp_vault, "*.md", max_results=200)
    results = search_content(tmp_vault, "#", files, max_results=1)
    assert len(results) == 1


def test_search_skips_large_files(tmp_vault: Path) -> None:
    big = tmp_vault / "big.md"
    big.write_text("A" * (MAX_READ_SIZE + 1), encoding="utf-8")

    files = walk_vault(tmp_vault, "*.md", max_results=200)
    results = search_content(tmp_vault, "A", files, max_results=200)

    assert all(result.path != "big.md" for result in results)
