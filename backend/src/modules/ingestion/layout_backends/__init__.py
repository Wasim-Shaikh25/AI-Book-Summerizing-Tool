"""Pluggable PDF layout backends (PyMuPDF signals vs ML layout parsers)."""

from __future__ import annotations

from .registry import (
    docling_available,
    extract_layout_lines,
    resolve_layout_backend,
)

__all__ = [
    "docling_available",
    "extract_layout_lines",
    "resolve_layout_backend",
]
