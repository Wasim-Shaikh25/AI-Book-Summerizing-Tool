# Testing Specification — AI Notes Creator

> **Status:** ACTIVE  
> **Version:** 2.0  
> **Date:** 2026-06-07  
> **Code root:** `backend/tests/`  
> **Runner:** pytest

---

## 1. Purpose

Tests validate the PDF-to-notes engine, web service layer, and export policy. They serve as living documentation of expected behavior and regression guards for future modifications.

---

## 2. Test Structure

```
backend/
├── conftest.py              # Adds backend/ to sys.path
├── pytest.ini               # Markers: integration
└── tests/
    ├── conftest.py          # PDF fixture, tmp cwd isolation
    ├── README.md
    ├── unit/                # Fast, no external LLM calls (representative subset)
    │   ├── test_continuity_and_gate.py
    │   ├── test_docx_toc_export.py
    │   ├── test_export_policy.py
    │   ├── test_heading_cleanup.py
    │   ├── test_heading_acceptance.py
    │   ├── test_enforce_chapter_structure.py
    │   ├── test_notes_body_postprocess.py
    │   ├── test_heading_validator_heuristics.py
    │   ├── test_llm_and_parser.py
    │   ├── test_missing_section_rewrite.py
    │   ├── test_ocr_stage.py
    │   ├── test_parallel_rewrite.py
    │   ├── test_pipeline_stages.py
    │   ├── test_qa_engine.py
    │   ├── test_rag_retriever.py
    │   ├── test_rewrite_validation.py
    │   ├── test_section_bundler.py
    │   ├── test_title_service.py
    │   ├── test_guest_auth.py            # guest mode + auth config
    │   ├── test_llm_cache.py             # rewrite disk cache
    │   ├── test_llm_chat_retry.py        # transient-error retry/backoff
    │   └── test_hierarchy_openai_gate.py # 15j names-pass skip gate
    └── integration/
        ├── test_fragment_coverage.py
        └── test_logging_contract.py
```

---

## 3. Running Tests

```bash
cd backend

# All tests
pytest

# Unit only (fast, ~seconds)
pytest tests/unit

# Integration only (uses bundled PDF, slower)
pytest tests/integration -m integration

# Single file
pytest tests/unit/test_export_policy.py -v

# Single test
pytest tests/unit/test_export_policy.py::test_long_qa_auto_docx -v
```

---

## 4. Fixtures

### Root `conftest.py`

```python
# Adds backend/ directory to sys.path so imports work:
# from services.export_policy import ...
# from src.modules.pipeline import run_pipeline
```

### `tests/conftest.py`

```python
@pytest.fixture
def torts_pdf_path():
    """Bundled test PDF: The Law of Torts 2018 by Jhabwala.pdf"""
    return Path(__file__).parent / "fixtures" / "The Law of Torts 2018 by Jhabwala.pdf"

@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """Run tests in isolated temp directory."""
    monkeypatch.chdir(tmp_path)
```

---

## 5. Unit Tests (Complete Reference)

### 5.1 Export Policy (`test_export_policy.py`)

**Module under test:** `services/export_policy.py`  
**Requirement traceability:** EXP-01 through EXP-04

| Test | Input | Expected | Requirement |
|------|-------|----------|-------------|
| `test_full_rewrite_always_docx` | `rewrite_book` intent | `needs=True, reason="rewrite"` | EXP-01 |
| `test_short_qa_stays_in_chat` | Short Q&A answer | `needs=False, reason="chat_only"` | EXP-02 |
| `test_long_qa_auto_docx` | Answer > 5000 chars | `needs=True, reason="qa_length"` | EXP-03 |
| `test_user_word_request` | "give me word file" | `needs=True, reason="user_request"` | EXP-04 |

```python
def test_full_rewrite_always_docx():
    needs, reason = resolve_export_mode(_rewrite_intent(), answer="x" * 100, user_text="rewrite")
    assert needs is True
    assert reason == "rewrite"

def test_short_qa_stays_in_chat():
    answer = "Short answer about torts."
    needs, reason = resolve_export_mode(_qa_intent(), answer=answer, user_text="explain tort")
    assert needs is False
    assert reason == "chat_only"
```

### 5.2 Title Service (`test_title_service.py`)

**Module under test:** `services/title_service.py`  
**Requirement traceability:** CHAT-05 (auto-generated titles)

