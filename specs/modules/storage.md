# Module: Storage

> **Code:** `backend/src/modules/storage/` (knowledge), `backend/storage/` (platform)  
> **Database:** `output/knowledge_base.db` (single SQLite file)

---

## 1. Purpose

SQLite knowledge base for processed books, TOC/fragment graphs, RAG chunks, and platform data (users, chats, exports).

---

## 2. Knowledge Store

**Code:** `backend/src/modules/storage/`

| Class | Module | Role |
|-------|--------|------|
| `KnowledgeStore` | `knowledge_store.py` | Connection + DDL + artifact save |
| `BookRepository` | `book_repository.py` | Book CRUD |
| `TocRepository` | `toc_repository.py` | TOC graph persistence |
| `RagRepository` | `rag_repository.py` | RAG chunks + index metadata |

**Schemas:** [data-models.md](../data-models.md) §2 (knowledge tables)

---

## 3. Platform Store

**Code:** `backend/storage/user_repository.py`  
**Schemas:** [data-models.md](../data-models.md) §3 (platform tables)

| Class | Methods |
|-------|---------|
| `UserRepository` | `upsert_oauth_user`, `get_by_id` |
| `UserBookRepository` | `link`, `get`, `list_for_user` |
| `ConversationRepository` | `create`, `get`, `list_for_user`, `update_title` |
| `MessageRepository` | `save`, `list_for_conversation` |
| `ExportRepository` | `save`, `get`, `get_for_user` |

---

## 4. Schema Models

```python
# backend/src/modules/storage/schema.py
class BookMetadata(BaseModel):
    title: str
    subject: str
    source_file_name: str
    total_pages: int
    book_id: str  # auto-generated UUID
```

---

## 5. Persistence Triggers

| Caller | What's Saved |
|--------|--------------|
| `run_pipeline(persist_to_db=True)` | Book + TOC + fragments + artifacts |
| `IngestionService.ingest_upload` | Book + TOC via separate `save_full_toc` |
| `ChatService.send_message` | Messages + optional exports |
| `UserRepository.upsert_oauth_user` | User profile |
| `RagService.ensure_index` | RAG chunks + index meta |

---

## 6. Tests

| Test | Coverage |
|------|----------|
| `test_fragment_coverage.py` | DB counts match pipeline |
| `test_rag_retriever.py` | RAG chunk storage |

See [testing.md](../testing.md) §6.
