# Tasks — AI Notes Creator Model

> Execution order for ongoing work. Update as stages complete.

---

## Stage 0 — MESO Bootstrap ✅

## Stage 0b — MESO Structure Refactor ✅

## Stage 1 — Spec ⇄ Code Alignment ✅

---

## Stage 2 — LLM Pipeline Hardening ✅

- [x] Wire Stage 15b doubted resolver in `run_pipeline` (`stages.py` + `stage_15b.py`)
- [x] Add missing encoder modules (`signal_extractor`, MiniLM, cross-encoder, BigBird stub)
- [x] Log stages `15b_doubted_resolved.json`, `15b_revalidation.json`
- [x] Unit tests for provider aliases, signals, parser
- [x] Document env keys in `parameters-config.md` and `.env.example`

---

## Stage 3 — CLI & Export ✅

- [x] Implement `RewriteEngine` via `RewriteModelRouter` + TOC sections
- [x] Implement `ExportHandler` and `RewriteHandler`
- [x] Wire `CommandLoop` with book_id tracking + keyword intents

---

## Stage 4 — Plugin Pipeline Restructure ✅

- [x] `PipelineContext` + `STAGES` plugin list in `stages.py`
- [x] Thin `runner.py` orchestrator shell
- [x] Updated `spec/architecture.md` (ADR-008)

---

## Dependencies

```
Stage 0 → Stage 1 → Stage 2 → Stage 3 → Stage 4
```

Spec updates MUST precede each stage (MESO Rule 10).
