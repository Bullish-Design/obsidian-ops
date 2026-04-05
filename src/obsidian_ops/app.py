from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from obsidian_ops.agent import Agent
from obsidian_ops.config import get_settings
from obsidian_ops.history_jj import JujutsuHistory
from obsidian_ops.inject import inject_overlay
from obsidian_ops.locks import FileLockManager
from obsidian_ops.models import JobRequest, JobResponse, JobStatus, SSEEvent
from obsidian_ops.page_context import resolve_page_path
from obsidian_ops.queue import JobQueue, run_worker
from obsidian_ops.rebuild import KilnRebuilder
from obsidian_ops.tools import ToolRuntime


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    jj = JujutsuHistory(settings.vault_dir, settings.jj_bin)
    await jj.ensure_workspace()

    rebuilder = KilnRebuilder(settings.vault_dir, settings.site_dir, settings.kiln_bin, settings.kiln_timeout_s)
    await rebuilder.rebuild()
    inject_overlay(settings.site_dir)

    lock_manager = FileLockManager()
    tool_runtime = ToolRuntime(settings, lock_manager, jj)
    agent = Agent(settings, tool_runtime)
    queue = JobQueue()

    worker_task = asyncio.create_task(run_worker(queue, agent, jj, rebuilder, inject_overlay, settings))

    app.state.settings = settings
    app.state.queue = queue
    app.state.jj = jj
    app.state.rebuilder = rebuilder
    app.state.worker_task = worker_task

    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs", response_model=JobResponse)
    async def create_job(request: JobRequest) -> JobResponse:
        queue: JobQueue = app.state.queue
        app_settings = app.state.settings
        file_path = request.current_file_path
        if file_path is None:
            file_path = resolve_page_path(
                app_settings.vault_dir,
                request.current_url_path,
                app_settings.page_url_prefix,
            )
        job = queue.create_job(request.instruction, file_path)
        return JobResponse(job_id=job.id)

    @app.get("/api/jobs/{job_id}/stream")
    async def stream_job(job_id: str) -> StreamingResponse:
        queue: JobQueue = app.state.queue
        job = queue.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        subscriber = queue.broadcaster.subscribe(job_id)

        async def event_generator():
            if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                message = ""
                payload = {}
                if job.result:
                    message = str(job.result.get("summary", ""))
                    payload = job.result
                elif job.error:
                    message = job.error
                final = SSEEvent(type="done", message=message, payload=payload)
                yield f"event: done\ndata: {final.model_dump_json()}\n\n"
                return

            while True:
                event = await subscriber.get()
                if event is None:
                    break
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.get("/api/jobs")
    async def list_jobs(limit: int = Query(default=20, ge=1, le=200)):
        queue: JobQueue = app.state.queue
        return queue.list_jobs(limit=limit)

    @app.post("/api/undo", response_model=JobResponse)
    async def undo() -> JobResponse:
        queue: JobQueue = app.state.queue
        job = queue.create_undo_job()
        return JobResponse(job_id=job.id)

    @app.get("/api/history")
    async def get_history(path: str, limit: int = Query(default=10, ge=1, le=200)):
        jj: JujutsuHistory = app.state.jj
        return await jj.log_for_file(path, limit)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/ops", StaticFiles(directory=str(static_dir)), name="ops")
    app.mount("/", StaticFiles(directory=str(settings.site_dir), html=True), name="site")
    return app


app = create_app()
