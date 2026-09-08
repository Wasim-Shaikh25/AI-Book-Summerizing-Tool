"""Tests for PROJECT_ROOT path helpers."""

from __future__ import annotations

from pathlib import Path

from src.shared.config import BASE_DIR
from src.shared.paths import resolve_project_path, to_project_relative_path


def test_to_project_relative_path() -> None:
    root = Path(BASE_DIR)
    rel = to_project_relative_path(root / "output" / "uploads" / "u1" / "book.pdf")
    assert rel == "output/uploads/u1/book.pdf"


def test_resolve_project_path_relative() -> None:
    root = Path(BASE_DIR)
    target = root / "output"
    target.mkdir(parents=True, exist_ok=True)
    resolved = resolve_project_path("output")
    assert resolved == target.resolve()
