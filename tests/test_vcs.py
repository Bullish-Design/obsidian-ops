from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from obsidian_ops.errors import VCSError
from obsidian_ops.vault import Vault
from obsidian_ops.vcs import JJ


def test_describe_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.describe("msg")

    run.assert_called_once_with(
        ["jj", "describe", "-m", "msg"],
        cwd=tmp_vault,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_new_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.new()

    run.assert_called_once()
    assert run.call_args.args[0] == ["jj", "new"]


def test_commit_runs_describe_then_new(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        vault.commit("hello")

    assert run.call_args_list == [
        call(
            ["jj", "describe", "-m", "hello"],
            cwd=tmp_vault,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        ),
        call(
            ["jj", "new"],
            cwd=tmp_vault,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        ),
    ]


def test_undo_runs_correct_command(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        vault.undo()

    run.assert_called_once()
    assert run.call_args.args[0] == ["jj", "undo"]


def test_status_returns_output(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="status out", stderr="")
        result = jj.status()

    assert result == "status out"


def test_nonzero_exit_raises_vcserror(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=1, stdout="bad", stderr="worse")
        with pytest.raises(VCSError) as exc:
            jj.status()

    message = str(exc.value)
    assert "stdout: bad" in message
    assert "stderr: worse" in message


def test_timeout_raises_vcserror(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run", side_effect=subprocess.TimeoutExpired(["jj"], timeout=120)):
        with pytest.raises(VCSError):
            jj.status()


def test_missing_binary_raises_vcserror(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault, jj_bin="missing-jj")

    with patch("obsidian_ops.vcs.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(VCSError):
            jj.status()


def test_commit_acquires_lock(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    class StubJJ:
        def describe(self, message: str) -> None:
            assert vault.is_busy() is True

        def new(self) -> None:
            assert vault.is_busy() is True

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    vault.commit("msg")
    assert vault.is_busy() is False


def test_undo_acquires_lock(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    class StubJJ:
        def undo(self) -> None:
            assert vault.is_busy() is True

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    vault.undo()
    assert vault.is_busy() is False


def test_status_no_lock(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    class StubJJ:
        def status(self) -> str:
            assert vault.is_busy() is False
            return "ok"

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    assert vault.vcs_status() == "ok"
