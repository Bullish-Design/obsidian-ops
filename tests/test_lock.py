from __future__ import annotations

import threading
import time

import pytest

from obsidian_ops.errors import BusyError
from obsidian_ops.lock import MutationLock


def test_acquire_release() -> None:
    lock = MutationLock()

    lock.acquire()
    assert lock.is_held is True

    lock.release()
    assert lock.is_held is False


def test_context_manager() -> None:
    lock = MutationLock()

    with lock:
        assert lock.is_held is True

    assert lock.is_held is False


def test_double_acquire_raises_busy() -> None:
    lock = MutationLock()

    lock.acquire()
    with pytest.raises(BusyError):
        lock.acquire()

    lock.release()


def test_release_on_exception() -> None:
    lock = MutationLock()

    with pytest.raises(RuntimeError):
        with lock:
            raise RuntimeError("boom")

    assert lock.is_held is False


def test_is_held_reflects_state() -> None:
    lock = MutationLock()
    assert lock.is_held is False

    with lock:
        assert lock.is_held is True

    assert lock.is_held is False


def test_concurrent_threads() -> None:
    lock = MutationLock()
    entered = threading.Event()
    release_now = threading.Event()

    def hold_lock() -> None:
        with lock:
            entered.set()
            release_now.wait(timeout=1)

    thread = threading.Thread(target=hold_lock)
    thread.start()

    entered.wait(timeout=1)
    time.sleep(0.01)

    with pytest.raises(BusyError):
        lock.acquire()

    release_now.set()
    thread.join(timeout=1)

    lock.acquire()
    lock.release()
