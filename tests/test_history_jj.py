from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from obsidian_ops.history_jj import JujutsuHistory


@pytest.fixture
def jj_workspace(tmp_path: Path) -> Path:
    subprocess.run(["jj", "git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    return tmp_path


@pytest.mark.asyncio
async def test_ensure_workspace_succeeds(jj_workspace: Path) -> None:
    history = JujutsuHistory(jj_workspace)
    await history.ensure_workspace()


@pytest.mark.asyncio
async def test_ensure_workspace_fails_for_non_workspace(tmp_path: Path) -> None:
    history = JujutsuHistory(tmp_path)
    with pytest.raises(RuntimeError, match="Jujutsu workspace"):
        await history.ensure_workspace()


@pytest.mark.asyncio
async def test_commit_and_log_for_file(jj_workspace: Path) -> None:
    note = jj_workspace / "note.md"
    note.write_text("hello", encoding="utf-8")

    history = JujutsuHistory(jj_workspace)
    await history.commit("first commit")

    entries = await history.log_for_file("note.md", limit=10)
    assert entries
    assert any("first commit" in line for line in entries)


@pytest.mark.asyncio
async def test_commit_then_undo(jj_workspace: Path) -> None:
    note = jj_workspace / "note.md"
    note.write_text("v1", encoding="utf-8")

    history = JujutsuHistory(jj_workspace)
    await history.commit("first")

    note.write_text("v2", encoding="utf-8")
    await history.commit("second")

    before = await history.log_for_file("note.md", limit=10)
    assert any("second" in line for line in before)

    await history.undo()

    after = await history.log_for_file("note.md", limit=10)
    assert not any("second" in line for line in after)
