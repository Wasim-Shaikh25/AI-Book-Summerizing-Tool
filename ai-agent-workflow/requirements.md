# Requirements — AI Notes Creator Model

> MESO-aligned requirements document. Authoritative design: [`../spec/SDD.md`](../spec/SDD.md).

---

## Problem Definition

Legal/academic PDF books need automated structure extraction (headings, fragments, TOC) and optional AI-assisted note generation/export — without losing reproducibility or traceability.

---

## Scope

**In scope:**

- PDF ingestion with layout metadata
- Deterministic heading/fragment/TOC pipeline
- Optional SQLite persistence
- Optional LLM doubted-section resolver and rewrite
- Word export and CLI interaction
- Debug trace + visualization

**Out of scope (current baseline):**

- Web UI
- Multi-user cloud deployment
- Full RAG Q&A (stub only)

---

## Functional Requirements

| ID | Requirement |
|----|-------------|
| FR1 | Ingest PDF and produce normalized line stream with layout flags |
| FR2 | Detect heading candidates, apply validity and continuity filters |
| FR3 | Build fragments and clean TOC sections deterministically |
| FR4 | Optionally persist book/TOC graph to SQLite |
| FR5 | Optionally log whitelisted stage JSON for debugging |
| FR6 | Export structured content to Word `.docx` |
| FR7 | Support multiple LLM providers via centralized config |
| FR8 | Resolve doubted sections via optional Stage 15b local LLM |

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR1 | Deterministic core path must run without LLM |
| NFR2 | All tunables in `src/config.py` / `.env` (MESO Rule 12) |
| NFR3 | Spec precedes code; changes logged in `spec/change-log.md` |
| NFR4 | No duplicate business logic across modules (MESO Rule 13) |

---

## Assumptions

- Input PDFs are text-based or OCR-fallback capable
- Local GGUF models available under `models/` for llama.cpp path
- Pandoc installed for Word export
