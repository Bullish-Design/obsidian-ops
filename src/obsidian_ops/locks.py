from __future__ import annotations

import asyncio
from pathlib import Path


class FileLockManager:
    """
    Manage per-file asyncio locks keyed by resolved absolute file path.

    Callers performing multi-file operations should acquire locks in sorted
    path order to avoid deadlocks.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, path: str) -> asyncio.Lock:
        resolved = str(Path(path).resolve())
        if resolved not in self._locks:
            self._locks[resolved] = asyncio.Lock()
        return self._locks[resolved]
