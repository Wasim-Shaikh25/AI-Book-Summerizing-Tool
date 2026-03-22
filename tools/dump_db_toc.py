from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script: `python tools/dump_db_toc.py ...`
# by ensuring project root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.storage.book_repository import BookRepository
from src.storage.knowledge_store import KnowledgeStore
from src.storage.toc_repository import TocRepository


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump finalized TOC (headings + fragments) from SQLite DB to JSON.")
    ap.add_argument("--db", type=str, default="output/knowledge_base.db", help="Path to SQLite DB.")
    ap.add_argument("--book-id", type=str, required=False, help="Book ID to dump. If omitted, dumps the latest book.")
    ap.add_argument("--out", type=str, required=False, help="Output JSON path (default: output/toc_<book_id>.json).")
    args = ap.parse_args()

    store = KnowledgeStore(db_path=args.db)
    book_repo = BookRepository(store)
    toc_repo = TocRepository(store)

    book_id = args.book_id
    if not book_id:
        books = book_repo.list_all_books()
        if not books:
            raise SystemExit("No books found in DB.")
        # pick most recent by processed_at (not available in BookMetadata mapping),
        # so fall back to last row returned by list_all_books().
        book_id = books[-1].book_id

    snapshot = toc_repo.get_book_toc(book_id)

    out_path = Path(args.out) if args.out else Path("output") / f"toc_{book_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print("db:", args.db)
    print("book_id:", book_id)
    print("out:", out_path.as_posix())
    print("headings:", len(snapshot.get("headings", [])))
    print("fragments:", len(snapshot.get("fragments", {})))


if __name__ == "__main__":
    main()
