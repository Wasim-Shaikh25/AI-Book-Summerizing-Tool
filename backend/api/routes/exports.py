"""Secure docx download."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth.dependencies import get_current_user
from storage.user_repository import ExportRepository, UserRecord

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{export_id}")
def download_export(export_id: str, current: UserRecord = Depends(get_current_user)):
    record = ExportRepository().get(export_id, current.user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")
    if not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="File missing on server")

    return FileResponse(
        record.file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=record.file_name,
    )
