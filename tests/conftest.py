from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "tmp_vault"
    vault.mkdir()

    (vault / "note.md").write_text(
        """---
title: Test Note
tags: [test, sample]
status: draft
---

# Test Note

Introduction paragraph.

## Summary

This is the summary section.
It has multiple lines.

### Details

Some details here.

## References

A paragraph with a block reference. ^ref-block

- List item one
- Important list item ^list-ref
""",
        encoding="utf-8",
    )

    (vault / "no-frontmatter.md").write_text("# Plain note\n\nNo frontmatter here.\n", encoding="utf-8")

    projects = vault / "Projects"
    projects.mkdir()
    (projects / "Alpha.md").write_text(
        "---\nstatus: active\n---\n\n# Alpha\n\n## Summary\n\nAlpha summary.\n",
        encoding="utf-8",
    )
    (projects / "Beta.md").write_text("# Beta\n\nBeta content.\n", encoding="utf-8")

    hidden = vault / ".hidden"
    hidden.mkdir()
    (hidden / "secret.md").write_text("classified\n", encoding="utf-8")

    prefixed_hidden = vault / "_hidden_dir"
    prefixed_hidden.mkdir()
    (prefixed_hidden / "internal.md").write_text("internal\n", encoding="utf-8")

    outside = tmp_path / "outside"
    outside.mkdir()

    symlink = vault / "symlink_escape"
    try:
        symlink.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Symlinks may be unavailable on some systems; tests can skip as needed.
        pass

    return vault
