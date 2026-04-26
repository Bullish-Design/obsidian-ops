from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from obsidian_ops.errors import VCSError
from obsidian_ops.vault import Vault
from obsidian_ops.vcs import JJ, ReadinessCheck, VCSReadiness


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


def test_check_sync_readiness_no_vcs(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    result = Vault(vault_root).check_sync_readiness()
    assert result.status == VCSReadiness.MIGRATION_NEEDED
    assert result.detail == "no vcs initialized"


def test_check_sync_readiness_jj_with_remote_is_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".jj").mkdir(parents=True)
    vault = Vault(vault_root)

    class StubJJ:
        def git_remote_list(self) -> str:
            return "origin\n"

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.READY
    assert result.detail is None


def test_check_sync_readiness_jj_no_remote_is_ready_with_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".jj").mkdir(parents=True)
    vault = Vault(vault_root)

    class StubJJ:
        def git_remote_list(self) -> str:
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.READY
    assert result.detail == "no remote configured"


def test_check_sync_readiness_git_only_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "_is_git_dirty", lambda _root: False)
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.MIGRATION_NEEDED
    assert result.detail == "git-only, safe to colocate"


def test_check_sync_readiness_git_only_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "_is_git_dirty", lambda _root: True)
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.MIGRATION_NEEDED
    assert result.detail == "git-only with uncommitted changes"


def test_check_sync_readiness_git_and_jj_is_migration_needed_when_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    (vault_root / ".jj").mkdir(parents=True)
    vault = Vault(vault_root)

    class StubJJ:
        def git_remote_list(self) -> str:
            raise VCSError("broken colocated state")

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.MIGRATION_NEEDED
    assert result.detail == "colocated state needs verification"


def test_check_sync_readiness_git_and_jj_can_be_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    (vault_root / ".jj").mkdir(parents=True)
    vault = Vault(vault_root)

    class StubJJ:
        def git_remote_list(self) -> str:
            return "origin\n"

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.check_sync_readiness()
    assert result.status == VCSReadiness.READY
    assert result.detail is None


def test_check_sync_readiness_never_mutates(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    _ = vault.check_sync_readiness()
    assert not (vault_root / ".jj").exists()


def test_ensure_sync_ready_initializes_when_no_vcs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    calls: list[str] = []

    class StubJJ:
        def git_init_colocate(self) -> str:
            calls.append("init")
            (vault_root / ".jj").mkdir(exist_ok=True)
            return ""

        def git_remote_list(self) -> str:
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.ensure_sync_ready()
    assert calls == ["init"]
    assert result.status == VCSReadiness.READY
    assert (vault_root / ".jj").exists()


def test_ensure_sync_ready_initializes_when_git_only_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "_is_git_dirty", lambda _root: False)
    calls: list[str] = []

    class StubJJ:
        def git_init_colocate(self) -> str:
            calls.append("init")
            (vault_root / ".jj").mkdir(exist_ok=True)
            return ""

        def git_remote_list(self) -> str:
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.ensure_sync_ready()
    assert calls == ["init"]
    assert result.status == VCSReadiness.READY
    assert result.detail == "no remote configured"


def test_ensure_sync_ready_does_not_mutate_git_only_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / ".git").mkdir(parents=True)
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "_is_git_dirty", lambda _root: True)

    class StubJJ:
        def git_init_colocate(self) -> str:
            pytest.fail("should not initialize when git working tree is dirty")

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.ensure_sync_ready()
    assert result.status == VCSReadiness.MIGRATION_NEEDED
    assert result.detail == "git-only with uncommitted changes"
    assert not (vault_root / ".jj").exists()


def test_configure_sync_remote_with_token_writes_helper_and_adds_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))
    calls: list[tuple[str, str, str]] = []

    class StubJJ:
        def git_remote_add(self, name: str, url: str) -> str:
            calls.append(("add", name, url))
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    vault.configure_sync_remote("https://github.com/example/repo.git", token="secret", remote="origin")

    helper = vault_root / ".forge" / "git-credential.sh"
    assert helper.exists()
    assert helper.stat().st_mode & 0o777 == 0o700
    content = helper.read_text(encoding="utf-8")
    assert "password=secret" in content
    assert calls == [("add", "origin", "https://github.com/example/repo.git")]


