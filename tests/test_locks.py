from __future__ import annotations

import asyncio

import pytest

from obsidian_ops.locks import FileLockManager


@pytest.mark.asyncio
async def test_same_path_lock_is_sequential() -> None:
    manager = FileLockManager()
    lock = manager.get_lock("/tmp/example.md")

    running = 0
    max_running = 0

    async def worker() -> None:
        nonlocal running, max_running
        async with lock:
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.02)
            running -= 1

    await asyncio.gather(worker(), worker())
    assert max_running == 1


@pytest.mark.asyncio
async def test_different_path_locks_can_overlap() -> None:
    manager = FileLockManager()
    lock_a = manager.get_lock("/tmp/a.md")
    lock_b = manager.get_lock("/tmp/b.md")

    running = 0
    max_running = 0

    async def worker(lock: asyncio.Lock) -> None:
        nonlocal running, max_running
        async with lock:
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.02)
            running -= 1

    await asyncio.gather(worker(lock_a), worker(lock_b))
    assert max_running >= 2


def test_same_path_returns_same_lock_instance() -> None:
    manager = FileLockManager()

    first = manager.get_lock("./note.md")
    second = manager.get_lock("./note.md")

    assert first is second