| Test | Input | Expected |
|------|-------|----------|
| Title from first message | "Explain negligence in tort law" | "Explain negligence in tort law" |
| Prefix stripping | "Please explain X" | "Explain X" |
| Book fallback | Empty message + book title | Book title |

### 5.3 Command Parser (`test_llm_and_parser.py`)

**Module under test:** `src/modules/interaction/command_parser.py`

| Test | Input | Expected Intent |
|------|-------|-----------------|
| Rewrite detection | "rewrite the full book" | `task_type=rewrite_book, scope=full_book` |
| Q&A detection | "explain negligence" | `task_type=question_answer` |
| Provider alias | Config normalization | Correct provider mapping |

### 5.4 Pipeline Stages (`test_pipeline_stages.py`)

**Module under test:** `src/modules/pipeline/stages.py`, doubted section logic

| Test | Scenario | Expected |
|------|----------|----------|
| Late TOC flagging | TOC on page > 3 | `doubted_sections` populated |
| Metadata stripping | Final headings with TOC rows | TOC/metadata removed from output |

### 5.4b Stage catalog & registry (`test_stage_catalog.py`, `test_pipeline_progress.py`, `test_pipeline_stages_registry.py`)

**Module under test:** `stage_catalog.py`, `stage_registry.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Semantic progress | `stage_progress_for("stage_ingest_pdf")` | ingest / 5% |
| Legacy alias | `stage_progress_for("stage_extract")` | Same as semantic name |
| STAGES order | `get_pipeline_stages()` | 15 functions; includes `stage_compute_document_profile` |
| Structure groups | `STRUCTURE_LOGICAL_GROUPS` | Covers all 10 structure log keys |

### 5.4c Document profile & export coverage (`test_document_profile.py`, `test_export_missing_body_mode.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Clause-dense profile | Many short enumerated lines | Lower overlap + min body chars |
| Prose-heavy profile | Long paragraphs | Higher overlap retained |
| Subject guard | `document_profile.py` source | No domain keywords |
| Placeholder export | Empty rewrite map | Section preserved with page reference |
| Skip / fail modes | `EXPORT_MISSING_BODY_MODE` | Omit or raise |

### 5.4d Rewrite fidelity & mirrors (`test_rewrite_fidelity.py`, `test_chapter_single_section_mirror.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Overlap score | Shared token overlap | High when generated tracks source |
| Regeneration trigger | Unrelated generated text | `needs_regeneration` true below 0.30 |
| Single-section mirror | Chapter == sole section | Subheadings promoted / title repaired |
| PDF title gate | LLM title not in lines | Reverts to local title when strict |

### 5.4d-2 Audit recalibration: semantic grounding & source-grounded titles (`test_line_audit.py`, `test_notes_quality_audit.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Low-grounding source skips overlap | Index-style source + paraphrased body | No `low_source_overlap` / `section_drift` |
| Literal overlap still flags (semantic off) | Unrelated body vs real source | `low_source_overlap` flagged |
| Semantic grounder no-op | `enabled=False` | `ready=False`, `grounded()=False` |
| Title grounded in source | Clean title covered by source | True; unrelated title False |
| pdf_match grounded title | Clean title absent from PDF, covered by source | status `grounded_in_source` (not a failure) |
| pdf_match ungrounded title | Clean title absent from PDF and source | status `not_in_pdf` |

### 5.4d-1 Text grounding & contents-region detection (`test_text_grounding.py`, `test_contents_region.py`)

**Modules under test:** `src/shared/text_grounding.py`, `src/modules/structure/contents_region.py`, partition gate in `book_assembler.build_ultimate_sections`.

| Test | Scenario | Expected |
|------|----------|----------|
| Enumerated-line match | `65. Title`, `(7) Title`, prose | True for index rows, False for prose |
| Real content chars | Mixed index + prose | Counts only prose letters |
| `is_low_grounding` | Enum list / thin prose / real section | True / True / False |
| `is_contents_listing` | Short real (40–160 chars) | Kept (False) — stricter partition floor |
| Contents-region detect | Enumeration-dominated page | All non-noise line ids flagged; noise excluded |
| Contents-region detect | Prose page / short page | No region |
| Partition grounding gate | Section body = index list | Section dropped; `meta.low_grounding_dropped ≥ 1` |

