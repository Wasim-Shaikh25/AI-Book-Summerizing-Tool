# Code Reference — Export

> **Package:** `backend/src/modules/export/`  
> **Module spec:** [../modules/export.md](../modules/export.md) · [../modules/export-format.md](../modules/export-format.md)

---

## Files

| File | Purpose | Why |
|------|---------|-----|
| `document_formatter.py` | Assemble full notes markdown from hierarchy + bodies | Separates structure from LLM body text |
| `docx_notes_exporter.py` | Hierarchical DOCX with TOC/bookmarks | Primary rewrite export path |
| `markdown_docx_renderer.py` | Generic MD → DOCX | Re-export from markdown file |
| `note_body_docx.py` | Render note body MD into DOCX paragraphs | Body rules separate from cover/TOC |
| `docx_theme.py` | Fonts, heading styles, cover, footers | Book layout (Times New Roman, justified) |
| `docx_theme_palettes.py` | Color theme palettes | `DOCX_THEME=color` accents |
| `mermaid_renderer.py` | Mermaid diagrams → PNG in DOCX | Optional diagrams in notes |
| `word_exporter.py` | Legacy Word export wrapper | Web chat shorter exports |
| `output_manager.py` | CLI terminal + Word routing | `main.py` output modes |

---

## `document_formatter.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `assemble_notes_document(hierarchy, rewritten_map, meta)` | Full MD document string | Single markdown artifact for pipeline | `RewriteEngine`, reexport |
| `chapter_blocks_from_hierarchy(hierarchy, map)` | Chapter-grouped blocks | Chapter page breaks in export | Assembler |
| `resolve_export_missing_body_mode()` | Read `EXPORT_MISSING_BODY_MODE` | Placeholder vs fail vs skip | `chapter_blocks_from_hierarchy` |
| `_resolve_section_body(...)` | Body, preview, or placeholder | Preserves section count in export | `chapter_blocks_from_hierarchy` |
| `_section_id_tag(section_id)` | `<!-- sid:SXX -->` HTML comment suffix | Deterministic audit/re-export join when display title ≠ hierarchy heading | `chapter_blocks_from_hierarchy` |
| `format_chapter_block(chapter, sections, map)` | One chapter MD block | `#` chapter + `##` sections | Assembler |
| `build_toc_section(entries)` | Markdown TOC | Optional MD TOC | Assembler |
| `build_cover_page(meta)` | Title page MD | Book metadata on cover; **Book / Generated / Chapters only** (no Source PDF, Sections, Notes style) | Assembler |
| `humanize_book_title(raw)` | PDF stem → readable title | Slug cleanup for cover | `resolve_export_book_title` |
| `resolve_export_book_title(...)` | Cover/book title from hierarchy, sidecar PDF, log artifacts, or MD stem | **Never use wrong DB row** (`ORDER BY processed_at`) | `run_full_openai_pipeline.py`, `reexport_docx.py` |
| `cover_from_hierarchy_meta(title, hierarchy)` | `BookCoverMeta` dataclass | DOCX + MD cover fields; `source_pdf` / `user_instruction` / `section_count` kept on dataclass but **not rendered on cover** | Pipeline, reexport |

**`BookCoverMeta`:** `title`, `subtitle`, `generated_at`, `chapter_count`, `topic_count` are exported. `source_pdf`, `user_instruction`, `section_count` are legacy fields omitted from cover by design (2026-06-15).
| `toc_entries_from_hierarchy(hierarchy)` | TOC row list | Page ref generation in DOCX | `DocxNotesExporter` |
| `rebuild_notes_markdown(md_path, map)` | Patch bodies into existing MD | Sidecar rebuild scripts | `build_rewritten_sidecar.py` |

---

## `docx_notes_exporter.py` — `DocxNotesExporter`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `export(hierarchy, rewritten_map, out_path, ...)` | Full book DOCX | TOC page numbers require two-pass build | `RewriteEngine` |
| `_add_cover_page(doc, cover)` | Word cover: title, subtitle, metadata table | **Fields: Book, Generated, Chapters only** (no Source PDF, Sections, Notes style) | `export` |
| `parse_markdown_sections(md)` | Split MD into section bodies | Returns `(by_heading, by_sid)` when sid tags present | Reexport, audit |
| `rewritten_map_from_section_bodies(sections)` | Bodies dict from parsed MD | Heading fallback when no sid tags | `reexport_docx.py` |
| `resolve_rewritten_map(log_dir, md_path)` | Load map from sidecar or MD | **Prefers `by_sid` from `<!-- sid:SXX -->` tags** | Quality audit, scripts |

**Why two-pass DOCX:** Word TOC PAGEREF fields need final pagination after content inserted.

---

## `docx_theme.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `apply_study_notes_theme(doc, theme)` | Base styles | Consistent book look | Exporter |
| `style_chapter_heading(p, theme)` | H1 20pt bold | Chapter prominence | Renderer |
| `style_section_heading(p, theme)` | H2 16pt bold | Section hierarchy | Renderer |
| `style_body_paragraph(p, theme)` | 11pt justified + indent | Book prose layout | `note_body_docx` |
| `add_page_number_footer(section)` | Footer page numbers | Print-ready notes | Exporter |
| `finalize_word_document(doc)` | Refresh fields | TOC page numbers update | Exporter end |

---

## `note_body_docx.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `append_note_body_markdown(doc, body, theme)` | Body MD → DOCX paragraphs | Justified prose, real bullet lists only | `DocxNotesExporter` |

---

## `markdown_docx_renderer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `render_markdown_to_document(doc, md, theme)` | Full MD render | Script re-export | `export_universal_docx.py` |
| `export_markdown_file_to_docx(md_path, out_path)` | File convenience | CLI one-liner | Scripts |

---

## `mermaid_renderer.py`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `iter_markdown_segments(md)` | Split MD vs mermaid fences | Diagrams optional per section | Body renderer |
| `render_mermaid_to_png(code, out_dir)` | Mermaid CLI → PNG | DOCX embeds images | When `user_requests_diagrams` |
| `add_mermaid_to_document(doc, png_path, ...)` | Insert image with sizing | Fit printable page width | Exporter |

---

## `word_exporter.py` — `WordExporter`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `structured_text_to_word(book_data, path)` | Legacy structured export | Web Q&A shorter exports | `ChatService` |
| `export_markdown_to_word(md, path)` | Simple MD → DOCX | Quick export | `OutputManager` |

---

## `output_manager.py` — `OutputManager`

| Symbol | Purpose | Why | Called by |
|--------|---------|-----|-----------|
| `handle_output(content, format_type)` | CLI print or Word | `main.py` user choice | CLI |
| `format_for_terminal(content)` | Terminal-safe formatting | CLI display | CLI |
