# Code Reference — Ingestion

> **Package:** `backend/src/modules/ingestion/`  
> **Module spec:** [../modules/ingestion.md](../modules/ingestion.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `pdf_extractor.py` | PyMuPDF extract + visual elements | Single PDF entry point |
| `layout_enrichment.py` | Bbox, bold, links on lines | Heading detection uses layout signals |
| `ocr_stage.py` | Scanned page detection + Tesseract | Many legal PDFs are scans |
| `text_normalizer.py` | Raw extract → `NormalizedLine` list | Canonical line model for pipeline |
| `pdf_outline.py` | PDF bookmark/outline supplement | When repeated-TOC detection misses syllabus TOC |
| `profile.py` | `fast_local` / `quality_cloud` / `debug` overrides | Performance vs quality tradeoff |
| `document_profile.py` | Measured document shape → tuning knobs | Subject-agnostic adaptation for structure + rewrite |

---

## `document_profile.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `DocumentCharacterProfile` | Measured signals + derived knobs | Universal per-document tuning | `compute_document_profile` |
| `compute_document_profile(lines, headings)` | Measure density, brevity, prose/clause ratios | No subject keywords | `stage_compute_document_profile` |
| `load_document_profile(run_dir)` | Read `s00_document_profile.json` | Rewrite reuses pipeline profile | `RewriteEngine.run` |
| `resolve_document_profile_settings()` | YAML/env base constants | Deployment tuning | `compute_document_profile` |

---

## `pdf_extractor.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `extract_pdf(pdf_path)` | Full PDF → lines, title, visuals | **Only** call site for extract in pipeline | `stage_extract` |
| `extract_visual_elements(pages)` | Tables, images metadata | Debug + future figure handling | `extract_pdf` |

**Why single extract:** Double `extract_pdf` before pipeline wasted minutes on large PDFs.

---

## `layout_enrichment.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `enrich_layout_from_pymupdf_pages(pages)` | Add geometry/font to lines | Bold/size help heading gate | `extract_pdf` |
| `lines_to_log(lines)` | Serialize for `s01` artifact | Debug visualizer | `stage_layout_log` |
| `log_dict_to_normalized_line(item)` | Rebuild `NormalizedLine` from s01 JSON item | Re-run 15h from saved logs | `load_layout_lines_from_log_dir` |
| `load_layout_lines_from_log_dir(log_dir)` | Load all lines from `s01_layout_lines.json` | Re-export / placement refresh without re-ingest | `reexport_docx.py` |
| `finalize_line_layout_signals(lines)` | Per-page large_font/large_gap/centered | After Docling or PyMuPDF extract | `docling_adapter.py` |

---

## `layout_backends/` — ML layout parsing

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `resolve_layout_backend(pdf_path)` | Pick `pymupdf` or `docling` | Scanned PDFs need ML layout when available | `extract_layout_lines` |
| `extract_layout_lines(pdf_path, ...)` | Route to backend + fallback | Single entry for `extract_pdf` | `pdf_extractor.extract_pdf` |
| `pdf_likely_scanned(pages)` | Low text char count ratio | Auto mode scan detection | `resolve_layout_backend` |
| `extract_lines_docling(pdf_path)` | Docling → NormalizedLine | ML section_header/title labels | `extract_layout_lines` |
| `docling_items_to_normalized_lines(items)` | Map Docling items to lines | Testable adapter | `extract_lines_docling` |

Optional install: `pip install -r requirements-ml-layout.txt` (Docling).

---

## `pymupdf_backend.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `extract_lines_pymupdf(...)` | PyMuPDF dict + OCR + enrich | Legacy signal path + fallback | `extract_layout_lines` |
| `pymupdf_extract_pages_dict(...)` | Raw page dicts | Scan sample + OCR input | `registry`, tests |

---

## `ocr_stage.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `is_scanned_page(page_text)` | Chars < `OCR_MIN_TEXT_CHARS` | Avoid OCR on digital PDFs | `apply_ocr_to_pages` |
| `apply_ocr_to_pages(pages, config)` | Tesseract on scan pages | Recover text from scanned books | `extract_pdf` |
| `split_page_regions(page)` | Two-up left/right crop | Scanned textbooks often two pages per image | OCR path |
| `virtual_page_number(pdf_page, half)` | Virtual page indexing | Fragment page refs stay monotonic | Normalizer |

---

## `text_normalizer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `normalize_text(extract_result)` | Build `list[NormalizedLine]` | Stable `line_id` for entire pipeline | `extract_pdf` |

---

## `pdf_outline.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `extract_pdf_outline(pdf_path)` | Read PDF bookmarks | Syllabus PDFs have usable outline | TOC supplement |
| `supplement_toc_from_pdf_outline(headings, outline)` | Merge outline into TOC detection | When repeat-detection fails | `stage_deterministic_toc` |

---

## `profile.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `ingestion_profile_context(profile)` | Context manager applying overrides | Temporarily set config for upload | `IngestionService` |
| `profile_overrides(profile)` | Dict of config overrides | `fast_local` uses BigBird, skips cloud 15f LLM | Profile switch |
| `upload_skip_rag_default(profile)` | Profile-specific RAG default | Fast upload path | `IngestionService` |

**Profiles (why):**

| Profile | Why |
|---------|-----|
| `fast_local` | Local models, lazy RAG — dev and batch speed |
| `quality_cloud` | Cloud LLM for 15e/15f/15j — best structure quality |
| `debug` | Verbose logs, smaller page limits | Development |
