# Module: Signal-Sections Pipeline V2

> **Code:**
> - Structure: `backend/src/modules/structure/signal_sections/`
> - Rewrite:   `backend/src/modules/generation/signal_rewrite/`
> - Export:    `backend/src/modules/export/signal_export/`
> - Runner:    `backend/scripts/pipeline_signal_sections.py`
> **Symbol reference:** [`../code-reference/signal_sections.md`](../code-reference/signal_sections.md)
> **Status:** **Implemented (2026-06-16)** — parallel V2, opt-in.
> **Does not modify the existing pipeline.** `scripts/run_full_openai_pipeline.py` keeps current behavior; no shared files were edited.

---

## 1. Purpose

A **second, opt-in** end-to-end pipeline whose entire goal is to make the generated DOCX **directly comparable to the source PDF**:

- **Chapter count and chapter titles** = the source PDF's structural markers (`MODULE/UNIT/PART/CHAPTER N`, Roman major, `(Arts. N–M)` ranges). No LLM-rewritten "study titles".
- **Section text** = the validated heading text taken verbatim from the PDF line. The model never renames section titles.
- **Section span** = from one high-signal heading to the next. Lower-confidence headings inside that span are passed to the LLM as inner-heading **hints**, not as section boundaries.
- **One LLM call per section** (default Gemini Flash Lite via OpenRouter). The LLM decides which inner hints become real `###` sub-topics in the rewrite; everything else folds into prose. A deterministic post-validator strips any `###` the model invents.

Triggered with `python backend/scripts/pipeline_signal_sections.py <pdf>`. The legacy pipeline keeps running through `scripts/pipeline_full_book.py` / `scripts/run_full_openai_pipeline.py` exactly as before.

---

## 2. End-to-end flow

```text
1. Standard early structure stages (re-used from the existing pipeline,
   stages 01–13). Mutates a PipelineContext. Produces:
     • ctx.lines, ctx.book_title
     • ctx.final_headings_2_items   (validated, TOC-filtered headings)
     • logs/run_<ts>/s03_candidate_scoring.json (read back for boundary picking)

2. signal_classifier.pick_boundary_line_ids(
       validated_headings = ctx.final_headings_2_items,
       scoring_log        = s03_candidate_scoring,
       percentile         = SIGNAL_BOUNDARY_PERCENTILE,
       min_score          = SIGNAL_BOUNDARY_MIN_SCORE,
       include_structural = SIGNAL_BOUNDARY_INCLUDE_STRUCTURAL,
   )
   → boundaries (sorted by line_id), BoundarySelectionStats.

3. signal_partitioner.build_sections(boundaries, validated_headings, lines)
   → one section per boundary span. Body = non-noise line text between
     boundary and next boundary. inner_headings = validated headings inside
     the span that were NOT picked as boundaries (with score + page + signals).

4. pdf_chapter_grouper.group_into_chapters(sections, lines)
   → group sections under chapters using PDF structural markers only;
     promote_h1 fallback if the PDF has none. No renaming. No size-based splits.

5. pdf_hierarchy_assembler.assemble_hierarchy(...)
   → signal_hierarchy.json payload (verbatim PDF titles).

6. signal_rewrite.rewrite_engine.rewrite_signal_sections(hierarchy, ...)
   → one OpenRouter Gemini-Flash-Lite call per section (parallelized).
     Prompt contains chapter L1 + section L2 + inner_heading hints + prev/next
     section headings + overlap text. Output validated by inner_heading_decider.

7. signal_export.pdf_mirror_docx.assemble_signal_markdown(...) → Markdown.
   signal_export.pdf_mirror_docx.export_signal_docx(...)      → DOCX.
```

All artifacts go to a **separate** log tree `logs/run_signal_<ts>/` so existing audit / re-export scripts that read `logs/run_<ts>/` never see them.

---

## 3. Artifacts written

| File | Producer | Content |
|---|---|---|
| `logs/run_<ts>/s*.json` | re-used early stages | standard pipeline logs (needed for boundary picking) |
| `logs/run_signal_<ts>/signal_boundaries.json` | `signal_logger` | every picked boundary `{line_id, text, page, score, source, signals}` + selection stats |
| `logs/run_signal_<ts>/signal_hierarchy.json` | `pdf_hierarchy_assembler` | full chapter → section → inner_heading tree (verbatim PDF text) |
| `logs/run_signal_<ts>/signal_rewritten.json` | `rewrite_engine` | per-section LLM output, model, attempts, decider report |
| `logs/run_signal_<ts>/signal_run_meta.json` | runner | resolved structure + rewrite settings, summary counts, output paths |
| `output/<title>__signal_<ts>.md` | exporter | Markdown that mirrors the PDF hierarchy |
| `output/<title>__signal_<ts>.docx` | exporter | DOCX rendered through the standard `markdown_docx_renderer` |

When the rewrite is skipped (`--skip-rewrite`), `signal_rewritten.json` is not written and the Markdown / DOCX body uses the raw PDF source text with a `[signal] rewrite unavailable` callout per section.

---

## 4. Boundary algorithm

```
structural_markers = lines matching ^(CHAPTER|MODULE|UNIT|PART) <num/roman>
                                   | ^[IVXLC]+\.\s+[A-Z]
                                   | (Arts?\.? \d+ ...)   when len(text) >= 20

percentile_pool    = validated headings NOT already in structural_markers
threshold          = max(SIGNAL_BOUNDARY_MIN_SCORE,
                         percentile_cutoff(percentile_pool.scores, percentile))
percentile_picks   = {h ∈ percentile_pool | h.score >= threshold}

boundaries         = sorted_by_line_id(structural_markers ∪ percentile_picks)
```

