# Requirements — Notes Quality Analysis Module

> **Status:** Implemented (2026-06-10)  
> **Date:** 2026-06-10

## Problem

After PDF → structure → rewrite → DOCX export, there is no automated report answering:

- Was **all important PDF content** reflected in the notes?
- Are notes **easy and simple** (as requested in rewrite instructions)?
- Are **topics repeated** across sections?
- Are **headings proper topic labels** (not prose, not parent topic copied as first subsection)?
- Does **DOCX match** markdown structure?

Existing `compare_notes_quality.py` script covers much of this but is not a pipeline module and lacks LLM narrative + universal fix suggestions.

## Goals

1. **`backend/src/modules/quality/`** — reusable analysis package (deterministic + optional LLM).
2. **Post-pipeline integration** — auto-run after DOCX export when `NOTES_QUALITY_AUDIT=1`.
3. **CLI script** — `run_notes_quality_audit.py` for standalone runs.
4. **LLM insights** — OpenAI or OpenRouter generates a short narrative + **universal** pipeline/config fix suggestions (never subject-specific legal advice).
5. **Reports** — `.txt`, `.json`, `.md` next to output DOCX.

## Non-goals

- Auto-editing DOCX or re-running rewrite.
- Subject-specific content grading (e.g. "Article 21 incomplete").
- Replacing human legal review.

## Functional requirements

### FR-1 Deterministic audit dimensions

| ID | Dimension | Method |
|----|-----------|--------|
| D1 | Section coverage | Mapped rewrite bodies / total sections |
| D2 | PDF fidelity | Keyword overlap source preview vs notes |
| D3 | Topic sequence | Page-order inversions in hierarchy |
| D4 | Heading naming | Weak/generic/syllabus/too-long/prose flags |
| D5 | Parent-as-subtopic | Chapter title ≈ first section title (similarity ≥ 0.72) |
| D6 | Repetition | Similar headings or note bodies across sections |
| D7 | Syllabus noise | Admin/syllabus phrases inside note bodies |
| D8 | DOCX parity | H1/H2 counts vs markdown |
| D9 | Language simplicity | Heuristic: avg sentence length, long sentences (>28 words) |
| D10 | PDF heading match | Heading appears in PDF page text |
| D11 | Line-by-line content | Per-line scan: meta filler, thin bullets, heading echo, drift, template artifacts |
| D12 | Heading acceptance | AC-01…AC-05, AC-07: structural partition / PDF fragment leaks, display resolver, completeness, thin bodies |

Each dimension: **PASS / OK / WARN** + overall verdict.

### FR-1c Heading acceptance criteria (D12)

`backend/src/modules/quality/heading_acceptance.py` enforces pipeline heading fixes in exported MD/DOCX and display titles:

| ID | Criterion | PASS when |
|----|-----------|-----------|
| AC-01 | No structural partition in export | Zero `CHAPTER I:`, `PART II`, `MODULE N`, `OF OFFENCES…` in `#` / `##` titles |
| AC-02 | No incomplete PDF fragments | Zero currency/BNS tails, page footers, truncated clause ends in export titles |
| AC-03 | No noisy fragments | Zero classification rows, bare markers, prose fragments in export titles |
| AC-04 | Display resolver clean | All `resolve_*_display_heading` outputs classify as `looks_ok` |
| AC-05 | Section coverage | Mapped rewrite bodies ≥ 98% of hierarchy sections |
| AC-07 | No thin bodies | ≤ 3 sections with note body &lt; 120 chars |

Report section **15. HEADING ACCEPTANCE CRITERIA**. Line quality (`line_quality`) is the main content-quality gate. Readability (sentence length) is informational only — not a failure criterion.

### FR-1b Line-by-line audit (D11)

`backend/src/modules/quality/line_audit.py` scans every non-empty line in each section body:

- Meta filler (`This chapter covers…`, `In this section…`)
- Standalone `**bold**` subheading lines
- Thin bullets / orphan one-liners
- Heading echoed in body
- Syllabus/template artifacts per line
- Section-level drift (low keyword overlap vs source preview)
- Bullet-only sections (no prose when book format expected)

Per-section verdict: **PASS / OK / WARN / FAIL** with score. Report section **15. LINE-BY-LINE CONTENT AUDIT**. Disable via `NOTES_QUALITY_LINE_AUDIT=0`; stricter mode via `NOTES_QUALITY_LINE_AUDIT_STRICT=1`.

### FR-2 LLM insights (optional)

- Input: compact JSON summary of deterministic results (no full PDF).
- Output: executive summary + up to 8 **universal** fix suggestions (config, pipeline stage, prompt wording).
- Provider: `LLM_PROVIDER` or `NOTES_QUALITY_LLM_PROVIDER` override.
- Disable via `NOTES_QUALITY_LLM=0`.

### FR-3 Pipeline integration

After successful export in `run_full_openai_pipeline.py`:

```text
output/{book}_{ts}.md
output/{book}_{ts}.docx
output/{book}_{ts}.quality_report.txt
output/{book}_{ts}.quality_report.json
output/{book}_{ts}.quality_insights.md
```

### FR-4 Configuration

| Env | Default | Purpose |
|-----|---------|---------|
| `NOTES_QUALITY_AUDIT` | `1` | Run after pipeline |
| `NOTES_QUALITY_LLM` | `1` | LLM narrative section |
| `NOTES_QUALITY_LLM_PROVIDER` | empty | Override provider |
| `NOTES_QUALITY_OUT_DIR` | empty | Same as output dir |

## Acceptance criteria

- [x] Module importable: `from src.modules.quality import run_quality_audit`
- [x] Pipeline run produces quality reports for Family Law
- [x] Unit tests for new heuristics (parent mirror, simplicity)
- [x] LLM suggestions contain no book-specific legal claims
- [x] `compare_notes_quality.py` remains working via module re-exports
- [x] Heading acceptance AC-01…AC-05, AC-07 audited on every run (export MD/DOCX + display titles)
- [x] Line quality and heading AC affect overall verdict; readability is informational only

## Risks

- OpenRouter free tier rate limits LLM insights — fallback to deterministic-only report.
- PDF text extraction may miss scanned pages — OCR stage quality affects fidelity scores.
