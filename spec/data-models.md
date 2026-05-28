# Data Models — AI Notes Creator Model

> Authoritative entities. Code dataclasses and DB schema must mirror these names (MESO Rule 8).

---

## 1. Pipeline Entities (`src/core/models.py`)

### `NormalizedLine`

One text line after PDF extraction and normalization.

| Field | Type | Notes |
|-------|------|-------|
| line_id | int | Stable line index |
| text | str | Line content |
| page_number | int \| None | Source page |
| y_pos, font_size, x0, x1, y0, y1, x_center | float | Layout |
| is_bold, is_italic, is_upper, is_centered, ... | bool | Typography flags |
| is_noise, noise_type | bool, str | Noise filter output |
| before_context, after_context | str | Context windows |
| source | str | `""`, `"table"`, `"image_ocr"` |

### `HeadingCandidate`

Pre-final heading proposal from candidate scoring.

| Field | Type | Notes |
|-------|------|-------|
| id | str | Candidate identifier |
| text | str | Heading text |
| start_line, end_line | int | Line span |
| confidence | float | Score |
| is_valid, valid_reason | bool, str | Gate output |
| line_id, source_line_id | int \| None | Line linkage |

### `FinalHeading`

Heading after continuity and TOC passes.

| Field | Type | Notes |
|-------|------|-------|
| id | str | Final heading id |
| text | str | Heading text |
| line_id | int | Source line |
| fragment_id | str \| None | Assigned fragment |
| level | int | Hierarchy level |
| is_toc, in_toc_section | bool | TOC flags |
| page_number | int \| None | Page |

### `Fragment`

Text block between headings.

| Field | Type | Notes |
|-------|------|-------|
| id / fragment_id | str | Fragment identifier |
| start_line, end_line | int | Line span |
| assigned_heading_id | str | Primary heading |
| text | str | Fragment body |

### `PipelineResult`

| Field | Type |
|-------|------|
| final_headings | list[FinalHeading] |
| fragments | list[Fragment] |
| heading_to_fragment_id | dict[str, str] |

---

## 2. Domain Layer (`src/domain/document.py`)

Parallel frozen/slots dataclasses — **target** clean layer. Fields mirror pipeline entities; migration in progress.

---

## 3. Storage Schema (`src/storage/schema.py`)

### `BookMetadata` (Pydantic)

Book-level metadata persisted to SQLite.

### `TopicKnowledge` (Pydantic)

Topic/chapter knowledge records linked to books.

---

## 4. Naming Conventions

- Python classes: `PascalCase`
- Fields: `snake_case`
- Heading IDs: string tokens derived from line ids (see `continuity_filter.py`)
- Fragment IDs: `frag_<n>` pattern from `fragments.py`
- Log stages: whitelisted JSON filenames under `logs/run_<utc>/`