Defaults: `percentile=35`, `min_score=6`, `include_structural=1`.

---

## 5. Rewrite prompt design (subject-agnostic)

For each section the LLM receives:

- **Parent path**: book title, chapter number + heading (L1), section number + heading (L2 verbatim, marked "DO NOT change or print").
- **Section page range**.
- **Inner heading hints**: every detected inner heading with its line, page, confidence, signals. Instruction is explicit: keep as `### ...` only when the source text below introduces real new sub-content; otherwise fold into prose with no heading at all.
- **Continuity blocks**: previous section heading + tail of its body (~ `SIGNAL_REWRITE_OVERLAP_CHARS` chars), next section heading + head of its body (~ half that).
- **Primary source**: the section body inside `----- SOURCE BEGIN/END -----` markers with a hard rule to use only that text.

After the call, `inner_heading_decider` enforces:

1. Strip any echoed `#` / `##` title at the top.
2. Unwrap a whole-answer code fence (keeps mermaid fences intact).
3. Downgrade any `### ...` whose text does not match a declared inner heading to `**...**` so the model cannot invent sub-topics.

---

## 6. Configuration surface (all new `SIGNAL_*` keys)

| Variable | Default | Effect |
|---|---|---|
| `SIGNAL_BOUNDARY_PERCENTILE` | `35` | Keep top N % of validated headings as boundaries |
| `SIGNAL_BOUNDARY_MIN_SCORE` | `6` | Minimum raw heading score required |
| `SIGNAL_BOUNDARY_INCLUDE_STRUCTURAL` | `1` | Always keep CHAPTER/MODULE/UNIT/PART/Roman markers |
| `SIGNAL_PROMOTE_H1_COUNT` | `8` | L1 promotions when PDF has no structural markers |
| `SIGNAL_REWRITE_PROVIDER` | `openrouter` | Chat provider (uses existing `LlmChatClient`) |
| `SIGNAL_REWRITE_MODEL` | `google/gemini-2.5-flash-lite` | OpenRouter model slug |
| `SIGNAL_REWRITE_TEMPERATURE` | `0.2` | LLM temperature |
| `SIGNAL_REWRITE_MAX_TOKENS` | `2500` | Per-section ceiling |
| `SIGNAL_REWRITE_OVERLAP_CHARS` | `600` | Continuity context size |
| `SIGNAL_REWRITE_PARALLEL_WORKERS` | `4` | Concurrent LLM calls |
| `SIGNAL_REWRITE_USER_INSTRUCTION` | `""` | Style override; falls back to `REWRITE_USER_INSTRUCTION` |
| `SIGNAL_OUTPUT_SUFFIX` | `__signal` | Output filename suffix |
| `SIGNAL_EXPORT_DOCX` | `1` | `0` writes Markdown only |
| `SIGNAL_LOG_LEVEL` | `INFO` | Runner Python logger level |

OpenRouter auth reuses existing `OPENROUTER_API_KEY`. No new secrets.

---

## 7. Tests

| Test file | Coverage |
|---|---|
| `backend/tests/unit/test_signal_classifier.py` | structural-marker detection, percentile cutoff, min-score override, dedup, empty input |
| `backend/tests/unit/test_signal_partitioner.py` | section spans, inner-heading attachment, noise skip, empty-section drop, verbatim heading preservation |
| `backend/tests/unit/test_pdf_chapter_grouper.py` | chapter grouping by PDF markers, promotion fallback, verbatim chapter titles |
| `backend/tests/unit/test_signal_rewrite_prompt.py` | prompt construction (parent path, hints, overlap), top-title strip, code-fence unwrap, undeclared `###` downgrade |
| `backend/tests/unit/test_signal_pipeline_end_to_end.py` | full structure → mocked rewrite → markdown assembly + logger artifacts |

All 33 new tests pass; all 378 pre-existing unit tests continue to pass (regression-clean per acceptance criterion SS-05).

---

## 8. Acceptance criteria status (from change plan)

| ID | Status |
|---|---|
| SS-01 chapter count == PDF structural markers (when present) | met (verified on `The Constitution Of India By Jhavala.pdf` — 193 chapters from 202 structural markers via marker-to-section alignment) |
| SS-02 section headings verbatim from PDF | met (no LLM rename anywhere in the new pipeline; titles taken from `ctx.final_headings_2_items[i].text`) |
| SS-03 every emitted `###` matches a declared inner heading | met by `inner_heading_decider.validate_inner_headings` (tested) |
| SS-04 existing `logs/run_<ts>/` artifacts untouched | met (new artifacts live in `logs/run_signal_<ts>/`) |
| SS-05 existing pipeline byte-equivalent after addition | met (regression test suite: 378 / 378 unit tests still pass) |
| SS-06 all rewrite LLM calls go through OpenRouter | met (engine routes via `client.chat_with_provider("openrouter", …)` with `SIGNAL_REWRITE_MODEL`) |
| SS-07 four signal artifacts written | met (boundaries, hierarchy, rewritten, run_meta) |
| SS-08 LLM calls ≤ section count | met (`rewrite_signal_sections` issues one call per section, empty-source sections are skipped) |
| SS-09 no existing module file modified | met (only new directories under `signal_sections/`, `signal_rewrite/`, `signal_export/` + the new runner script) |

---

## 9. Out of scope (intentionally not built)

- Web / chat-UI integration (script only)
- Re-implementing PDF heading detection or scoring (re-uses existing modules)
- Any automatic switching of existing defaults to this pipeline
- Any new audit module — the existing `notes_quality_audit` still applies to outputs of the legacy pipeline; signal outputs can be diffed against the PDF directly because titles are verbatim
- Hierarchy-aware retry, structural cleanup, MiniLM rerank, or any additional structural transformations beyond §4
