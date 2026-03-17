from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def main() -> None:
    ap = argparse.ArgumentParser(description="Dump topics from knowledge_base.db as a headings-like list.")
    ap.add_argument("--db", type=str, default="output/knowledge_base.db")
    ap.add_argument("--book-id", type=str, default=None, help="Optional: restrict to a single book_id.")
    ap.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional: write output JSON to this path (if omitted, prints to terminal).",
    )
    ap.add_argument("--limit", type=int, default=0, help="Optional: limit number of rows (0 = no limit).")
    ap.add_argument(
        "--unique",
        action="store_true",
        help="If set, outputs unique headings (grouped by normalized text) with count + page range.",
    )
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = sqlite3.connect(db_path.as_posix())
    try:
        cur = con.cursor()
        q = "SELECT topic_id, book_id, topic, subtopic, source_page, importance_score, topic_type, metadata FROM topics"
        params: tuple[Any, ...] = ()
        if args.book_id:
            q += " WHERE book_id = ?"
            params = (args.book_id,)
        q += " ORDER BY book_id, source_page, topic"

        if args.limit and args.limit > 0:
            q += f" LIMIT {int(args.limit)}"

        rows = cur.execute(q, params).fetchall()

        def norm(s: str) -> str:
            return " ".join((s or "").split()).strip()

        if args.unique:
            # Group rows by normalized heading text.
            grouped: dict[str, dict[str, Any]] = {}
            for topic_id, book_id, topic, subtopic, source_page, importance_score, topic_type, metadata in rows:
                text = norm(str(subtopic or topic or ""))
                if not text:
                    continue
                g = grouped.get(text)
                if g is None:
                    grouped[text] = {
                        "text": text,
                        "count": 1,
                        "book_ids": {str(book_id)},
                        "min_page": int(source_page) if source_page is not None else None,
                        "max_page": int(source_page) if source_page is not None else None,
                        "sample_topic_ids": [str(topic_id)],
                        "sample_topic": norm(str(topic or "")),
                        "sample_subtopic": norm(str(subtopic or "")) if subtopic else None,
                    }
                else:
                    g["count"] += 1
                    g["book_ids"].add(str(book_id))
                    if source_page is not None:
                        p = int(source_page)
                        g["min_page"] = p if g["min_page"] is None else min(g["min_page"], p)
                        g["max_page"] = p if g["max_page"] is None else max(g["max_page"], p)
                    if len(g["sample_topic_ids"]) < 5:
                        g["sample_topic_ids"].append(str(topic_id))

            out_unique: list[dict[str, Any]] = []
            for text, g in grouped.items():
                out_unique.append(
                    {
                        "text": text,
                        "count": g["count"],
                        "book_ids": sorted(list(g["book_ids"])),
                        "page_range": [g["min_page"], g["max_page"]],
                        "sample_topic_ids": g["sample_topic_ids"],
                        "sample_topic": g["sample_topic"],
                        "sample_subtopic": g["sample_subtopic"],
                    }
                )
            out_unique.sort(key=lambda x: (-int(x["count"]), x["text"]))

            if args.out:
                out_path = Path(args.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(out_unique, ensure_ascii=False, indent=2), encoding="utf-8")
                print("Wrote:", out_path, "unique_rows=", len(out_unique))
            else:
                print(json.dumps(out_unique, ensure_ascii=False, indent=2))
            return

        out: list[dict[str, Any]] = []
        for topic_id, book_id, topic, subtopic, source_page, importance_score, topic_type, metadata in rows:
            md: dict[str, Any] = {}
            try:
                md = json.loads(metadata) if metadata else {}
            except Exception:
                md = {}

            out.append(
                {
                    "heading_id": str(topic_id),
                    "book_id": str(book_id),
                    "text": norm(str(subtopic or topic or "")),
                    "topic": norm(str(topic or "")),
                    "subtopic": norm(str(subtopic or "")) if subtopic else None,
                    "page_number": int(source_page) if source_page is not None else None,
                    "importance_score": importance_score,
                    "topic_type": topic_type,
                    "metadata": md,
                }
            )

        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Wrote:", out_path, "rows=", len(out))
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
