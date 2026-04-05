from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class KilnRebuilder:
    def __init__(self, vault_dir: Path, site_dir: Path, kiln_bin: str = "kiln", timeout_s: int = 180) -> None:
        self._vault_dir = vault_dir
        self._site_dir = site_dir
        self._kiln_bin = kiln_bin
        self._timeout_s = timeout_s

    async def rebuild(self) -> str:
        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    self._kiln_bin,
                    "generate",
                    "--input",
                    str(self._vault_dir),
                    "--output",
                    str(self._site_dir),
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )

        result = await asyncio.to_thread(_run)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "kiln generate failed")
        return result.stdout.strip()
