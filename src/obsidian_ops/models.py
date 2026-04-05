from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    instruction: str
    file_path: str | None = None
    status: JobStatus = JobStatus.QUEUED
    messages: list[str] = Field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class JobRequest(BaseModel):
    instruction: str
    current_url_path: str
    current_file_path: str | None = None


class JobResponse(BaseModel):
    job_id: str


class SSEEvent(BaseModel):
    type: str
    message: str
    payload: dict = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    summary: str
    timestamp: str | None = None
