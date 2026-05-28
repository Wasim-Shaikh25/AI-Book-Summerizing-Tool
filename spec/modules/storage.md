# Module: Storage

> Code package: `src/storage/`  
> Legacy: `doc/spec/07-storage-repositories.md`

## Purpose

SQLite knowledge base for processed books, topics, and finalized TOC/fragment graphs.

## Public APIs

| Class | Module | Role |
|-------|--------|------|
| `KnowledgeStore` | `knowledge_store.py` | Connection + artifact save |
| `BookRepository` | `book_repository.py` | Book CRUD |
| `TopicRepository` | `topic_repository.py` | Topic search/save |
| `TocRepository` | `toc_repository.py` | TOC graph persistence |

## Schema

- Pydantic models in `schema.py`: `BookMetadata`, `TopicKnowledge`
- SQLite DDL managed in `knowledge_store.py` / schema module

## Dependencies

- `PipelineResult` artifacts from `run_pipeline`
- Local SQLite file (path from config)
