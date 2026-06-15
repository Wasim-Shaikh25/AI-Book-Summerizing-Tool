"""Tests that STAGES list is built from stage_registry."""

from __future__ import annotations

from src.modules.pipeline.stage_registry import PIPELINE_STAGE_FUNCTIONS, get_pipeline_stages
from src.modules.pipeline.stages import STAGES


def test_stages_built_from_registry() -> None:
    assert len(STAGES) == len(PIPELINE_STAGE_FUNCTIONS)
    assert STAGES == get_pipeline_stages()
    assert STAGES[0].__name__ == "stage_ingest_pdf"
    assert STAGES[-1].__name__ == "stage_build_book_structure"
