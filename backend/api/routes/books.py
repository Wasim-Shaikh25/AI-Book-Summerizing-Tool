"""Book upload and listing."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from api.schemas import BookSummary, UploadJobResponse, UploadStatusResponse
from auth.config import get_auth_settings
from auth.dependencies import get_current_user
from services.ingestion_service import IngestionService
from services import upload_jobs
from storage.user_repository import UserBookRepository, UserRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


def _run_ingestion_job(job_id: str, user_id: str, tmp_path: str, filename: str) -> None:
    def on_progress(status: str, message: str) -> None:
        upload_jobs.update_job(job_id, status=status, message=message)

    try:
        upload_jobs.update_job(job_id, status="processing", message="Starting ingestion...")
        result = IngestionService().ingest_upload(
            user_id,
            tmp_path,
            filename,
            on_progress=on_progress,
        )
        upload_jobs.complete_job(job_id, result)
    except Exception as exc:
        logger.exception("Upload job %s failed", job_id)
        upload_jobs.fail_job(job_id, str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/upload", response_model=UploadJobResponse)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current: UserRecord = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    max_bytes = get_auth_settings().max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {get_auth_settings().max_upload_mb} MB limit",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    job = upload_jobs.create_job(current.user_id, file.filename)
    background_tasks.add_task(_run_ingestion_job, job.job_id, current.user_id, tmp_path, file.filename)

    return UploadJobResponse(
        job_id=job.job_id,
        status="queued",
        message=f"Uploaded {file.filename}. Processing in background...",
    )


@router.get("/upload/{job_id}", response_model=UploadStatusResponse)
def upload_status(job_id: str, current: UserRecord = Depends(get_current_user)):
    job = upload_jobs.get_job(job_id, current.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")

    book = None
    if job.status == "done" and job.result:
        book = BookSummary(
            book_id=job.result["book_id"],
            title=job.result["title"],
            total_pages=job.result.get("total_pages"),
            processed_at=None,
        )

    return UploadStatusResponse(
        job_id=job.job_id,
        status=job.status,
        message=job.message,
        book=book,
        error=job.error,
    )


@router.get("", response_model=list[BookSummary])
def list_books(current: UserRecord = Depends(get_current_user)):
    rows = UserBookRepository().list_for_user(current.user_id)
    return [
        BookSummary(
            book_id=r["book_id"],
            title=r["title"],
            total_pages=r.get("total_pages"),
            processed_at=r.get("processed_at"),
        )
        for r in rows
    ]
