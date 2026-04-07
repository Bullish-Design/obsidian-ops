"""Mutation lock implementation for write serialization."""

from __future__ import annotations

import threading
from typing import Self

from obsidian_ops.errors import BusyError


class MutationLock:
    """Non-blocking lock that raises BusyError when already held."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Acquire the lock without waiting."""
        if not self._lock.acquire(blocking=False):
            raise BusyError("vault is busy with another mutation")

    def release(self) -> None:
        """Release the lock."""
        self._lock.release()

    @property
    def is_held(self) -> bool:
        """Return True when the lock is currently held."""
        return self._lock.locked()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
