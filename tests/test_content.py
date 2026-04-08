from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.content import find_block, find_heading
from obsidian_ops.errors import ContentPatchError
from obsidian_ops.vault import Vault

SAMPLE = """# Title
Intro paragraph.

## Summary
Summary content here.
More summary.

### Details
Detail content.

## Next Section
Tail.
"""


def test_find_heading_h2() -> None:
    bounds = find_heading(SAMPLE, "## Summary")
    assert bounds is not None
    start, end = bounds
    section = SAMPLE[start:end]
    assert section.startswith("Summary content here")


def test_find_heading_h1() -> None:
    bounds = find_heading(SAMPLE, "# Title")
    assert bounds is not None
    section = SAMPLE[bounds[0] : bounds[1]]
    assert section.startswith("Intro paragraph")


def test_find_heading_includes_subheadings() -> None:
    bounds = find_heading(SAMPLE, "## Summary")
    assert bounds is not None
    section = SAMPLE[bounds[0] : bounds[1]]
    assert "### Details" in section


def test_find_heading_stops_at_same_level() -> None:
    bounds = find_heading(SAMPLE, "## Summary")
    assert bounds is not None
    section = SAMPLE[bounds[0] : bounds[1]]
    assert "## Next Section" not in section


def test_find_heading_stops_at_higher_level() -> None:
    text = "# Top\n\n## Summary\nA\n# New Top\nB\n"
    bounds = find_heading(text, "## Summary")
    assert bounds is not None
    section = text[bounds[0] : bounds[1]]
    assert section == "A\n"


def test_find_heading_at_eof() -> None:
    text = "# Top\n\n## End\nFinal line"
    bounds = find_heading(text, "## End")
    assert bounds is not None
    section = text[bounds[0] : bounds[1]]
    assert section == "Final line"


def test_find_heading_not_found() -> None:
    assert find_heading(SAMPLE, "## Missing") is None


def test_find_heading_first_match() -> None:
    text = "## Summary\nFirst\n\n## Summary\nSecond\n"
    bounds = find_heading(text, "## Summary")
    assert bounds is not None
    section = text[bounds[0] : bounds[1]]
    assert section == "First\n\n"


def test_find_heading_non_heading_exact_match() -> None:
    text = "## Summary\nContent\n\nSummary\nNot a heading.\n"
    bounds = find_heading(text, "## Summary")
    assert bounds is not None
    section = text[bounds[0] : bounds[1]]
    assert section.startswith("Content")
    assert "Not a heading." in section


def test_write_heading_replaces(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_heading("note.md", "## Summary", "Updated summary.\n")

    result = vault.read_heading("note.md", "## Summary")
    assert result == "Updated summary.\n"


def test_write_heading_appends(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_heading("no-frontmatter.md", "## Added", "Appended content")

    text = vault.read_file("no-frontmatter.md")
    assert text.endswith("\n\n## Added\nAppended content")


def test_write_heading_appends_when_file_lacks_trailing_newline(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "plain.md").write_text("Plain body", encoding="utf-8")

    vault = Vault(vault_root)
    vault.write_heading("plain.md", "## Added", "Section body.\n")

    text = vault.read_file("plain.md")
    assert text == "Plain body\n\n## Added\nSection body.\n"


def test_find_block_paragraph() -> None:
    text = "Para one. ^ref\n\nPara two.\n"
    bounds = find_block(text, "^ref")
    assert bounds is not None
    assert text[bounds[0] : bounds[1]] == "Para one. ^ref\n"


def test_find_block_list_item() -> None:
    text = "- Item one\n- Item two ^list-ref\n\nAfter\n"
    bounds = find_block(text, "^list-ref")
    assert bounds is not None
    assert text[bounds[0] : bounds[1]] == "- Item two ^list-ref\n"


def test_find_block_no_substring_match() -> None:
    """Block ID must not match as a substring of a larger token."""
    text = "This has some^ref-block-extra text\n\nReal block ^ref-block\n"
    bounds = find_block(text, "^ref-block")
    assert bounds is not None
    matched = text[bounds[0] : bounds[1]]
    assert "Real block ^ref-block" in matched
    assert "extra" not in matched


def test_find_block_multi_line_paragraph() -> None:
    text = "Unrelated.\n\nFirst line of paragraph.\nSecond line.\nThird line with ^block-id\n\nAfter.\n"
    bounds = find_block(text, "^block-id")
    assert bounds is not None
    block = text[bounds[0] : bounds[1]]
    assert block.startswith("First line of paragraph.")
    assert "^block-id" in block


def test_find_block_not_found() -> None:
    assert find_block("No refs here\n", "^missing") is None


def test_write_block_replaces(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_block("note.md", "^ref-block", "Updated paragraph ^ref-block")

    block = vault.read_block("note.md", "^ref-block")
    assert block == "Updated paragraph ^ref-block\n"


def test_write_block_not_found_raises(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(ContentPatchError):
        vault.write_block("note.md", "^missing", "x")


def test_read_heading_via_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    section = vault.read_heading("note.md", "## Summary")
    assert section is not None
    assert "This is the summary section." in section


def test_read_heading_via_vault_missing_returns_none(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.read_heading("note.md", "## Missing") is None


def test_write_heading_via_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_heading("note.md", "## Summary", "Replaced\n")
    assert vault.read_heading("note.md", "## Summary") == "Replaced\n"


def test_read_block_via_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    block = vault.read_block("note.md", "^ref-block")
    assert block is not None
    assert "^ref-block" in block


def test_read_block_via_vault_missing_returns_none(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.read_block("note.md", "^missing") is None


def test_write_block_via_vault(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.write_block("note.md", "^list-ref", "- Updated list item ^list-ref")
    block = vault.read_block("note.md", "^list-ref")
    assert block == "- Updated list item ^list-ref\n"
