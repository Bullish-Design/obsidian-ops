from __future__ import annotations

import asyncio

import pytest

from obsidian_ops.models import JobStatus, SSEEvent
from obsidian_ops.queue import JobQueue


def test_create_job_defaults_to_queued() -> None:
    queue = JobQueue()

    job = queue.create_job("test instruction", "notes/a.md")

    assert job.status == JobStatus.QUEUED
    assert queue.get_job(job.id) is not None


def test_list_jobs_returns_newest_first() -> None:
    queue = JobQueue()

    first = queue.create_job("first", None)
    second = queue.create_job("second", None)

    jobs = queue.list_jobs()
    assert jobs[0].id == second.id
    assert jobs[1].id == first.id


def test_get_job_unknown_returns_none() -> None:
    queue = JobQueue()
    assert queue.get_job("unknown") is None


@pytest.mark.asyncio
async def test_broadcaster_publish_sends_to_all_subscribers() -> None:
    queue = JobQueue()
    job = queue.create_job("x", None)

    subscriber_a = queue.broadcaster.subscribe(job.id)
    subscriber_b = queue.broadcaster.subscribe(job.id)

    event = SSEEvent(type="status", message="hello")
    await queue.broadcaster.publish(job.id, event)

    assert await subscriber_a.get() == event
    assert await subscriber_b.get() == event


@pytest.mark.asyncio
async def test_broadcaster_close_sends_none_sentinel() -> None:
    queue = JobQueue()
    job = queue.create_job("x", None)

    subscriber = queue.broadcaster.subscribe(job.id)
    await queue.broadcaster.close(job.id)

    assert await subscriber.get() is None
