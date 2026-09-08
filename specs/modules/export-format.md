# Universal Document Export Format

**Status:** Implemented  
**Source of truth:** `backend/src/shared/document_format_style.py`  
**Word renderer:** `backend/src/modules/export/docx_theme.py`  
**LLM prompts:** `backend/src/modules/generation/rewrite_prompts.py` (`universal_rewrite_format_addendum`)

Applies to **every export**. LLM rules control **structure only** — length, depth, bullets vs prose follow the **user's request**.

---

## 1. Markdown hierarchy (LLM output)

| Level | Markdown | Word style | Who inserts |
|-------|----------|------------|-------------|
| Chapter | `# Title` | Heading 1 | Exporter |
| Section | `## Title` | Heading 2 | Exporter |
| Subtopic | `### Title` | Heading 3 | LLM (optional) |

### Per-section LLM body rules

- Write section **body only** — export adds the `##` title; do not repeat it.
- **Study mode (`notes_style=study`, default):** mix of `###` subheadings and bullets for key facts; prose for explanations.
- **Book mode (`notes_style=book`):** continuous justified prose paragraphs; bullets **only** for enumerations, examples, or lists explicitly in the source.
- **Length and depth follow the user's instruction** (short summary, detailed notes, etc.).
- Optional `###` subtopics when the source has clear sub-parts.
- No auto template blocks (`Key Points`, `Quick Revision`, …) unless the user asked.
- No standalone `**bold**` fake subheadings unless the user asked for labeled blocks.
- No meta filler (`This chapter covers…`, `In this section we…`) — removed by `notes_body_postprocess.py` if leaked.
- English only; no outline/admin filler.

**Why study mode default:** Structured bullets + `###` subheadings improve revision notes; set `NOTES_EXPORT_STYLE=book` for textbook prose. Line-audit still flags meta filler and pseudo-bullet paragraphs in book mode.

---

## 2. Word typography — book layout (DOCX)

| Element | Font | Size | Weight | Alignment | Spacing |
|---------|------|------|--------|-----------|---------|
| Body | Times New Roman | **11 pt** | Regular | Justified | 1.2 line; 8 pt after |
| First line indent | — | — | — | — | **0.3 in** (default on) |
| Heading 1 (chapter) | Times New Roman | **20 pt** | Bold | Left | 24 pt before / 14 pt after |
| Heading 2 (section) | Times New Roman | **16 pt** | Bold | Left | 16 pt before / 10 pt after |
| Heading 3 (subtopic) | Times New Roman | **13 pt** | Bold | Left | 12 pt before / 6 pt after |
| Cover title | Times New Roman | 26 pt | Bold | Center | — |
| TOC title | Times New Roman | 18 pt | Bold | Center | — |
| Margins | — | — | — | — | 0.9" top, 0.85" bottom, 1.15" left, 1.0" right |

Chapter page breaks, cover, and TOC are handled by the exporter. Color accents (`DOCX_THEME=color`) apply to headings only.

---

## 3. Configuration

See `config/default.yaml` → `export:` and `.env` variables `DOCX_FONT_FAMILY`, `DOCX_*_SIZE_PT`, `DOCX_LINE_SPACING`, `DOCX_FIRST_LINE_INDENT*`.

---

## 4. Re-export script

```powershell
python backend/scripts/export_universal_docx.py output/notes.md
```

---

## 5. Design rationale

- **Book look in Word** — Times New Roman, justified indented paragraphs, prominent chapter headings, chapter page breaks.
- **No LLM length caps** — universal rules define hierarchy and anti-template guardrails only; user instruction controls quality and coverage.
