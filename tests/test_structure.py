from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from obsidian_ops.errors import PathError
from obsidian_ops.vault import Vault


def test_mixed_heading_levels_have_correct_ranges(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "doc.md").write_text(
        "# Top\n\n## One\nBody 1\n\n### Nested\nNested body\n\n## Two\nBody 2\n",
        encoding="utf-8",
    )

    view = Vault(root).list_structure("doc.md")

    assert [h.text for h in view.headings] == ["# Top", "## One", "### Nested", "## Two"]
    assert [(h.text, h.line_start, h.line_end) for h in view.headings] == [
        ("# Top", 1, 10),
        ("## One", 3, 8),
        ("### Nested", 6, 8),
        ("## Two", 9, 10),
    ]


def test_multiline_paragraph_anchor_has_correct_span(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    text = "# Note\n\nLine a\nLine b\nLine c ^anchor-1\n\nTail\n"
    (root / "note.md").write_text(text, encoding="utf-8")

    view = Vault(root).list_structure("note.md")

    assert len(view.blocks) == 1
    block = view.blocks[0]
    assert block.block_id == "anchor-1"
    assert (block.line_start, block.line_end) == (3, 5)


def test_empty_file_returns_valid_structure_and_hash(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "empty.md").write_text("", encoding="utf-8")

    view = Vault(root).list_structure("empty.md")

    assert view.path == "empty.md"
    assert view.headings == []
    assert view.blocks == []
    assert view.sha256 == hashlib.sha256(b"").hexdigest()


def test_list_structure_rejects_path_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.list_structure("../outside.md")
