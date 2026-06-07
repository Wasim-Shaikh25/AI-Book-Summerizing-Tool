"""In-memory upload job tracking for async PDF ingestion."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class UploadJob:
    job_id: str
    user_id: str
    filename: str
    status: str = "queued"
    message: str = "Waiting to start..."
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_lock = threading.Lock()
_jobs: dict[str, UploadJob] = {}


def create_job(user_id: str, filename: str) -> UploadJob:
    job = UploadJob(job_id=str(uuid.uuid4()), user_id=user_id, filename=filename)
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str, user_id: str) -> UploadJob | None:
    with _lock:
        job = _jobs.get(job_id)
    if not job or job.user_id != user_id:
        return None
    return job


def update_job(job_id: str, *, status: str | None = None, message: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if message is not None:
            job.message = message
        job.updated_at = datetime.now(timezone.utc).isoformat()


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "done"
        job.message = "Ingestion complete"
        job.result = result
        job.updated_at = datetime.now(timezone.utc).isoformat()


def fail_job(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "error"
        job.message = "Ingestion failed"
        job.error = error
        job.updated_at = datetime.now(timezone.utc).isoformat()
