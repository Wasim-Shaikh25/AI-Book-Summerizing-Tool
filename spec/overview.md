# Overview — AI Notes Creator Model

> Status: **ACTIVE** — synced from codebase 2026-05-27

---

## 1. Purpose

Transform legal/academic **PDF books** into structured notes:

1. **Ingest** PDF → normalized lines with layout metadata
2. **Extract structure** — heading candidates, validity gates, continuity, fragments
3. **Resolve TOC** — deterministic repeat-TOC detection, book metadata tagging
4. **Persist** (optional) — SQLite knowledge store
5. **Export** (optional) — Word `.docx` via Pandoc
6. **Generate** (optional, partial) — LLM rewrite / doubted-section resolver

The production path is **deterministic**; LLM stages are optional overlays.

---

## 2. Entry Points

| Entry | Module | Role |
|-------|--------|------|
| `python main.py` | `src/interaction/command_loop.py` | Interactive CLI |
| `from src.book_pipeline import run_pipeline` | `src/core/pipeline.py` | Canonical pipeline import |
| `python -m src.debug.run_toc_trace <pdf>` | `src/debug/run_toc_trace.py` | Debug trace (logs + DB) |

---

## 3. End-to-End Flow

```
PDF
 └─ ingestion (extract → enrich → normalize)
     └─ structure (noise → candidates → gate → continuity → fragments → TOC)
         └─ run_pipeline → PipelineResult
             ├─ storage (optional SQLite persist)
             ├─ export (Word / terminal)
             ├─ generation (optional LLM rewrite / doubted resolver)
             └─ debug (stage JSON logs + PDF visualization)
```

---

## 4. Package Map

| Area | Path | Role |
|------|------|------|
| Core | `src/core/` | `run_pipeline`, models, `LlmChatClient` |
| Ingestion | `src/ingestion/` | PDF → lines, layout enrichment |
| Structure | `src/structure/` | Scoring, noise, gates, fragments, TOC |
| Storage | `src/storage/` | SQLite schema + repositories |
| Interaction | `src/interaction/` | CLI loop, command parser, handlers |
| Debug | `src/debug/` | Trace runner, PDF visualizer |
| Export | `src/export/` | Word export, OutputManager |
| Generation | `src/generation/` | Rewrite engine (stub), model router |
| Domain | `src/domain/` | Target pure types (parallel to `core.models`) |
| Utils | `src/utils/` | PDF/OCR low-level helpers |

---

## 5. Operating Modes

| Mode | Trigger | Logging | DB |
|------|---------|---------|-----|
| CLI ingestion | `CommandLoop` | Off by default | Off by default |
| Debug trace | `run_toc_trace` | On (`logs/run_*`) | On |
| OpenAI pipeline script | `scripts/run_full_openai_pipeline.py` | Configurable | Configurable |
