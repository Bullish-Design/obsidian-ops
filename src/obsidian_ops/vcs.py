"""Jujutsu VCS wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

from obsidian_ops.errors import VCSError


class JJ:
    """Thin wrapper around `jj` subprocess calls."""

    def __init__(self, cwd: Path, *, jj_bin: str = "jj", timeout: int = 120) -> None:
        self.cwd = cwd
        self.jj_bin = jj_bin
        self.timeout = timeout

    def _run(self, *args: str) -> str:
        cmd = [self.jj_bin, *args]
        try:
            result = subprocess.run(
                cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise VCSError(f"jj binary not found: {self.jj_bin}") from exc
        except subprocess.TimeoutExpired as exc:
            raise VCSError(f"jj command timed out after {self.timeout}s: {' '.join(cmd)}") from exc

        if result.returncode != 0:
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            raise VCSError(
                "jj command failed: "
                f"{' '.join(cmd)}\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )

        return result.stdout

    def describe(self, message: str) -> None:
        self._run("describe", "-m", message)

    def new(self) -> None:
        self._run("new")

    def undo(self) -> None:
        self._run("undo")

    def status(self) -> str:
        return self._run("status")
