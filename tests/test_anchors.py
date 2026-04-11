from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from obsidian_ops.errors import BusyError, PathError
from obsidian_ops.vault import Vault


@pytest.fixture
def anchor_vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    (root / "note.md").write_text("# Note\n\nLine one\nLine two\n", encoding="utf-8")
    return root


def test_existing_anchor_returns_created_false(anchor_vault: Path) -> None:
    path = anchor_vault / "note.md"
    path.write_text("# Note\n\nParagraph line ^existing\n", encoding="utf-8")

    result = Vault(anchor_vault).ensure_block_id("note.md", 3, 3)

    assert result.created is False
    assert result.block_id == "existing"


def test_new_anchor_is_written(anchor_vault: Path) -> None:
    vault = Vault(anchor_vault)

    result = vault.ensure_block_id("note.md", 3, 4)

    assert result.created is True
    updated = vault.read_file("note.md")
    assert f"^{result.block_id}" in updated


def test_concurrent_ensure_converges_on_single_anchor(anchor_vault: Path) -> None:
    vault = Vault(anchor_vault)

    def ensure_with_retry() -> str:
        for _ in range(50):
            try:
                return vault.ensure_block_id("note.md", 3, 4).block_id
            except BusyError:
                time.sleep(0.01)
        raise AssertionError("failed to acquire mutation lock")

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _i: ensure_with_retry(), [0, 1]))

    assert ids[0] == ids[1]
    assert vault.read_file("note.md").count(f"^{ids[0]}") == 1


def test_ensure_block_id_rejects_escape(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)
    with pytest.raises(PathError):
        vault.ensure_block_id("../secret.md", 1, 1)
