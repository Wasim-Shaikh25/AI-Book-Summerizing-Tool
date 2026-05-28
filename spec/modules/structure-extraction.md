# Module: Structure Extraction

> Code package: `src/structure/`  
> Legacy: `doc/spec/04-structure-extraction-chain.md`

## Purpose

Deterministic heading detection, validity filtering, continuity enforcement, fragment building, and TOC cleaning.

## Stage Modules

| Stage | Module | Key function |
|-------|--------|--------------|
| Noise | `noise_filter.py` | `mark_noise` |
| Candidates | `candidate_scoring.py` | `collect_candidates_scored` |
| Validity gate | `heading_validity_gate.py` | `gate_heading_validity_candidates` |
| Continuity | `continuity_filter.py` | `apply_continuity_filter` |
| Fragments | `fragments.py` | `build_fragments` |
| TOC clean | `toc_cleaning.py` | `clean_toc` |
| Heuristics | `heading_heuristics.py` | `should_force_invalid_enumerated_list_item` |
| Context | `context_preview_builder.py` | `build_context_preview` |

## Final Structuring (optional LLM)

| Module | Role |
|--------|------|
| `final_structuring/doubted_section_resolver.py` | Resolve ambiguous segments |
| `final_structuring/revalidation.py` | Selective revalidation pass |
| `final_structuring/models/segment_llm_classifier.py` | Fast local LLM classifier |

## Dependencies

- `src/core/models` types throughout
- Optional: `src/core/llm_chat_client.py` for Stage 15b

## Note

Use **`src/structure/candidate_scoring.py`** only — duplicate in `src/core/` is legacy (see `unused-tracking.md`).
