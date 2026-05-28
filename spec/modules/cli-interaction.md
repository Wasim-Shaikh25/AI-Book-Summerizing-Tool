# Module: CLI Interaction

> Code package: `src/interaction/`  
> Legacy: `doc/spec/01-entry-cli-interaction.md`

## Purpose

Interactive terminal loop for PDF ingestion and intent routing (rewrite, export, Q&A, question papers).

## Public APIs

- `CommandLoop.start()` — main REPL
- `CommandParser.parse_intent(user_input) → IntentResult`

## Handlers

| Handler | Status | Module |
|---------|--------|--------|
| Ingestion | Active | inline in `CommandLoop._handle_ingestion` |
| Rewrite | Partial/legacy | `handlers/rewrite_handler.py` |
| Export | Stub | `handlers/export_handler.py` |
| Ask | Stub | `handlers/ask_handler.py` |
| Question paper | Active | `handlers/question_paper_handler.py` |

## Dependencies

- `src/book_pipeline.run_pipeline` for ingestion path
- `src/config.py` for paths and LLM settings

## Flow

```
main.py → CommandLoop.start()
  → parse user input
  → route to handler or ingestion pipeline
```
