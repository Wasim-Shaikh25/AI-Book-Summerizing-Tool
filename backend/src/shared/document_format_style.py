"""Universal document format — single source of truth for LLM markdown + Word export.

Applies to every rewrite regardless of intent, subject, or NOTES_EXPORT_STYLE.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.shared import config as _config


@dataclass(frozen=True, slots=True)
class DocumentTypography:
    """Word / print typography — Times New Roman book layout."""

    body_font: str = "Times New Roman"
    heading_font: str = "Times New Roman"
    body_size_pt: int = 11
    h1_size_pt: int = 20
    h2_size_pt: int = 16
    h3_size_pt: int = 13
    cover_title_size_pt: int = 26
    cover_subtitle_size_pt: int = 14
    toc_title_size_pt: int = 18
    line_spacing: float = 1.2
    first_line_indent_inches: float = 0.3
    space_after_body_pt: int = 8
    h1_space_before_pt: int = 24
    h1_space_after_pt: int = 14
    h2_space_before_pt: int = 16
    h2_space_after_pt: int = 10
    h3_space_before_pt: int = 12
    h3_space_after_pt: int = 6
    margin_top_inches: float = 0.9
    margin_bottom_inches: float = 0.85
    margin_left_inches: float = 1.15
    margin_right_inches: float = 1.0


def resolve_body_font() -> str:
    raw = (
        os.environ.get("DOCX_FONT_FAMILY")
        or os.environ.get("DOCX_BODY_FONT")
        or getattr(_config, "DOCX_FONT_FAMILY", "")
        or "Times New Roman"
    )
    return str(raw).strip() or "Times New Roman"


def resolve_heading_font() -> str:
    raw = (
        os.environ.get("DOCX_HEADING_FONT")
        or os.environ.get("DOCX_FONT_FAMILY")
        or getattr(_config, "DOCX_HEADING_FONT", "")
        or resolve_body_font()
    )
    return str(raw).strip() or resolve_body_font()


def resolve_typography() -> DocumentTypography:
    """Load typography from env overrides (pt sizes as integers)."""

    def _pt(key: str, yaml_key: str, default: int) -> int:
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return int(float(raw))
            except ValueError:
                pass
        cfg_val = getattr(_config, key, None)
        if cfg_val is not None and str(cfg_val).strip():
            try:
                return int(float(str(cfg_val)))
            except ValueError:
                pass
        try:
            from src.shared.config import _cfg_get, _YAML  # type: ignore[attr-defined]

            yv = _cfg_get(_YAML, "export", yaml_key, default=default)
            return int(float(yv))
        except Exception:
            return default

    def _float(key: str, yaml_key: str, default: float) -> float:
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        try:
            from src.shared.config import _cfg_get, _YAML  # type: ignore[attr-defined]

            return float(_cfg_get(_YAML, "export", yaml_key, default=default))
        except Exception:
            return default

    return DocumentTypography(
        body_font=resolve_body_font(),
        heading_font=resolve_heading_font(),
        body_size_pt=_pt("DOCX_BODY_SIZE_PT", "body_size_pt", 11),
        h1_size_pt=_pt("DOCX_H1_SIZE_PT", "h1_size_pt", 20),
        h2_size_pt=_pt("DOCX_H2_SIZE_PT", "h2_size_pt", 16),
        h3_size_pt=_pt("DOCX_H3_SIZE_PT", "h3_size_pt", 13),
        line_spacing=_float("DOCX_LINE_SPACING", "line_spacing", 1.2),
        first_line_indent_inches=_float("DOCX_FIRST_LINE_INDENT_IN", "first_line_indent_inches", 0.3),
    )


def universal_markdown_hierarchy() -> str:
    """How assembled notes map to Word heading levels."""
    return """\
Document hierarchy (export adds headings — follow this in section bodies):
  #   H1 — Chapter title (one per chapter; exporter inserts)
  ##  H2 — Section title (exporter inserts from pipeline)
  ### H3 — Optional subtopic inside a section (only when the source has clear sub-parts)

Per-section LLM output (body only — do NOT repeat the section title as first line):
  - Write the section body in the format and depth the user requested (short, detailed, bullets, etc.)
  - Optional ### subtopic headings when the source has distinct sub-parts
  - No # or ## in section body (chapter/section titles are added by export)
"""


def universal_prose_rules() -> str:
    return """\
Layout rules (export only — do NOT limit coverage, length, or sentence count):
  - Word export uses Times New Roman 11pt, justified prose with first-line indent
  - "Simple English" = plain words a beginner can understand — NOT short sentences or omitted detail
  - Write continuous paragraphs for explanations; do not chop every sentence into its own line
  - Use bullets or numbered lists ONLY for examples, steps, case lists, or 3+ parallel items — not for whole sections
  - Do NOT add "Key Points", "Quick Revision", "Definition", or similar template blocks unless the user explicitly requested them
  - Do NOT repeat the section title as the first sentence or standalone line
  - Do NOT use standalone **bold** lines as fake subheadings unless the user asked for labeled blocks
  - No syllabus/admin filler (course outcomes, instructional hours, module labels, "This chapter covers…")
  - English only; stay faithful to the provided source text
"""


def universal_rewrite_format_addendum() -> str:
    """Appended to every rewrite system prompt — structure only, not content length."""
    return (
        "\nUNIVERSAL OUTPUT FORMAT (structure only — user request controls length and depth):\n"
        + universal_markdown_hierarchy()
        + "\n"
        + universal_prose_rules()
        + "\nExported book style: Times New Roman 11pt body, justified with first-line indent; "
        "chapter/section/subtopic headings 20pt / 16pt / 13pt.\n"
    )


def format_spec_summary() -> str:
    """Human-readable spec for docs and debugging."""
    t = resolve_typography()
    return (
        f"Font: {t.body_font} {t.body_size_pt}pt body; "
        f"headings {t.h1_size_pt}/{t.h2_size_pt}/{t.h3_size_pt}pt; "
        f"line spacing {t.line_spacing}; "
        f"first-line indent {t.first_line_indent_inches}in"
    )
