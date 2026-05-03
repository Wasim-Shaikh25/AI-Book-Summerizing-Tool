# 01 — Entry, CLI, interaction layer

## Chain: application start

```
main.main()
  → CommandLoop.__init__()
       → CommandParser()
       → KnowledgeStore()
       → BookRepository(store)
       → TopicRepository(store)
       → TocRepository(store)
       → WordExporter(output_folder=OUTPUT_FOLDER)   # src/config.OUTPUT_FOLDER
  → CommandLoop.start()    # blocking REPL
```

**Files:** `main.py`, `src/interaction/command_loop.py`, `src/config.py`.

## Chain: user pastes a PDF path

```
CommandLoop.start()
  → (path ends with .pdf and exists) CommandLoop._handle_ingestion(file_path)
       → extract_pdf(file_path)                         # metadata: page_count
       → BookRepository.save_book(BookMetadata(...))
       → run_pipeline(file_path, enable_logs=False)      # src.core.pipeline
       → SQL DELETE topics for book_id                   # legacy cleanup
       → TocRepository.save_full_toc(book_id, result...)
       → sets current_file_path, rewriter = None
```

**Files:** `src/interaction/command_loop.py`, `src/ingestion/pdf_extractor.py`, `src/core/pipeline.py`, `src/storage/book_repository.py`, `src/storage/toc_repository.py`.

## Chain: non-PDF input (intent path)

```
CommandLoop.start()
  → CommandParser.parse_intent(user_input)
       → fixed strings: "exit" | "help" | "export"
       → else: IntentResult(...) fallback (no LLM)
  → CommandLoop._process_intent_pipeline(IntentResult)
       → if scope full_book and rewriter: RewriteEngine.run(...)   # not set after current ingestion
       → else: NotImplementedError (Q&A retrieval not wired)
```

**Files:** `src/interaction/command_parser.py`, `src/interaction/command_loop.py`.

## Chain: export last answer

```
CommandLoop._handle_export()
  → WordExporter.assemble_full_book_structured_text(...)
  → WordExporter.structured_text_to_word(..., include_toc=False)
```

**Files:** `src/export/word_exporter.py`.

## Handlers (present but not central to ingestion)

- `src/interaction/handlers/ask_handler.py`, `export_handler.py`, `question_paper_handler.py`, `rewrite_handler.py` — available for extension; **`CommandLoop` does not import them** in the shown ingestion path.
