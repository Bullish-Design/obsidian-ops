from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class JujutsuHistory:
    def __init__(self, vault_dir: Path, jj_bin: str = "jj") -> None:
        self._vault_dir = vault_dir
        self._jj_bin = jj_bin

    async def _run_jj(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [self._jj_bin, *args],
                cwd=str(self._vault_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        return await asyncio.to_thread(_run)

    async def ensure_workspace(self) -> None:
        result = await self._run_jj("status", timeout=30)
        if result.returncode != 0:
            raise RuntimeError("Vault is not a Jujutsu workspace")

    async def commit(self, message: str) -> str:
        result = await self._run_jj("commit", "-m", message, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "jj commit failed")
        return result.stdout.strip()

    async def undo(self) -> str:
        result = await self._run_jj("undo", timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "jj undo failed")
        return result.stdout.strip()

    async def log_for_file(self, path: str, limit: int = 10) -> list[str]:
        result = await self._run_jj(
            "log",
            "--no-graph",
            "-r",
            "all()",
            "--limit",
            str(limit),
            path,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "jj log failed")
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    async def diff_for_file(self, path: str) -> str:
        result = await self._run_jj("diff", path, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "jj diff failed")
        return result.stdout
