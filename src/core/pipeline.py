"""Backward-compatible pipeline shim. Prefer: from src.modules.pipeline import run_pipeline."""

from src.modules.pipeline.runner import run_pipeline

__all__ = ["run_pipeline"]
