from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_ops.errors import FrontmatterError
from obsidian_ops.frontmatter import parse_frontmatter, serialize_frontmatter
from obsidian_ops.vault import Vault

FRONTMATTER_TEXT = """---
title: My Note
tags: [project, active]
metadata:
  created: 2024-01-15
---
# Content starts here
Paragraph.
"""


NO_FRONTMATTER_TEXT = "# Content starts here\nParagraph.\n"


def test_parse_valid() -> None:
    data, body = parse_frontmatter(FRONTMATTER_TEXT)
    assert data == {
        "title": "My Note",
        "tags": ["project", "active"],
        "metadata": {"created": "2024-01-15"},
    }
    assert body == "# Content starts here\nParagraph.\n"


def test_parse_no_frontmatter() -> None:
    data, body = parse_frontmatter(NO_FRONTMATTER_TEXT)
    assert data is None
    assert body == NO_FRONTMATTER_TEXT


def test_parse_malformed_yaml() -> None:
    broken = "---\ntitle: [not closed\n---\nBody\n"
    with pytest.raises(FrontmatterError):
        parse_frontmatter(broken)


def test_parse_preserves_body() -> None:
    _data, body = parse_frontmatter(FRONTMATTER_TEXT)
    assert body == "# Content starts here\nParagraph.\n"


def test_parse_with_bom() -> None:
    data, body = parse_frontmatter("\ufeff" + FRONTMATTER_TEXT)
    assert data is not None
    assert data["title"] == "My Note"
    assert body == "# Content starts here\nParagraph.\n"


def test_parse_frontmatter_crlf_body_separator() -> None:
    text = "---\ntitle: Test\n---\r\nBody here."
    data, body = parse_frontmatter(text)
    assert data == {"title": "Test"}
    assert body == "Body here."


def test_parse_frontmatter_none_yaml_block() -> None:
    text = "---\n# just a comment\n---\nBody."
    data, body = parse_frontmatter(text)
    assert data == {}
    assert body == "Body."


def test_parse_frontmatter_non_dict_raises() -> None:
    text = "---\n- item1\n- item2\n---\nBody."
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter(text)


def test_serialize_roundtrip() -> None:
    data, body = parse_frontmatter(FRONTMATTER_TEXT)
    assert data is not None

    rendered = serialize_frontmatter(data, body)
    roundtrip_data, roundtrip_body = parse_frontmatter(rendered)

    assert roundtrip_data == data
    assert roundtrip_body == body


def test_get_frontmatter(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert data["title"] == "Test Note"


def test_get_frontmatter_none(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    assert vault.get_frontmatter("no-frontmatter.md") is None


def test_set_frontmatter(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.set_frontmatter("note.md", {"status": "done"})

    data = vault.get_frontmatter("note.md")
    assert data == {"status": "done"}


def test_set_frontmatter_no_existing(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.set_frontmatter("no-frontmatter.md", {"status": "new"})

    data = vault.get_frontmatter("no-frontmatter.md")
    assert data == {"status": "new"}


def test_update_frontmatter_merge(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.update_frontmatter("note.md", {"status": "published"})

    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert data["status"] == "published"


def test_update_frontmatter_preserves_unmentioned(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.update_frontmatter("note.md", {"status": "published"})

    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert data["title"] == "Test Note"
    assert data["tags"] == ["test", "sample"]


def test_update_frontmatter_shallow(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.set_frontmatter(
        "note.md",
        {
            "metadata": {"created": "2024-01-15", "author": "Alice"},
            "status": "draft",
        },
    )
    vault.update_frontmatter("note.md", {"metadata": {"reviewed": True}})

    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert data["metadata"] == {"reviewed": True}
    assert data["status"] == "draft"


def test_update_frontmatter_creates_new(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.update_frontmatter("no-frontmatter.md", {"status": "active"})

    data = vault.get_frontmatter("no-frontmatter.md")
    assert data == {"status": "active"}


def test_delete_frontmatter_field(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.delete_frontmatter_field("note.md", "status")

    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert "status" not in data


def test_delete_frontmatter_field_nonexistent(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    vault.delete_frontmatter_field("note.md", "does_not_exist")

    data = vault.get_frontmatter("note.md")
    assert data is not None
    assert data["title"] == "Test Note"


def test_delete_frontmatter_field_no_frontmatter_no_change(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    path = tmp_vault / "no-frontmatter.md"
    before = path.read_text(encoding="utf-8")

    vault.delete_frontmatter_field("no-frontmatter.md", "anything")

    after = path.read_text(encoding="utf-8")
    assert after == before


def test_body_preserved_after_set(tmp_vault: Path) -> None:
    path = tmp_vault / "note.md"
    before = parse_frontmatter(path.read_text(encoding="utf-8"))[1]

    vault = Vault(tmp_vault)
    vault.set_frontmatter("note.md", {"status": "done"})

    after = parse_frontmatter(path.read_text(encoding="utf-8"))[1]
    assert after == before


def test_body_preserved_after_update(tmp_vault: Path) -> None:
    path = tmp_vault / "note.md"
    before = parse_frontmatter(path.read_text(encoding="utf-8"))[1]

    vault = Vault(tmp_vault)
    vault.update_frontmatter("note.md", {"status": "done"})

    after = parse_frontmatter(path.read_text(encoding="utf-8"))[1]
    assert after == before
