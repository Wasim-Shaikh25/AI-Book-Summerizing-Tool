"""
Single import path for the book structure pipeline (same behavior as src.core.pipeline).

Use: ``from src.book_pipeline import run_pipeline``
"""

from src.modules.pipeline import run_pipeline

__all__ = ["run_pipeline"]
