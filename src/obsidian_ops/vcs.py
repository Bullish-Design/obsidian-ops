"""Jujutsu VCS wrapper."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from obsidian_ops.errors import VCSError


@dataclass(frozen=True)
class UndoResult:
    """Outcome of the high-level undo lifecycle."""

    restored: bool
    warning: str | None = None


class VCSReadiness(Enum):
    """Whether the vault is ready for sync operations."""

    READY = "ready"
    MIGRATION_NEEDED = "migration_needed"
    ERROR = "error"


@dataclass(frozen=True)
class ReadinessCheck:
    """Result of inspecting vault VCS state."""

    status: VCSReadiness
    detail: str | None = None


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync cycle."""

    ok: bool
    conflict: bool = False
    conflict_bookmark: str | None = None
    error: str | None = None


class JJ:
    """Thin wrapper around `jj` subprocess calls."""

    def __init__(self, cwd: Path, *, jj_bin: str = "jj", timeout: int = 120) -> None:
        self.cwd = cwd
        self.jj_bin = jj_bin
        self.timeout = timeout

    def _run(self, *args: str, env: Mapping[str, str] | None = None) -> str:
        cmd = [self.jj_bin, *args]
        run_kwargs: dict[str, object] = {}
        if env is not None:
            run_kwargs["env"] = {**os.environ, **env}
        try:
            result = subprocess.run(
                cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                **run_kwargs,
            )
        except FileNotFoundError as exc:
            raise VCSError(f"jj binary not found: {self.jj_bin}") from exc
        except subprocess.TimeoutExpired as exc:
            raise VCSError(f"jj command timed out after {self.timeout}s: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            raise VCSError(f"jj command failed: {' '.join(cmd)}\nstdout: {stdout}\nstderr: {stderr}")

        return result.stdout

    def describe(self, message: str) -> None:
        self._run("describe", "-m", message)

    def new(self) -> None:
        self._run("new")

    def undo(self) -> None:
        self._run("undo")

    def restore_from_previous(self) -> None:
        self._run("restore", "--from", "@-")

    def status(self) -> str:
        return self._run("status")

    def git_init_colocate(self) -> str:
        """Initialize a colocated jj+git workspace."""
        return self._run("git", "init", "--colocate")

    def git_fetch(self, *, remote: str = "origin", env: Mapping[str, str] | None = None) -> str:
        """Fetch from a git remote."""
        return self._run("git", "fetch", "--remote", remote, env=env)

    def git_push(
        self,
        *,
        remote: str = "origin",
        bookmark: str | None = None,
        allow_new: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> str:
        """Push to a git remote."""
        args = ["git", "push", "--remote", remote]
        if bookmark:
            args.extend(["-b", bookmark])
        if allow_new:
            args.append("--allow-new")
        return self._run(*args, env=env)

    def rebase(self, *, destination: str = "trunk()") -> str:
        """Rebase the current change onto a destination revision."""
        return self._run("rebase", "-d", destination)

    def bookmark_create(self, name: str, *, revision: str = "@") -> str:
        """Create a bookmark at the given revision."""
        return self._run("bookmark", "create", name, "-r", revision)

    def bookmark_list(self) -> str:
        """List all bookmarks."""
        return self._run("bookmark", "list")

    def git_remote_add(self, name: str, url: str) -> str:
        """Add a git remote."""
        return self._run("git", "remote", "add", name, url)

    def git_remote_set_url(self, name: str, url: str) -> str:
        """Update an existing git remote URL."""
        self._run("git", "remote", "remove", name)
        return self._run("git", "remote", "add", name, url)

    def git_remote_list(self) -> str:
        """List configured git remotes."""
        return self._run("git", "remote", "list")

    def log(self, *, revset: str = "@", template: str = "builtin_log_oneline", no_graph: bool = True) -> str:
        """Query the jj log."""
        args = ["log", "-r", revset, "-T", template]
        if no_graph:
            args.append("--no-graph")
        return self._run(*args)
