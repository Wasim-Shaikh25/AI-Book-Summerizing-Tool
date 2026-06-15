# Code Reference — RAG

> **Package:** `backend/src/modules/rag/`  
> **Module spec:** [../modules/rag-retrieval.md](../modules/rag-retrieval.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `service.py` | `RagService` index lifecycle + retrieve API | Single entry for web/CLI |
| `chunk_builder.py` | Section → overlapping chunks | Long sections need multiple retrieval units |
| `indexer.py` | FAISS build/load/save | Fast vector search local |
| `retriever.py` | Hybrid lexical + vector fusion | Legal terms need keyword + semantic |
| `reranker.py` | Cross-encoder rerank top-k | Precision after hybrid recall |
| `context_builder.py` | Dedupe + format Q&A context string | LLM context window limits |

---

## `service.py` — `RagService`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `ensure_index(book_id, sections, lines, log_dir)` | Build or load FAISS index | Lazy index on first ask (`UPLOAD_SKIP_RAG`) | `ChatService`, `rag_index_helper` |
| `retrieve(book_id, question, top_k)` | Hybrid retrieve + rerank | Q&A evidence selection | `BookQaEngine` |

---

## `chunk_builder.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `sections_to_rag_chunks(sections, chunk_words, overlap)` | Section list → chunk records | Default one chunk per section (`RAG_CHUNK_SIZE_WORDS=0`) | `ensure_index` |

---

## `indexer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `build_faiss_index(chunks, embedder)` | Embed + build index | First-time index | `ensure_index` |
| `load_faiss_index(book_id, dir)` | Load from `output/rag_index/` | Reuse across sessions | `ensure_index` |
| `FaissVectorIndex` | Wrapper for add/search/save | Isolate faiss-cpu API | Service |

---

## `retriever.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `hybrid_retrieve(question, chunks, index, weights)` | Vector + lexical fusion | Statute names match lexically; concepts match semantically | `RagService.retrieve` |
| `chunks_to_sections(chunks)` | Map chunks back to section ids | Q&A cites whole sections | `BookQaEngine` |

---

## `reranker.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `get_rag_reranker()` | Lazy cross-encoder singleton | Model load is expensive | `retrieve` |
| `rerank_chunks(question, chunks, top_k)` | Re-score top candidates | Hybrid recall is noisy on long books | `RagService.retrieve` |

---

## `context_builder.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `dedupe_sections(sections)` | Remove duplicate section hits | Multiple chunks same section | `build_qa_context` |
| `build_qa_context(sections, max_chars)` | Format citations for LLM | Bounded context + provenance | `BookQaEngine` |
