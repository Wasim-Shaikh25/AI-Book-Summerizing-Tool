from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _read_trace(trace_json: Path) -> list[dict[str, Any]]:
    raw = json.loads(trace_json.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        raw = raw["items"]
    if not isinstance(raw, list):
        raise ValueError(f"Unexpected trace JSON shape in {trace_json}")

    out: list[dict[str, Any]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "heading_id": it.get("heading_id"),
                "text": (it.get("text") or "").strip(),
                "level": it.get("level"),
                "parent_heading": it.get("parent_heading"),
                "fragment_id": it.get("fragment_id"),
                "page_number": it.get("page_number"),
                "line_id": it.get("line_id"),
            }
        )
    return out


def _db_tables(con: sqlite3.Connection) -> list[str]:
    cur = con.cursor()
    rows = cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def _print_db_overview(db_path: Path) -> None:
    con = sqlite3.connect(db_path.as_posix())
    try:
        tables = _db_tables(con)
        print("db_path:", db_path)
        print("tables:", tables)

        cur = con.cursor()
        for t in tables:
            cols = [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]
            print(f"table.{t}.columns:", cols)
            rows = cur.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
            print(f"table.{t}.sample_rows:", rows)
    finally:
        con.close()


def _extract_headings_like_rows(db_path: Path) -> list[dict[str, Any]]:
    """
    Extract finalized headings from DB (source of truth):

      final_headings + heading_fragments

    Note: DB stores the edge heading->fragment, but the trace stage logs store
    a single fragment_id field. For diffing, we take the first fragment_id
    (sorted) if multiple exist.
    """
    con = sqlite3.connect(db_path.as_posix())
    try:
        tables = _db_tables(con)
        if "final_headings" not in tables:
            return []

        cur = con.cursor()

        # Load links (book-agnostic; for compare we flatten across all books)
        links = cur.execute("SELECT heading_id, fragment_id FROM heading_fragments").fetchall()
        heading_to_fragments: dict[str, list[str]] = {}
        for hid, fid in links:
            if isinstance(hid, str) and isinstance(fid, str):
                heading_to_fragments.setdefault(hid, []).append(fid)

        rows = cur.execute(
            """
            SELECT heading_id, text, level, parent_heading_id, page_number, line_id
            FROM final_headings
            """
        ).fetchall()

        out: list[dict[str, Any]] = []
        for heading_id, text, level, parent_heading_id, page_number, line_id in rows:
            frag_ids = sorted(heading_to_fragments.get(heading_id, []))
            out.append(
                {
                    "heading_id": heading_id,
                    "text": (text or "").strip(),
                    "level": level,
                    "parent_heading": parent_heading_id,
                    "fragment_id": frag_ids[0] if frag_ids else None,
                    "page_number": page_number,
                    "line_id": line_id,
                }
            )
        return out
    finally:
        con.close()


def _key(h: dict[str, Any]) -> tuple:
    return (h.get("heading_id") or "", h.get("text") or "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare trace final headings JSON vs headings-like data in SQLite DB.")
    ap.add_argument(
        "--trace",
        type=str,
        required=True,
        help="Path to logs/*/09_final_headings.json (or stage json containing final_headings).",
    )
    ap.add_argument(
        "--db",
        type=str,
        default="output/knowledge_base.db",
        help="Path to SQLite DB (default: output/knowledge_base.db).",
    )
    ap.add_argument("--overview", action="store_true", help="Print DB schema/tables overview before diffing.")
    args = ap.parse_args()

    trace_json = Path(args.trace)
    db_path = Path(args.db)

    if not trace_json.exists():
        raise SystemExit(f"Trace JSON not found: {trace_json}")
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    if args.overview:
        _print_db_overview(db_path)

    trace = sorted(_read_trace(trace_json), key=_key)
    db_heads = sorted(_extract_headings_like_rows(db_path), key=_key)

    print("trace.count:", len(trace))
    print("db_like.count:", len(db_heads))

    trace_keys = {_key(h) for h in trace}
    db_keys = {_key(h) for h in db_heads}

    only_trace = sorted(trace_keys - db_keys)
    only_db = sorted(db_keys - trace_keys)

    print("only_in_trace:", len(only_trace))
    print("only_in_db_like:", len(only_db))

    # Print small samples to keep output readable
    if only_trace:
        print("\\nSample only_in_trace:")
        for k in only_trace[:25]:
            print(" -", k)
    if only_db:
        print("\\nSample only_in_db_like:")
        for k in only_db[:25]:
            print(" -", k)

    # Note: this comparison is best-effort because current DB schema stores topics, not headings.
    # If you add a dedicated headings table, update _extract_headings_like_rows accordingly.


if __name__ == "__main__":
    main()
