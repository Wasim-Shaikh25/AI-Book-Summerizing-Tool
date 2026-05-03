# 07 — Storage and repositories

## KnowledgeStore

**File:** `src/storage/knowledge_store.py`

- `__init__(db_path="output/knowledge_base.db")`
- `_initialize_db()` — creates `books`, `topics`, `final_headings`, `fragments`, `heading_fragments`, pipeline artifact tables (see file for full schema + migrations).
- `get_connection()`, JSON helpers, `save_pipeline_artifact(...)` for run JSON mirroring.

## BookRepository

**File:** `src/storage/book_repository.py`

- `save_book(BookMetadata)` — upsert book row, returns metadata with `book_id`.

## TocRepository

**File:** `src/storage/toc_repository.py`

Main production entry used by CLI ingestion and pipeline:

```
save_full_toc(book_id, final_headings, fragments, heading_to_fragment_id, clear_existing=True)
  → clear_book_toc if clear_existing
  → save_fragments
  → save_final_headings
  → persists heading–fragment links (heading_fragments)
```

Also exposes `clear_book_toc`, granular saves for tests/tools.

## TopicRepository

**File:** `src/storage/topic_repository.py`

Legacy topic rows; **CommandLoop** deletes `topics` for a book after ingestion to avoid stale data.

## Schema models

**File:** `src/storage/schema.py` — `BookMetadata`, `TopicKnowledge` (Pydantic).
