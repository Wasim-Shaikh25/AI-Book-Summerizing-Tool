# Module: Export

> **Code package:** `backend/src/modules/export/`  
> **Symbol reference:** [../code-reference/export.md](../code-reference/export.md)  
> **Web policy:** `backend/services/export_policy.py`

---

## 1. Purpose

Format pipeline output for terminal display and Word `.docx` export. Web chat uses smart export policy to decide when to auto-generate Word files.

---

## 2. Public APIs

### Full-book primary path (CLI pipeline / `run_full_openai_pipeline.py`)

```python
# backend/src/modules/export/docx_notes_exporter.py
class DocxNotesExporter:
    def export(self, hierarchy: dict, rewritten: dict, *, output_path: str) -> str: ...
    # Orchestrates: cover → TOC → chapter bodies via note_body_docx + markdown_docx_renderer

# backend/src/modules/export/document_formatter.py
def chapter_blocks_from_hierarchy(hierarchy, rewritten_map, *, missing_body_mode) -> list[dict]: ...
def resolve_export_book_title(hierarchy, *, log_dir, pdf_path) -> str: ...
# Cover page (Book / Generated / Chapters), hierarchical TOC with PAGEREF

# backend/src/modules/export/note_body_docx.py
# Renders each section body: ordered-list restart per section (NumberedListTracker),
# heading-level mapping (##/###), inline bold/italic via docx_theme

# backend/src/modules/export/markdown_docx_renderer.py
def export_markdown_file_to_docx(md_path: str, output_path: str) -> str: ...
# Markdown → DOCX rendering (also used by signal_export/pdf_mirror_docx.py)

# backend/src/modules/export/docx_theme.py
# Style helpers: restart_numbered_paragraph (no-op — list restart is done at MD level),
# apply_heading_style, NumberedListTracker
```

### Web-chat secondary path (single-section, short answers)

```python
# backend/src/modules/export/word_exporter.py
class WordExporter:
    def structured_text_to_word(
        self, book_data: dict, output_path: str, *, include_toc: bool = True
    ) -> str: ...
    def assemble_full_book_structured_text(self, sections: list[str], title: str) -> dict: ...
```

### CLI terminal routing

```python
# backend/src/modules/export/output_manager.py
class OutputManager:
    def format_for_terminal(self, content: str) -> str: ...
    def export_to_word(self, content, title, output_path) -> str: ...
    def handle_output(self, content, format_type) -> None: ...
```

### File inventory

| File | Role | Path |
|------|------|------|
| `docx_notes_exporter.py` | **Full-book primary** — hierarchical DOCX with TOC | Full-book pipeline |
| `document_formatter.py` | Cover page, TOC (PAGEREF), `resolve_export_book_title` | Full-book pipeline |
| `note_body_docx.py` | Section body rendering, numbered-list restart per section | Full-book pipeline |
| `markdown_docx_renderer.py` | Markdown → DOCX (shared: full-book + signal V2) | Both pipelines |
| `docx_theme.py` | Style helpers, heading styles, `NumberedListTracker` | Full-book pipeline |
| `docx_theme_palettes.py` | Color/font palette definitions | Full-book pipeline |
| `word_exporter.py` | **Web-chat secondary** — single-section Word export | Web chat |
| `output_manager.py` | CLI terminal + Word output routing | CLI |
| `mermaid_renderer.py` | Mermaid diagram rendering (optional) | Debug/docs |
| `signal_export/pdf_mirror_docx.py` | Signal-sections V2 DOCX via `markdown_docx_renderer` | Signal pipeline |

---

## 3. Export Policy (Web)

```python
# backend/services/export_policy.py
REWRITE_TASKS = {"rewrite_book", "summarize_book", "study_notes", "revision_notes"}

def resolve_export_mode(intent, *, answer, user_text) -> tuple[bool, str]:
    # Returns (needs_docx, reason)
    # reason: "rewrite" | "qa_length" | "user_request" | "chat_only"
```

| Trigger | Condition | Result |
|---------|-----------|--------|
| Full rewrite | `task_type in REWRITE_TASKS` | Always `.docx` |
| Long Q&A | `len(answer) > CHAT_DOCX_CHAR_LIMIT` | Auto `.docx` |
| User request | "give me word file" pattern | `.docx` |
| Short Q&A | Default | Chat only |

Requirement IDs: [requirements-web-platform.md](../requirements-web-platform.md) §2.4 (EXP-*)

---

## 3b. Missing rewrite body (`EXPORT_MISSING_BODY_MODE`)

`chapter_blocks_from_hierarchy` no longer silently drops sections when rewrite body and fragment preview are empty.

| Mode | Behaviour |
|------|-----------|
| `placeholder` (default) | Emit one-line placeholder referencing source page |
| `fail` | Raise `ValueError` — caller handles retry |
| `skip` | Legacy behaviour — omit section from export |

Symbols: `resolve_export_missing_body_mode`, `_resolve_section_body` in `document_formatter.py`.

---

## 4. DOCX Structure

Build order (fixes TOC page numbers — see change-log 2026-05-31):

```
1. Cover page (Book, Generated, Chapters — no Source PDF / Sections / Notes style)
2. Table of Contents (PAGEREF fields)
3. Chapter content (hierarchical headings)
4. Footer page numbers
```

Cover title comes from `resolve_export_book_title()` (hierarchy → sidecar PDF → log artifacts → MD stem), not `ORDER BY processed_at DESC` from DB.

**Windows:** `pywin32` for Word COM field refresh (auto TOC pagination).

---

## 5. File Paths

| Type | Path Pattern |
|------|--------------|
| CLI export | `output/{title}.docx` |
| Web export | `output/exports/{user_id}/{title}.docx` |
| Reference template | `reference.docx` at project root |

---

## 6. Dependencies

- `python-docx` for document assembly
- `reference.docx` template (`REFERENCE_DOCX_PATH` in config)
- Optional Pandoc for alternative export paths
- Optional `pywin32` on Windows for TOC field refresh

---

## 7. Tests

| Test | Coverage |
|------|----------|
| `test_export_policy.py` | All export decision rules |
| `test_docx_toc_export.py` | TOC built before chapters |
| `test_note_body_docx.py` | Numbered-list restart per section, heading-level mapping |
| `test_export_cover.py` | `resolve_export_book_title` per-book resolution, simplified cover fields |
| `test_export_missing_body_mode.py` | `placeholder` / `fail` / `skip` modes |

See [testing.md](../testing.md) §5.1, §5.10.