### 5.4e Post-rewrite structural fixer (`test_notes_structure_fix.py`)

**Module under test:** `src/modules/generation/notes_structure_fix.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Parse/render round-trip | Sample MD | Chapters/sections/bodies preserved |
| Offline heading repair | Noisy prose section title | Replaced with `looks_ok` title; clean titles untouched |
| LLM heading repair | Mocked batched chat | Title from JSON map applied (detail `section/llm`) |
| Chapter title repair | Noisy `#` chapter | Repaired from section context |
| TOC regeneration | Repaired heading | TOC reflects new title |
| Low-grounding | Index-style source | Flagged; dropped only with `drop=True`; skipped without source |
| Duplicate merge | Adjacent identical bodies | Flagged; merged only with `apply_merge=True` |

### 5.4f Structure-fix runner + title sync (`test_structure_fix_runner.py`)

**Module under test:** `src/modules/generation/structure_fix_runner.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Enabled/engine defaults | No env | `structure_fix_enabled()` true; engine `hybrid` |
| Offline list renumber | Per-topic ordered lists | Restart at 1 each section |
| Propagate in-memory | Noisy hierarchy + clean MD | Section (by sid) + chapter (by vote) headings replaced |
| Propagate on-disk | Hierarchy artifact file | Artifact rewritten with clean titles |
| Chapter sid-vote | Reordered sections | Correct chapter title by majority sid vote |
| No-match no-op | Unrelated sids | 0 updates; titles untouched |

### 5.4g Hierarchy loader (`test_toc_sections.py`)

**Module under test:** `src/modules/generation/toc_sections.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Wrapped schema | `{items:{chapters}}` (s15f) | Loads inner hierarchy |
| Top-level schema | `{chapters,...}` (s15j) | Loads directly |
| Both present | `items` + top-level | Prefers `items` |
| Non-hierarchy | List payload | Raises `ValueError` |

### 5.5 OCR Stage (`test_ocr_stage.py`)

**Module under test:** `src/modules/ingestion/ocr_stage.py`  
**Requirement traceability:** `requirements-ocr-stage.md`

| Test | Scenario | Expected |
|------|----------|----------|
| Scanned page detection | Page with < 40 chars text | Flagged for OCR |
| Two-up split | `OCR_SPLIT_TWO_UP=true` | Left/right regions created |
| Virtual page numbers | Two-up page 1 | Left=1, Right=2 |

### 5.6 RAG Retriever (`test_rag_retriever.py`)

**Module under test:** `src/modules/rag/retriever.py`

| Test | Scenario | Expected |
|------|----------|----------|
| One chunk per section | `RAG_CHUNK_SIZE_WORDS=0` | Single chunk per section |
| Hybrid semantic preference | Vector + lexical fusion | Semantic match ranked higher |

### 5.7 QA Engine (`test_qa_engine.py`)

**Module under test:** `src/modules/generation/qa_engine.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Lexical retrieval | Question about heading text | Heading section preferred |

### 5.8 Heading Cleanup (`test_heading_cleanup.py`)

**Module under test:** Stage 15f heading cleanup

| Test | Scenario | Expected |
|------|----------|----------|
| Art-only cleanup | Heading "Art. 5" only | Cleaned or flagged |
| Number prefix strip | "1. Introduction" | Prefix removed |
| Chapter dedup | Duplicate chapter titles | Deduplicated |

### 5.9 Parallel Rewrite (`test_parallel_rewrite.py`)

**Module under test:** `src/modules/generation/parallel_rewrite.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Job overlap context | Adjacent sections | Context overlap included |
| Section ID preservation | Parallel rewrite | IDs unchanged in output |

### 5.10 DOCX TOC Export (`test_docx_toc_export.py`)

**Module under test:** `src/modules/export/word_exporter.py`

| Test | Scenario | Expected |
|------|----------|----------|
| TOC before chapters | Export plan build | TOC block precedes body |

### 5.11 Section Bundler (`test_section_bundler.py`)

**Module under test:** Rewrite section bundling

| Test | Scenario | Expected |
|------|----------|----------|
| Bundle grouping | Multiple small sections | Grouped by size limit |
| SID tag parsing | Section ID tags in text | Correctly parsed |
| Chapter page breaks | `REWRITE_CHAPTER_PAGE_BREAKS=1` | Page break per chapter |

