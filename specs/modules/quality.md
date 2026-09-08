# Module: Notes Quality Audit

> **Code package:** `backend/src/modules/quality/`  
> **Symbol reference:** [../code-reference/quality.md](../code-reference/quality.md)  
> **Agent requirements:** `ai-agent-workflow/requirements-notes-quality.md`  
> **Pipeline hook:** `run_full_openai_pipeline.py` (post-export when `NOTES_QUALITY_AUDIT=1`)

---

## 1. Purpose

Deterministic post-export audit of rewritten notes: coverage, heading quality, line-level content issues, DOCX parity, optional LLM narrative. Does **not** auto-edit notes or re-run rewrite.

---

## 2. Modules

| File | Role |
|------|------|
| `service.py` | `run_quality_audit()` entry point |
| `analyzer.py` | Orchestrates dimensions, builds report sections |
| `heuristics.py` | Heading weakness, parent mirror, repetition, overall verdict |
| `heading_acceptance.py` | AC-01…AC-05, AC-07 on export MD/DOCX + display titles |
| `line_audit.py` | Per-line scan: meta filler, thin bullets, heading echo, drift |
| `llm_insights.py` | Optional narrative + universal fix suggestions |
| `models.py` | Report dataclasses |

---

## 3. Audit dimensions

| ID | Dimension | Verdict weight |
|----|-----------|----------------|
| D1–D9 | Coverage, PDF fidelity, sequence, naming, mirrors, repetition, syllabus, DOCX, PDF match | Mixed |
| D11 | Line-by-line content | **Primary** content gate (`line_quality`) |
| D12 | Heading acceptance (AC) | Structural gate on export titles |

**Sentence length / prose density is no longer audited** (rule removed 2026-06-15): the `readability` dimension, `assess_body_simplicity`, and the report §14 block were deleted. “Simple English” in rewrite prompts means plain understandable language, not short sentences — it is a generation concern, not an audit gate.

---

## 4. Heading acceptance (D12)

`heading_acceptance.py` checks exported `#` / `##` titles and `resolve_*_display_heading` outputs:

| ID | Criterion |
|----|-----------|
| AC-01 | No structural partitions (`CHAPTER I:`, `PART II`, `MODULE N`, …) |
| AC-02 | No PDF fragments (currency tails, page footers, truncated clauses) |
| AC-03 | No noisy fragments (classification rows, bare markers, statute prose) |
| AC-04 | Display resolver outputs classify as `looks_ok` |
| AC-05 | Section coverage ≥ 98% |
| AC-07 | ≤ 3 sections with body &lt; 120 chars |

AC-06 (sentence-length simplicity) **removed** — sentence length is not a quality concern.

Statute prose titles (`Explanation:…`, `Section 309: … —`) are blocked via `is_statute_prose_heading()` in structure pipeline and flagged in AC-03.

---

## 5. Configuration

| Env | Default | Purpose |
|-----|---------|---------|
| `NOTES_QUALITY_AUDIT` | `1` | Run after pipeline export |
| `NOTES_QUALITY_LLM` | `1` | LLM insights section |
| `NOTES_QUALITY_LINE_AUDIT` | `1` | Line-by-line scan |
| `NOTES_QUALITY_LINE_AUDIT_STRICT` | `0` | Stricter line thresholds |
| `NOTES_QUALITY_LLM_PROVIDER` | empty | Override `LLM_PROVIDER` |
| `NOTES_QUALITY_OUT_DIR` | empty | Report output dir |

---

## 6. Output artifacts

Per run (next to DOCX):

```text
output/{book}_{ts}.quality_report.txt
output/{book}_{ts}.quality_report.json
output/{book}_{ts}.quality_insights.md   # when LLM enabled
```

---

## 7. Tests

| Test | Coverage |
|------|----------|
| `test_heading_acceptance.py` | AC rules on synthetic exports |
| `test_notes_body_postprocess.py` | Post-rewrite body cleanup (generation) |

See [testing.md](../testing.md).
