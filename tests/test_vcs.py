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


def test_restore_from_previous_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.restore_from_previous()

    run.assert_called_once()
    assert run.call_args.args[0] == ["jj", "restore", "--from", "@-"]


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


def test_undo_last_change_runs_undo_then_restore(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = vault.undo_last_change()

    assert result.restored is True
    assert result.warning is None
    assert run.call_args_list == [
        call(
            ["jj", "undo"],
            cwd=tmp_vault,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        ),
        call(
            ["jj", "restore", "--from", "@-"],
            cwd=tmp_vault,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        ),
    ]


def test_undo_last_change_raises_when_undo_fails(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.side_effect = [
            SimpleNamespace(returncode=1, stdout="bad", stderr="worse"),
        ]
        with pytest.raises(VCSError):
            vault.undo_last_change()

    assert run.call_count == 1


def test_undo_last_change_returns_warning_when_restore_fails(tmp_vault: Path) -> None:
    vault = Vault(tmp_vault)

    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=1, stdout="bad", stderr="worse"),
        ]
        result = vault.undo_last_change()

    assert result.restored is False
    assert result.warning is not None
    assert "restore after undo failed" in result.warning


def test_undo_last_change_acquires_lock(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    class StubJJ:
        def undo(self) -> None:
            assert vault.is_busy() is True

        def restore_from_previous(self) -> None:
            assert vault.is_busy() is True

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    result = vault.undo_last_change()
    assert result.restored is True
    assert vault.is_busy() is False


def test_status_no_lock(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Vault(tmp_vault)

    class StubJJ:
        def status(self) -> str:
            assert vault.is_busy() is False
            return "ok"

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())

    assert vault.vcs_status() == "ok"


def test_git_init_colocate_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_init_colocate()
    assert run.call_args.args[0] == ["jj", "git", "init", "--colocate"]


def test_git_fetch_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_fetch(remote="upstream")
    assert run.call_args.args[0] == ["jj", "git", "fetch", "--remote", "upstream"]


def test_git_fetch_passes_env_overrides(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_fetch(env={"GIT_ASKPASS": "/tmp/askpass.sh"})
    env = run.call_args.kwargs["env"]
    assert env is not None
    assert env["GIT_ASKPASS"] == "/tmp/askpass.sh"


def test_git_push_builds_args(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_push(remote="origin", bookmark="main", allow_new=True)
    assert run.call_args.args[0] == ["jj", "git", "push", "--remote", "origin", "-b", "main", "--allow-new"]


def test_rebase_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.rebase(destination="trunk()")
    assert run.call_args.args[0] == ["jj", "rebase", "-d", "trunk()"]


def test_bookmark_create_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.bookmark_create("sync-conflict/abc", revision="@")
    assert run.call_args.args[0] == ["jj", "bookmark", "create", "sync-conflict/abc", "-r", "@"]


def test_bookmark_list_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.bookmark_list()
    assert run.call_args.args[0] == ["jj", "bookmark", "list"]


def test_git_remote_add_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_remote_add("origin", "https://github.com/example/repo.git")
    assert run.call_args.args[0] == ["jj", "git", "remote", "add", "origin", "https://github.com/example/repo.git"]


def test_git_remote_set_url_removes_then_adds(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.git_remote_set_url("origin", "https://github.com/example/repo.git")
    assert run.call_args_list[0].args[0] == ["jj", "git", "remote", "remove", "origin"]
    assert run.call_args_list[1].args[0] == ["jj", "git", "remote", "add", "origin", "https://github.com/example/repo.git"]


def test_git_remote_list_runs_correct_command(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="origin\n", stderr="")
        result = jj.git_remote_list()
    assert run.call_args.args[0] == ["jj", "git", "remote", "list"]
    assert result == "origin\n"


def test_log_runs_with_default_no_graph(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.log()
    assert run.call_args.args[0] == ["jj", "log", "-r", "@", "-T", "builtin_log_oneline", "--no-graph"]


def test_log_can_disable_no_graph(tmp_vault: Path) -> None:
    jj = JJ(tmp_vault)
    with patch("obsidian_ops.vcs.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        jj.log(no_graph=False)
    assert run.call_args.args[0] == ["jj", "log", "-r", "@", "-T", "builtin_log_oneline"]