### 5.12 Rewrite Validation (`test_rewrite_validation.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Heading normalization | Various heading formats | Normalized consistently |
| Similarity check | Near-duplicate headings | Detected |
| Coverage validation | Missing sections | Flagged |

### 5.13 Missing Section Rewrite (`test_missing_section_rewrite.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Auto-retry | Missing section in rewrite output | Filled on retry |

### 5.14 Continuity & Gate (`test_continuity_and_gate.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Line ID parsing | Heading ID format | Correct line_id extracted |
| Heading heuristics | Enumeration patterns | Invalid headings blocked |

### 5.15 Heading Validator Heuristics (`test_heading_validator_heuristics.py`)

| Test | Scenario | Expected |
|------|----------|----------|
| Section number blocking | "1.2.3 Item" | Blocked as heading |
| Enumeration blocking | "a) First item" | Blocked as heading |

### 5.16 Enforce Chapter Structure (`test_enforce_chapter_structure.py`)

**Module under test:** `chapter_placement.enforce_chapter_structure`

| Test | Scenario | Expected |
|------|----------|----------|
| Mega-chapter split | 22 sections in one chapter | ≥ 2 chapters after enforce |
| Parent mirror | Chapter title = first section | Mirror fixed or chapter retitled |
| Statute prose | `Explanation:` / `Section N: … —` titles | Repaired or demoted |

### 5.17 Heading Acceptance (`test_heading_acceptance.py`)

**Module under test:** `quality/heading_acceptance.py`

| Test | Scenario | Expected |
|------|----------|----------|
| AC-01 partition leak | `CHAPTER I:` in export `##` | FAIL |
| AC-03 statute prose | `Explanation:` as section title | FAIL |
| Clean export | Valid study titles only | PASS |

### 5.18 Notes Body Postprocess (`test_notes_body_postprocess.py`)

**Module under test:** `generation/notes_body_postprocess.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Meta filler strip | "This chapter covers…" | Removed |
| Heading echo | Body repeats section title | Echo removed |
| Thin bullets | Orphan one-liner bullets | Stripped |
| Never empty real content | All bullets thin but body real | Original kept (robustness guard) |

### 5.19 Guest Auth (`test_guest_auth.py`)

**Module under test:** `auth/config.py`, `api/routes/auth.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Config exposes flag | `GET /api/auth/config` | Includes `allow_guest` |
| Guest token issued | `AUTH_ENABLED=true`, `ALLOW_GUEST=true` | `{user, token}` with JWT |
| Guest blocked | `ALLOW_GUEST=false` | 403 |
| No token when auth off | `AUTH_ENABLED=false` | `{user, token: null}` (shared dev identity) |

### 5.20 LLM Rewrite Cache (`test_llm_cache.py`)

**Module under test:** `shared/llm_cache.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Cache hit | Identical prompt twice | Second call skips LLM |
| Key sensitivity | Different prompt/model/max_tokens | New cache key |
| Disable flag | `REWRITE_CACHE_ENABLED=0` | Cache bypassed |

### 5.21 LLM Chat Retry (`test_llm_chat_retry.py`)

**Module under test:** `pipeline/llm_chat_client.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Transient retry | 429 then 200 | Succeeds after backoff |
| Client error | 400 | No retry; falls through to model fallback |

### 5.22 Hierarchy OpenAI Gate (`test_hierarchy_openai_gate.py`)

**Module under test:** `structure/final_structuring/hierarchy_openai_refinement.py`

| Test | Scenario | Expected |
|------|----------|----------|
| Clean titles | All hierarchy titles already clean | Cloud names pass skipped (cost saved) |
| Prose/partition title | Statute-prose or partition heading present | Cloud names pass runs |
| Generic title | "Section topic (p.N)" style | Cloud names pass runs |

---

## 6. Integration Tests

### 6.1 Logging Contract (`test_logging_contract.py`)

**Marker:** `@pytest.mark.integration`  
**Uses:** Bundled Torts PDF  
**Validates:** Pipeline writes expected stage JSON files

| Check | Expected Artifacts |
|-------|-------------------|
| Stage files exist | `s01_layout_lines.json` through `s16_rag_snapshot.json` (see `stage_registry.py`) |
| Envelope schema | Each file has `stage`, `timestamp`, `items` or `payload` |
| Item shape | Spot-check heading/fragment fields |