def test_configure_sync_remote_without_token_clears_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    helper = vault_root / ".forge" / "git-credential.sh"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text("old", encoding="utf-8")

    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))

    class StubJJ:
        def git_remote_add(self, _name: str, _url: str) -> str:
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    vault.configure_sync_remote("https://github.com/example/repo.git", token=None)
    assert not helper.exists()


def test_sync_fetch_passes_askpass_env_when_helper_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    helper = vault_root / ".forge" / "git-credential.sh"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))
    seen_env: dict[str, str] | None = None

    class StubJJ:
        def git_fetch(self, *, remote: str = "origin", env: dict[str, str] | None = None) -> str:
            nonlocal seen_env
            assert remote == "origin"
            seen_env = env
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    vault.sync_fetch()
    assert seen_env is not None
    assert seen_env["GIT_ASKPASS"].endswith("git-credential.sh")


def test_sync_status_returns_empty_without_prior_sync(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    assert vault.sync_status() == {}


def test_sync_happy_path_persists_success_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))
    monkeypatch.setattr(vault, "_has_rebase_conflict", lambda: False)
    monkeypatch.setattr(vault, "_now_iso", lambda: "2026-04-26T12:34:56+00:00")
    calls: list[str] = []

    class StubJJ:
        def git_fetch(self, *, remote: str = "origin", env: dict[str, str] | None = None) -> str:
            calls.append("fetch")
            return ""

        def rebase(self, *, destination: str = "trunk()") -> str:
            calls.append(f"rebase:{destination}")
            return ""

        def git_push(
            self,
            *,
            remote: str = "origin",
            bookmark: str | None = None,
            allow_new: bool = False,
            env: dict[str, str] | None = None,
        ) -> str:
            calls.append(f"push:{remote}:{bookmark}:{allow_new}")
            return ""

        def bookmark_create(self, name: str, *, revision: str = "@") -> str:
            calls.append(f"bookmark:{name}:{revision}")
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.sync()
    assert result.ok is True
    assert result.conflict is False
    assert calls == ["fetch", "rebase:trunk()", "bookmark:main:@-", "push:origin:main:True"]
    assert vault.sync_status()["last_sync_ok"] is True


def test_sync_conflict_creates_bookmark_and_persists_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))
    monkeypatch.setattr(vault, "_has_rebase_conflict", lambda: True)
    monkeypatch.setattr(vault, "_create_conflict_bookmark", lambda _prefix: "sync-conflict/2026-04-26T12-34-56Z")
    monkeypatch.setattr(vault, "_now_iso", lambda: "2026-04-26T12:34:56+00:00")
    pushed_bookmarks: list[str | None] = []

    class StubJJ:
        def git_fetch(self, *, remote: str = "origin", env: dict[str, str] | None = None) -> str:
            return ""

        def rebase(self, *, destination: str = "trunk()") -> str:
            return ""

        def git_push(
            self,
            *,
            remote: str = "origin",
            bookmark: str | None = None,
            allow_new: bool = False,
            env: dict[str, str] | None = None,
        ) -> str:
            pushed_bookmarks.append(bookmark)
            return ""

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.sync()
    assert result.ok is False
    assert result.conflict is True
    assert result.conflict_bookmark == "sync-conflict/2026-04-26T12-34-56Z"
    assert pushed_bookmarks == ["sync-conflict/2026-04-26T12-34-56Z"]
    status = vault.sync_status()
    assert status["conflict_active"] is True
    assert status["conflict_bookmark"] == "sync-conflict/2026-04-26T12-34-56Z"


def test_sync_fetch_failure_returns_error_and_persists_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    monkeypatch.setattr(vault, "ensure_sync_ready", lambda: ReadinessCheck(status=VCSReadiness.READY))
    monkeypatch.setattr(vault, "_now_iso", lambda: "2026-04-26T12:34:56+00:00")

    class StubJJ:
        def git_fetch(self, *, remote: str = "origin", env: dict[str, str] | None = None) -> str:
            raise VCSError("network failure")

    monkeypatch.setattr(vault, "_get_jj", lambda: StubJJ())
    result = vault.sync()
    assert result.ok is False
    assert "network failure" in (result.error or "")
    status = vault.sync_status()
    assert status["last_sync_ok"] is False
    assert status["conflict_active"] is False
