"""
Web platform package shim — services, auth, and storage.

Incremental rename target for ``backend/services/``, ``auth/``, ``storage/``.
Do not name this package ``platform`` — it shadows Python's stdlib ``platform`` module.
"""

from services.ingestion_service import IngestionService
from services.chat_service import ChatService
from services import upload_jobs

__all__ = ["IngestionService", "ChatService", "upload_jobs"]