**Expected stage files:**

```
s01_layout_lines.json … s12_doubted_sections.json
s15a_heading_hierarchy.json
s15b_doubted_resolved.json (if late TOC)
s15c_final_book.json
s15d_ultimate_sections.json
s15e_chapter_hierarchy.json
s15f_heading_cleanup.json
s15h_chapter_placement.json
s15i_heading_refinement.json
s15j_hierarchy_openai.json
s15g_title_validation.json
s16_rag_snapshot.json
```

### 6.2 Fragment Coverage (`test_fragment_coverage.py`)

**Marker:** `@pytest.mark.integration`  
**Validates:** No missing fragment mappings; DB counts match pipeline

| Check | Expected |
|-------|----------|
| Fragment count | Every heading has fragment mapping |
| DB persistence | `persist_to_db=True` counts match |
| Nonempty artifacts | Key JSON files have items |

---

## 7. Acceptance Test Matrix (Web Platform)

Maps to `requirements-web-platform.md` §9:

| # | Acceptance Criterion | Test Coverage | Manual Test |
|---|---------------------|---------------|-------------|
| 1 | Google login works | — | OAuth flow in browser |
| 2 | PDF upload → chat | `test_logging_contract` (engine) | Upload in UI |
| 3 | Full rewrite → docx | `test_full_rewrite_always_docx` | "Rewrite full book" in chat |
| 4 | Short Q&A → text only | `test_short_qa_stays_in_chat` | "Explain X" short answer |
| 5 | Long Q&A → auto docx | `test_long_qa_auto_docx` | Long explain question |
| 6 | "Give me word file" → docx | `test_user_word_request` | Explicit request in chat |
| 7 | Conversations persist | — | Refresh browser, check sidebar |
| 8 | CLI still works | — | `python main.py` |

---

## 8. Test Data

| Asset | Path | Purpose |
|-------|------|---------|
| Torts PDF | `tests/fixtures/The Law of Torts 2018 by Jhabwala.pdf` | Integration tests |
| Sample logs | `{PROJECT_ROOT}/logs/run_*/` | Reference artifacts (not test fixtures) |

---

## 9. CI Recommendations

```yaml
# Suggested CI pipeline
steps:
  - name: Unit tests
    run: cd backend && pytest tests/unit -v

  - name: Integration tests
    run: cd backend && pytest tests/integration -m integration -v
    # Requires: bundled PDF, no external LLM API keys
```

**Notes:**
- Integration tests do NOT call external LLM APIs for deterministic stages
- LLM-dependent stages (15b, rewrite) may be skipped or mocked in CI
- Web API endpoints have no dedicated test suite yet (gap — see §10)

---

## 10. Known Gaps

| Gap | Priority | Suggested Test |
|-----|----------|----------------|
| Partial API route tests | Medium | Auth/guest covered (`test_guest_auth.py`); add `test_chat.py`, `test_books.py` with TestClient |
| No frontend tests | Medium | Vitest + React Testing Library (guest button, `downloadFile`) |
| No E2E browser tests | Low | Playwright for upload → chat → download |
| Upload job persistence | Medium | Test job survives... (currently in-memory only) |

### Adding API Route Tests (Recommended Pattern)

```python
# tests/api/test_export_policy_integration.py
from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_guest_login_when_auth_disabled(client, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    res = client.post("/api/auth/guest")
    assert res.status_code == 200
    assert "user_id" in res.json()
```

---

## 11. Modification Guide (Testing)

When changing code:

1. **Update spec first** if behavior changes (`specs/testing.md`, module spec)
2. **Add/update unit test** for every new function or changed logic
3. **Run `pytest tests/unit`** before committing
4. **Run integration tests** if pipeline stages change
5. **Map tests to requirements** using traceability tables above

### Test Naming Convention

```
test_{what}_{scenario}_{expected}
# Examples:
test_full_rewrite_always_docx
test_short_qa_stays_in_chat
test_late_toc_flags_doubted_sections
```

### Adding a New Unit Test

```python
# tests/unit/test_my_feature.py
"""Tests for my_feature module."""

from services.my_feature import my_function

def test_my_function_happy_path():
    result = my_function("input")
    assert result == "expected"

def test_my_function_edge_case():
    result = my_function("")
    assert result is None
```
