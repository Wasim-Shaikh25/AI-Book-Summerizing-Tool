"""Cross-book search endpoint.

Activated by RAG_CORPUS_INDEX_ENABLED=1. Returns [] when disabled.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from auth.dependencies import get_current_user
from storage.user_repository import UserRecord

router = APIRouter(tags=["search"])


def _get_rag_service():
    from src.modules.rag.service import RagService

    return RagService()


@router.get("/search")
async def search_books(
    q: str = Query(..., min_length=1, description="Search query"),
    books: str = Query("all", description="Comma-separated book IDs or 'all'"),
    top_k: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    current_user: UserRecord = Depends(get_current_user),
    rag: object = Depends(_get_rag_service),
) -> dict:
    """Search across multiple books using the corpus-level FAISS index.

    Requires RAG_CORPUS_INDEX_ENABLED=1. When disabled, returns an empty list.
    """
    user_id = current_user.user_id
    book_ids = None if books == "all" else [b.strip() for b in books.split(",") if b.strip()]
    results = rag.retrieve_cross_book(q, user_id, book_ids=book_ids, top_k=top_k)  # type: ignore[attr-defined]
    return {"query": q, "results": results, "count": len(results)}
