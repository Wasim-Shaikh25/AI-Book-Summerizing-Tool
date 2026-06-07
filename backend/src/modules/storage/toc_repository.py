import json
import logging
import sqlite3
from typing import Any, Dict, Optional, Sequence

from src.modules.storage.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


class TocRepository:
    """
    Persists the finalized TOC state (final headings + fragments + relationship)
    into SQLite. This is the production source-of-truth for reconstruction/export.

    Design notes:
    - We persist per-book and support reruns by clearing existing rows for book_id.
    - Relationship table allows future 1-heading->many-fragments without schema change.
    """

    def __init__(self, store: KnowledgeStore):
        self.store = store

    def clear_book_toc(self, book_id: str) -> None:
        """Deletes all persisted TOC rows for a given book_id."""
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM heading_fragments WHERE book_id = ?", (book_id,))
            cur.execute("DELETE FROM final_headings WHERE book_id = ?", (book_id,))
            cur.execute("DELETE FROM fragments WHERE book_id = ?", (book_id,))
            conn.commit()
        finally:
            conn.close()

    def save_fragments(self, book_id: str, fragments: Sequence[Any]) -> None:
        """
        Bulk upsert fragments.

        Expected fragment shape:
          - has .id or .fragment_id
          - has .text (or .fragment_text)
        """
        rows: list[tuple[str, str, str]] = []
        for f in fragments or []:
            fid = getattr(f, "id", None) or getattr(f, "fragment_id", None)
            text = getattr(f, "text", None) or getattr(f, "fragment_text", None) or ""
            if not isinstance(fid, str) or not fid:
                continue
            rows.append((fid, book_id, str(text)))

        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT OR REPLACE INTO fragments (fragment_id, book_id, text)
                VALUES (?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            logger.debug("Saved %d fragments for book_id=%s", len(rows), book_id)
        finally:
            conn.close()

    def save_final_headings(self, book_id: str, final_headings: Sequence[Any]) -> None:
        """
        Bulk upsert final headings.

        Expected heading shape:
          - has .id or .heading_id
          - has .text
          - has .level
          - has .parent_heading (string id or None)
          - optional: .confidence
          - optional hierarchy metadata:
              - .reason
              - .signals_used (list[str])
              - .hierarchy_model
              - .hierarchy_latency_ms
        """
        rows: list[tuple] = []
        for h in final_headings or []:
            hid = getattr(h, "id", None) or getattr(h, "heading_id", None)
            if not isinstance(hid, str) or not hid:
                continue

            text = str(getattr(h, "text", "") or "")
            level = getattr(h, "level", None)
            parent_id = getattr(h, "parent_heading", None) or getattr(h, "parent_heading_id", None)

            line_id = getattr(h, "line_id", None)
            page_number = getattr(h, "page_number", None)
            confidence = getattr(h, "confidence", None)

            reason = getattr(h, "reason", None)
            signals_used = getattr(h, "signals_used", None)
            hierarchy_model = getattr(h, "hierarchy_model", None)
            hierarchy_latency_ms = getattr(h, "hierarchy_latency_ms", None)

            rows.append(
                (
                    hid,
                    book_id,
                    text,
                    level,
                    parent_id,
                    line_id,
                    page_number,
                    confidence,
                    reason,
                    None if signals_used is None else json.dumps(signals_used, ensure_ascii=False),
                    hierarchy_model,
                    hierarchy_latency_ms,
                )
            )

        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT OR REPLACE INTO final_headings
                  (heading_id, book_id, text, level, parent_heading_id, line_id, page_number, confidence,
                   reason, signals_used, hierarchy_model, hierarchy_latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            logger.debug("Saved %d final headings for book_id=%s", len(rows), book_id)
        finally:
            conn.close()

    def save_heading_fragment_links(
        self,
        book_id: str,
        heading_to_fragment_id: Dict[str, Optional[str]] | None,
    ) -> None:
        """Bulk insert heading->fragment edges (skips nulls)."""
        rows: list[tuple[str, str, str]] = []
        for hid, fid in (heading_to_fragment_id or {}).items():
            if not isinstance(hid, str) or not hid:
                continue
            if not isinstance(fid, str) or not fid:
                continue
            rows.append((hid, fid, book_id))

        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT OR REPLACE INTO heading_fragments (heading_id, fragment_id, book_id)
                VALUES (?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            logger.debug("Saved %d heading-fragment links for book_id=%s", len(rows), book_id)
        finally:
            conn.close()

    def get_book_toc(self, book_id: str) -> dict[str, Any]:
        """
        Returns a DB snapshot for a given book_id:
          {
            "book_id": "...",
            "headings": [ {heading fields...}, ...],
            "fragments": {fragment_id: {"text": ...}, ...},
            "heading_fragments": {heading_id: [fragment_id, ...], ...}
          }
        """
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()

            headings_rows = cur.execute(
                """
                SELECT heading_id, text, level, parent_heading_id, line_id, page_number, confidence,
                       reason, signals_used, hierarchy_model, hierarchy_latency_ms
                FROM final_headings
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchall()

            fragments_rows = cur.execute(
                """
                SELECT fragment_id, text
                FROM fragments
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchall()

            links_rows = cur.execute(
                """
                SELECT heading_id, fragment_id
                FROM heading_fragments
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchall()

            fragments: dict[str, dict[str, Any]] = {fid: {"text": text} for (fid, text) in fragments_rows}

            heading_fragments: dict[str, list[str]] = {}
            for hid, fid in links_rows:
                heading_fragments.setdefault(hid, []).append(fid)

            headings: list[dict[str, Any]] = []
            for (
                heading_id,
                text,
                level,
                parent_heading_id,
                line_id,
                page_number,
                confidence,
                reason,
                signals_used,
                hierarchy_model,
                hierarchy_latency_ms,
            ) in headings_rows:
                headings.append(
                    {
                        "heading_id": heading_id,
                        "text": text,
                        "level": level,
                        "parent_heading_id": parent_heading_id,
                        "line_id": line_id,
                        "page_number": page_number,
                        "confidence": confidence,
                        "reason": reason,
                        "signals_used": None if signals_used is None else json.loads(signals_used),
                        "hierarchy_model": hierarchy_model,
                        "hierarchy_latency_ms": hierarchy_latency_ms,
                        "fragment_ids": heading_fragments.get(heading_id, []),
                    }
                )

            return {
                "book_id": book_id,
                "headings": headings,
                "fragments": fragments,
                "heading_fragments": heading_fragments,
            }
        finally:
            conn.close()

    def save_full_toc(
        self,
        *,
        book_id: str,
        final_headings: Sequence[Any],
        fragments: Sequence[Any],
        heading_to_fragment_id: Dict[str, Optional[str]] | None,
        clear_existing: bool = True,
    ) -> None:
        """
        Writes a consistent TOC snapshot in a transaction.

        Order:
          1) (optional) clear existing per-book rows
          2) upsert fragments
          3) upsert headings
          4) upsert links
        """
        conn = self.store.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")

            if clear_existing:
                cur.execute("DELETE FROM heading_fragments WHERE book_id = ?", (book_id,))
                cur.execute("DELETE FROM final_headings WHERE book_id = ?", (book_id,))
                cur.execute("DELETE FROM fragments WHERE book_id = ?", (book_id,))

            # fragments
            frag_rows: list[tuple[str, str, str]] = []
            for f in fragments or []:
                fid = getattr(f, "id", None) or getattr(f, "fragment_id", None)
                text = getattr(f, "text", None) or getattr(f, "fragment_text", None) or ""
                if not isinstance(fid, str) or not fid:
                    continue
                frag_rows.append((fid, book_id, str(text)))
            if frag_rows:
                cur.executemany(
                    "INSERT OR REPLACE INTO fragments (fragment_id, book_id, text) VALUES (?, ?, ?)",
                    frag_rows,
                )

            # headings
            head_rows: list[tuple] = []
            for h in final_headings or []:
                hid = getattr(h, "id", None) or getattr(h, "heading_id", None)
                if not isinstance(hid, str) or not hid:
                    continue
                text = str(getattr(h, "text", "") or "")
                level = getattr(h, "level", None)
                parent_id = getattr(h, "parent_heading", None) or getattr(h, "parent_heading_id", None)
                line_id = getattr(h, "line_id", None)
                page_number = getattr(h, "page_number", None)
                confidence = getattr(h, "confidence", None)

                reason = getattr(h, "reason", None)
                signals_used = getattr(h, "signals_used", None)
                hierarchy_model = getattr(h, "hierarchy_model", None)
                hierarchy_latency_ms = getattr(h, "hierarchy_latency_ms", None)

                head_rows.append(
                    (
                        hid,
                        book_id,
                        text,
                        level,
                        parent_id,
                        line_id,
                        page_number,
                        confidence,
                        reason,
                        None if signals_used is None else json.dumps(signals_used, ensure_ascii=False),
                        hierarchy_model,
                        hierarchy_latency_ms,
                    )
                )
            if head_rows:
                cur.executemany(
                    """
                    INSERT OR REPLACE INTO final_headings
                      (heading_id, book_id, text, level, parent_heading_id, line_id, page_number, confidence,
                       reason, signals_used, hierarchy_model, hierarchy_latency_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    head_rows,
                )

            # links
            link_rows: list[tuple[str, str, str]] = []
            for hid, fid in (heading_to_fragment_id or {}).items():
                if not isinstance(hid, str) or not hid:
                    continue
                if not isinstance(fid, str) or not fid:
                    continue
                link_rows.append((hid, fid, book_id))
            if link_rows:
                cur.executemany(
                    "INSERT OR REPLACE INTO heading_fragments (heading_id, fragment_id, book_id) VALUES (?, ?, ?)",
                    link_rows,
                )

            conn.commit()
            logger.info(
                "Persisted TOC snapshot for book_id=%s (headings=%d, fragments=%d, links=%d)",
                book_id,
                len(head_rows),
                len(frag_rows),
                len(link_rows),
            )
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("Failed to persist TOC snapshot for book_id=%s: %s", book_id, e)
            raise
        finally:
            conn.close()
