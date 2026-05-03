# 04 — Structure extraction (headings & fragments)

All paths below are **invoked from** `run_pipeline` unless noted.

## Noise

**File:** `src/structure/noise_filter.py`

```
mark_noise(lines) -> (lines, noise_log)
```

Internal helpers: margin buckets, page-number detection, `_should_protect_from_noise`.

## Candidate scoring (authoritative candidates)

**File:** `src/structure/candidate_scoring.py` (canonical; pipeline imports this)

```
collect_candidates_scored(lines) -> (candidates, scoring_log)
  → _score_line(ln) per line
```

## Heading validity gate (deterministic)

**File:** `src/structure/heading_validity_gate.py`

```
gate_heading_validity_candidates(candidates, lines=...) -> (filtered, gate_log)
```

Notable internals: `_embedding_gate_is_fake_heading`, `gate_toc_candidates` (exported; not called from current `pipeline.run_pipeline` — TOC path uses `clean_toc` + repeat detection instead).

## Fragments

**File:** `src/structure/fragments.py`

```
build_fragments(lines, headings) -> (BuildFragmentsResult, fragments_log)
```

Internals: `_to_lines`, `_normalize_fragment_text`, `_fragment_stats`.

## TOC cleaning (post-heading list)

**File:** `src/structure/toc_cleaning.py`

```
clean_toc(headings, fragments=...) -> List[FinalHeading]
```

Uses dedupe helpers `_dedupe_keep_stronger`, fragment text lookup (for a future non-identity `clean_toc`). Current `clean_toc` is an identity pass.

## Deterministic heuristics (tests)

**File:** `src/structure/heading_heuristics.py` — `should_force_invalid_enumerated_list_item` (used by unit tests; not wired into `run_pipeline` today).

## Supporting utilities (not the main `run_pipeline` order)

| Module | Main symbols | Notes |
|--------|----------------|--------|
| `context_preview_builder.py` | `build_context_preview` | Candidate scoring context |
| `noise_filter.py` | (see above) | **In pipeline** |

## `src/structure/toc_splitter.py`

Utility for splitting TOC-forward occurrences — not called by `run_pipeline` (optional offline use).
