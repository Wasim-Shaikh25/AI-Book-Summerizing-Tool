# Code Reference — Interaction (CLI)

> **Package:** `backend/src/modules/interaction/`  
> **Module spec:** [../modules/cli-interaction.md](../modules/cli-interaction.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `command_loop.py` | Interactive CLI REPL | `python main.py` entry |
| `command_parser.py` | Regex/heuristic intent parsing | Fast deterministic routing (ADR-011) |
| `intent_router.py` | Optional LLM intent + prompt refinement | Web chat uses LLM router; CLI can too |
| `intent_catalog.py` | Task type taxonomy | Maps intents to handlers |
| `prompt_refiner.py` | Polish user ask before rewrite | Better rewrite without changing user intent storage |
| `handlers/ask_handler.py` | Q&A with RAG | Ask intents |
| `handlers/rewrite_handler.py` | Full book rewrite | Rewrite intents |
| `handlers/export_handler.py` | Export saved book | Export intents |

---

## `command_loop.py` — `CommandLoop`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `start()` | Read stdin loop, dispatch handlers | CLI UX | `main.py` |

---

## `command_parser.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `parse_intent(text)` | Keyword/regex → `IntentResult` | No LLM latency for obvious commands | CLI default |
| `effective_user_instruction(result)` | Original user text for executor | Refined prompt is display-only | Handlers |

---

## `intent_router.py` — `IntentRouter`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `parse_intent(text)` | LLM classification + refinement | Ambiguous web chat messages | `ChatService` |
| `use_llm_intent()` | Env gate | Fallback to parser when off | Router |
| `apply_prompt_refinement(instruction, task)` | OpenRouter polish | Study-notes phrasing | Web rewrite path |

---

## `intent_catalog.py`

| Symbol | Purpose | Why |
|--------|---------|-----|
| `is_rewrite_task(task_type)` | Route to `RewriteHandler` | Task taxonomy |
| `is_qa_task(task_type)` | Route to `AskHandler` | Task taxonomy |
| `intent_options_for_prompt()` | LLM JSON schema labels | Intent router system prompt |

---

## `prompt_refiner.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `refine_user_prompt(instruction, task)` | LLM rewrite of user ask | Clearer notes instruction | `IntentRouter`, batch pipeline |
| `should_refine(instruction)` | Skip short/clear asks | Save tokens | Refiner |
| `refiner_backend()` | OpenAI vs OpenRouter | Config-driven | Refiner |

---

## Handlers

| Handler | Symbol | Purpose | Why |
|---------|--------|---------|-----|
| `AskHandler` | `handle` / `handle_intent` | Load book, RAG, `BookQaEngine.answer` | Q&A path |
| `RewriteHandler` | `handle_intent` | `RewriteEngine.run` + export | Notes generation path |
| `ExportHandler` | `handle_export_book` | Re-export from saved logs | No re-ingest |
