# Module: Export

> **Code package:** `backend/src/modules/export/`  
> **Symbol reference:** [../code-reference/export.md](../code-reference/export.md)  
> **Web policy:** `backend/services/export_policy.py`

---

## 1. Purpose

Format pipeline output for terminal display and Word `.docx` export. Web chat uses smart export policy to decide when to auto-generate Word files.

---

## 2. Public APIs

```python
# backend/src/modules/export/word_exporter.py
class WordExporter:
    def structured_text_to_word(
        self, book_data: dict, output_path: str, *, include_toc: bool = True
    ) -> str: ...

    def assemble_full_book_structured_text(
        self, sections: list[str], title: str
    ) -> dict: ...

# backend/src/modules/export/output_manager.py
class OutputManager:
    def format_for_terminal(self, content: str) -> str: ...
    def export_to_word(self, content, title, output_path) -> str: ...
    def handle_output(self, content, format_type) -> None: ...

# backend/src/modules/export/document_formatter.py
# Cover page, hierarchical TOC with PAGEREF, footer page numbers

# backend/src/modules/export/docx_notes_exporter.py
# Full-book hierarchical DOCX with TOC page numbers (rewrite path)

# backend/src/modules/export/markdown_docx_renderer.py
# Markdown → DOCX rendering helper
```

### File inventory

| File | Role |
|------|------|
| `word_exporter.py` | Primary Word export API (web + CLI) |
| `docx_notes_exporter.py` | Hierarchical full-book export with TOC |
| `document_formatter.py` | Cover, TOC, footer formatting |
| `markdown_docx_renderer.py` | Markdown rendering |
| `output_manager.py` | CLI terminal + Word output routing |

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
1. Cover page
2. Table of Contents (PAGEREF fields)
3. Chapter content (hierarchical headings)
4. Footer page numbers
```

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

See [testing.md](../testing.md) §5.1, §5.10.
