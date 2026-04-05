from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from obsidian_ops.agent import Agent
from obsidian_ops.config import Settings
from obsidian_ops.history_jj import JujutsuHistory
from obsidian_ops.models import Job, JobStatus, SSEEvent
from obsidian_ops.rebuild import KilnRebuilder


class SSEBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    async def publish(self, job_id: str, event: SSEEvent) -> None:
        for queue in self._subscribers.get(job_id, []):
            await queue.put(event)

    async def close(self, job_id: str) -> None:
        for queue in self._subscribers.get(job_id, []):
            await queue.put(None)
        self._subscribers.pop(job_id, None)


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._pending: asyncio.Queue[str] = asyncio.Queue()
        self.broadcaster = SSEBroadcaster()

    def create_job(self, instruction: str, file_path: str | None) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:8],
            instruction=instruction,
            file_path=file_path,
            created_at=datetime.now(UTC),
        )
        self._jobs[job.id] = job
        self._pending.put_nowait(job.id)
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)[:limit]

    async def next_job_id(self) -> str:
        return await self._pending.get()


async def run_worker(
    queue: JobQueue,
    agent: Agent,
    jj: JujutsuHistory,
    rebuilder: KilnRebuilder,
    injector: Callable,
    settings: Settings,
) -> None:
    while True:
        job_id = await queue.next_job_id()
        job = queue.get_job(job_id)
        if job is None:
            continue

        job.status = JobStatus.RUNNING
        await queue.broadcaster.publish(job_id, SSEEvent(type="status", message="Job started"))

        async def on_progress(event: SSEEvent) -> None:
            job.messages.append(event.message)
            await queue.broadcaster.publish(job_id, event)

        try:
            result = await agent.run(job.instruction, job.file_path, on_progress)

            if result.get("changed_files"):
                await queue.broadcaster.publish(job_id, SSEEvent(type="status", message="Recording changes..."))
                try:
                    await jj.commit(f"ops: {job.instruction[:80]}")
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "Files were changed but history recording failed. You may need to inspect the vault manually."
                    ) from exc

                await queue.broadcaster.publish(job_id, SSEEvent(type="status", message="Rebuilding site..."))
                try:
                    await rebuilder.rebuild()
                    injector(settings.site_dir)
                except Exception:  # noqa: BLE001
                    warning = "Changes saved but site rebuild failed. Refresh may show stale content."
                    summary = str(result.get("summary", "")).strip()
                    result["summary"] = f"{summary}\n\n{warning}".strip()
                    result["warning"] = warning

            job.status = JobStatus.SUCCEEDED
            job.result = result
            job.finished_at = datetime.now(UTC)
            await queue.broadcaster.publish(
                job_id,
                SSEEvent(
                    type="done",
                    message=str(result.get("summary", "")),
                    payload=result,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = datetime.now(UTC)
            await queue.broadcaster.publish(job_id, SSEEvent(type="error", message=job.error))
            await queue.broadcaster.publish(job_id, SSEEvent(type="done", message=job.error))
        finally:
            await queue.broadcaster.close(job_id)
