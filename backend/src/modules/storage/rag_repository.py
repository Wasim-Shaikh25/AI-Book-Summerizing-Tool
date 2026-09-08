"""SQLite persistence for RAG chunks and index metadata."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Sequence

from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class RagRepository:
    def __init__(self, store: KnowledgeStore) -> None:
        self.store = store
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            expected = {
                "chunk_id",
                "book_id",
                "section_id",
                "heading",
                "chapter_heading",
                "page_number",
                "part_no",
                "text",
                "char_count",
                "metadata_json",
            }
            existing = {row[1] for row in cur.execute("PRAGMA table_info(rag_chunks)").fetchall()}
            if existing and (not expected.issubset(existing) or "text_hash" in existing):
                logger.warning("Recreating rag_chunks table (schema mismatch)")
                cur.execute("DROP TABLE IF EXISTS rag_chunks")
                cur.execute("DROP TABLE IF EXISTS rag_index_meta")
                existing = set()

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL,
                    section_id TEXT,
                    heading TEXT,
                    chapter_heading TEXT,
                    page_number INTEGER,
                    part_no INTEGER,
                    text TEXT NOT NULL,
                    char_count INTEGER,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES books (book_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_index_meta (
                    book_id TEXT PRIMARY KEY,
                    embedding_model TEXT,
                    chunk_count INTEGER,
                    index_path TEXT,
                    built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES books (book_id)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_book_id ON rag_chunks (book_id)")
            conn.commit()
        finally:
            conn.close()

    def clear_book(self, book_id: str) -> None:
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM rag_chunks WHERE book_id = ?", (book_id,))
            cur.execute("DELETE FROM rag_index_meta WHERE book_id = ?", (book_id,))
            conn.commit()
        finally:
            conn.close()

    def save_chunks(self, book_id: str, chunks: Sequence[Dict[str, Any]]) -> None:
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM rag_chunks WHERE book_id = ?", (book_id,))
            rows = []
            for ch in chunks or []:
                cid = str(ch.get("chunk_id") or "")
                if not cid:
                    continue
                meta = {k: v for k, v in ch.items() if k not in {"text", "embed_text"}}
                rows.append(
                    (
                        cid,
                        book_id,
                        ch.get("section_id"),
                        ch.get("heading"),
                        ch.get("chapter_heading"),
                        ch.get("page_number"),
                        ch.get("part_no"),
                        str(ch.get("text") or ""),
                        int(ch.get("char_count") or 0),
                        json.dumps(meta, ensure_ascii=False),
                    )
                )
            cur.executemany(
                """
                INSERT OR REPLACE INTO rag_chunks
                  (chunk_id, book_id, section_id, heading, chapter_heading,
                   page_number, part_no, text, char_count, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            logger.debug("Saved %d rag_chunks for book_id=%s", len(rows), book_id)
        finally:
            conn.close()

    def save_index_meta(self, book_id: str, meta: Dict[str, Any]) -> None:
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO rag_index_meta
                  (book_id, embedding_model, chunk_count, index_path, built_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    book_id,
                    meta.get("embedding_model"),
                    int(meta.get("chunk_count") or 0),
                    meta.get("index_path"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_index_meta(self, book_id: str) -> Dict[str, Any] | None:
        conn = self.store.get_connection()
        try:
            row = conn.execute(
                "SELECT book_id, embedding_model, chunk_count, index_path, built_at FROM rag_index_meta WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "book_id": row[0],
                "embedding_model": row[1],
                "chunk_count": row[2],
                "index_path": row[3],
                "built_at": row[4],
            }
        finally:
            conn.close()

    def list_chunks(self, book_id: str, *, limit: int = 5000) -> List[Dict[str, Any]]:
        conn = self.store.get_connection()
        try:
            rows = conn.execute(
                """
                SELECT chunk_id, section_id, heading, chapter_heading, page_number, text, metadata_json
                FROM rag_chunks WHERE book_id = ? ORDER BY chunk_id LIMIT ?
                """,
                (book_id, limit),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                meta = json.loads(row[6] or "{}") if row[6] else {}
                out.append(
                    {
                        "chunk_id": row[0],
                        "section_id": row[1],
                        "heading": row[2],
                        "chapter_heading": row[3],
                        "page_number": row[4],
                        "text": row[5],
                        **meta,
                    }
                )
            return out
        finally:
            conn.close()
