"""Notes export layout — study (bullets) vs book (prose chapters)."""

from __future__ import annotations

import os

from src.shared import config


def resolve_notes_export_style(name: str | None = None) -> str:
    raw = (name or os.environ.get("NOTES_EXPORT_STYLE") or getattr(config, "NOTES_EXPORT_STYLE", "study") or "study")
    style = str(raw).strip().lower()
    if style in {"book", "textbook", "prose"}:
        return "book"
    return "study"


def is_book_export_style() -> bool:
    return resolve_notes_export_style() == "book"


def default_cover_subtitle() -> str:
    return "Textbook Notes" if is_book_export_style() else "Study Notes"
