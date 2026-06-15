# Module: Structure Extraction

> **Code package:** `backend/src/modules/structure/`  
> **Symbol reference:** [../code-reference/structure.md](../code-reference/structure.md)  
> **Pipeline stages:** `backend/src/modules/pipeline/stages.py`

> **Stage name map:** [stage-catalog.md](./stage-catalog.md)

---

## 1. Purpose

Deterministic heading detection, validity filtering, continuity enforcement, fragment building, TOC cleaning, and final structuring (`partition_tree` through `rag_snapshot` — see [stage-catalog.md](./stage-catalog.md)).

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

Runs in `stage_build_book_structure` via `structure_orchestrator.py` → `final_structuring_stage.py`:

| File | Log key | Role |
|------|---------|------|
| `book_assembler.py` | `partition_tree`, `partition_sections`, `assemble_book`, `rag_snapshot` | Tree, rewrite sections, final book, RAG snapshot |
| `chapter_hierarchy_builder.py` | `group_chapters` | Chapter hierarchy (rules/MiniLM + optional LLM) |
| `heading_cleanup.py` | `clean_titles` | Weak title cleanup, chapter dedup, `sanitize_hierarchy_headings` |
| `chapter_placement.py` | `place_chapters` | `run_chapter_placement`, **`enforce_chapter_structure`** |
| `subheading_refinement.py` | `refine_titles` | `run_heading_refinement`, parent-mirror + verbose title fixes |
| `hierarchy_openai_refinement.py` | `cloud_hierarchy` | Optional cloud regroup + title polish |
| `title_validation.py` | `validate_titles` | `validate_chapter_hierarchy` (FLAN/MiniLM title checks) |
| `dropped_heading_registry.py` | — | `is_statute_prose_heading`, partition/noise patterns |
| `doubted_section_resolver.py` | `resolve_doubted_toc` | Resolve ambiguous segments (late TOC) |
| `revalidation.py` | `resolve_doubted_revalidation` | Selective revalidation pass |
| `signal_extractor.py` | — | Feature signals for resolver |
| `models/segment_llm_classifier.py` | — | Fast local LLM classifier |
| `models/mini_lm_encoder.py` | — | MiniLM embeddings |
| `models/cross_encoder_model.py` | — | Cross-encoder scoring |
| `models/bigbird_encoder.py` | — | BigBird encoder (optional) |

**Pipeline order** (`structure_orchestrator.py`): `partition_tree` → `partition_sections` → `group_chapters` → `place_chapters` → `clean_titles` → `refine_titles` → `cloud_hierarchy` → `validate_titles` → `assemble_book` → `rag_snapshot`.

**`enforce_chapter_structure()`** runs at end of `validate_titles`, `refine_titles`, `cloud_hierarchy`, and again at rewrite load. It:
- splits at structural markers and oversized chapters (`max_sections_per_chapter` default 10)
- fixes parent-mirror chapters (chapter title ≈ first section)
- sanitizes headings and repairs unacceptable/statute-prose section titles
- re-splits after fixes and renumbers chapters

**Log artifacts (filenames on disk):** `s15a_…` → `s15d_…` → `s15e_…` → `s15h_…` → `s15f_…` → `s15i_…` → `s15j_…` → `s15g_…` → `s15c_…` → `s16_…` — see [stage-catalog.md](./stage-catalog.md) for semantic log keys.

---

## 4. Doubted TOC resolution (`resolve_doubted_toc`)

Triggered when `first_toc_page > 3` in `stage_flag_doubted_toc`.

| File | Role |
|------|------|
| `backend/src/modules/pipeline/stage_15b.py` | `run_stage_15b_if_doubted` — pipeline hook |
| `doubted_section_resolver.py` | Main resolver logic |
| `revalidation.py` | LLM audit of flagged segments |

**Logs:** `s12_doubted_sections.json`, `s15b_doubted_resolved.json` (`resolve_doubted_toc`), `s15b_revalidation.json` (`resolve_doubted_revalidation`)

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
| `test_enforce_chapter_structure.py` | Mega-chapter split, mirror/title enforce |
| `test_title_validation.py` | Stage 15g title validation |
| `test_heading_title_validation.py` | Heading title heuristics |
| `test_dropped_heading_registry.py` | Statute prose / partition patterns |

See [testing.md](../testing.md).
