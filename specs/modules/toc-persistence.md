# Module: TOC & Persistence

> **Code:** `backend/src/modules/structure/toc_*`, `backend/src/modules/storage/`  
> **Web entry:** `backend/services/ingestion_service.py` (saves TOC after upload)

---

## 1. Purpose

Detect repeated TOC patterns, tag book metadata, clean final heading sets, and persist to SQLite.

---

## 2. TOC Functions

| Function | Module |
|----------|--------|
| `detect_deterministic_toc` | `structure/toc_repeat_detection.py` |
| `build_toc_sections_from_repeated_headings` | `structure/toc_repeat_detection.py` |
| `book_metadata_from_first_toc_section` | `structure/toc_repeat_detection.py` |
| `clean_toc` | `structure/toc_cleaning.py` |

**Removed (2026-06-01):** `toc_splitter.py` — never called from pipeline. See [unused-tracking.md](../unused-tracking.md).

---

## 3. Persistence

### Pipeline path (`persist_to_db=True`)

```python
# backend/src/modules/pipeline/runner.py::_persist
KnowledgeStore → BookRepository.save_book → TocRepository.save_full_toc
```

### Web upload path

```python
# backend/services/ingestion_service.py
run_pipeline(enable_logs=True, persist_to_db=False)
TocRepository.save_full_toc(book_id, final_headings, fragments, ...)
UserBookRepository.link(user_id, book_id, file_path, log_dir)
```

| Repository | Module | Role |
|------------|--------|------|
| `KnowledgeStore` | `storage/knowledge_store.py` | Connection + DDL |
| `BookRepository` | `storage/book_repository.py` | Book CRUD |
| `TocRepository` | `storage/toc_repository.py` | Headings, fragments, links |
| `RagRepository` | `storage/rag_repository.py` | RAG chunks (optional, post-ingestion) |

**Removed (2026-06-01):** `TopicRepository` — only used by deleted question paper handler.

---

## 4. Outputs

- `final_headings` with `is_toc` / `in_toc_section` stripped for consumer-facing lists
- SQLite rows in `books`, `final_headings`, `fragments`, `heading_fragments`
- Pipeline logs in `logs/run_{timestamp}/` (linked via `user_books.log_dir` for web)

---

## 5. Tests

| Test | Coverage |
|------|----------|
| `test_fragment_coverage.py` | DB counts match pipeline, no missing mappings |
| `test_logging_contract.py` | TOC stage JSON files written |

See [testing.md](../testing.md) §6.
