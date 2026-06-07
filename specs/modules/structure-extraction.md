# Module: Structure Extraction

> **Code package:** `backend/src/modules/structure/`  
> **Pipeline stages:** `backend/src/modules/pipeline/stages.py`

---

## 1. Purpose

Deterministic heading detection, validity filtering, continuity enforcement, fragment building, TOC cleaning, and final structuring (stages 15a–15f).

---

## 2. Stage Modules

| Stage | File | Key function |
|-------|------|--------------|
| Noise | `noise_filter.py` | `mark_noise` |
| Candidates | `candidate_scoring.py` | `collect_candidates_scored` |
| Validity gate | `heading_validity_gate.py` | `gate_heading_validity_candidates` |
| Continuity | `continuity_filter.py` | `apply_continuity_filter` |
| Fragments | `fragments.py` | `build_fragments` |
| TOC clean | `toc_cleaning.py` | `clean_toc` |
| Heuristics | `heading_heuristics.py` | `should_force_invalid_enumerated_list_item` |
| Context | `context_preview_builder.py` | `build_context_preview` |
| TOC detection | `toc_repeat_detection.py` | `detect_deterministic_toc`, etc. |

---

## 3. Final Structuring (`final_structuring/`)

Runs in `stage_final_structuring` via `final_structuring_stage.py`:

| File | Stage | Role |
|------|-------|------|
| `book_assembler.py` | 15a, 15d, 15c, 16 | `build_heading_hierarchy`, `build_ultimate_sections`, `assemble_final_book`, `build_rag_snapshot` |
| `chapter_hierarchy_builder.py` | 15e | Chapter hierarchy (LLM + rules) |
| `heading_cleanup.py` | 15f | Weak title cleanup, chapter dedup |
| `doubted_section_resolver.py` | 15b | Resolve ambiguous segments (late TOC) |
| `revalidation.py` | 15b | Selective revalidation pass |
| `signal_extractor.py` | 15b | Feature signals for resolver |
| `models/segment_llm_classifier.py` | 15b | Fast local LLM classifier |
| `models/mini_lm_encoder.py` | 15b | MiniLM embeddings |
| `models/cross_encoder_model.py` | 15b | Cross-encoder scoring |
| `models/bigbird_encoder.py` | 15b | BigBird encoder (optional) |

**Log artifacts:** `15a_heading_hierarchy.json` → `15d_ultimate_sections.json` → `15e_chapter_hierarchy.json` → `15f_heading_cleanup.json` → `15c_final_book.json` → `16_rag_snapshot.json`

---

## 4. Doubted Sections (Stage 15b)

Triggered when `first_toc_page > 3` in `stage_doubted_sections`.

| File | Role |
|------|------|
| `backend/src/modules/pipeline/stage_15b.py` | `run_stage_15b_if_doubted` — pipeline hook |
| `doubted_section_resolver.py` | Main resolver logic |
| `revalidation.py` | LLM audit of flagged segments |

**Logs:** `14_doubted_sections.json`, `15b_doubted_resolved.json`, `15b_revalidation.json`

---

## 5. Dependencies

- `src.shared.models` — `NormalizedLine`, `HeadingCandidate`, `FinalHeading`, `Fragment`
- `src.modules.pipeline.llm_chat_client` — optional LLM for Stage 15b
- `src.modules.structure.logging.pipeline_logger` — stage JSON output

---

## 6. Tests

| Test | Coverage |
|------|----------|
| `test_pipeline_stages.py` | Doubted-section flagging, metadata stripping |
| `test_continuity_and_gate.py` | Line ID parsing, heading heuristics |
| `test_heading_validator_heuristics.py` | Enumeration blocking |
| `test_heading_cleanup.py` | Stage 15f cleanup rules |

See [testing.md](../testing.md).
