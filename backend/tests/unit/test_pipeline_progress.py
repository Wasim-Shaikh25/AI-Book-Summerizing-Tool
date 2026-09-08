"""Tests for pipeline stage progress registry."""

from __future__ import annotations

from src.modules.pipeline.stage_registry import PIPELINE_STAGE_PROGRESS, stage_progress_for


def test_stage_progress_for_semantic_name() -> None:
    row = stage_progress_for("stage_ingest_pdf")
    assert row is not None
    stage_id, message, percent = row
    assert stage_id == "ingest"
    assert percent == 5
    assert "Ingesting" in message


def test_stage_progress_for_legacy_alias() -> None:
    row = stage_progress_for("stage_extract")
    assert row is not None
    stage_id, message, percent = row
    assert stage_id == "ingest"
    assert percent == 5


def test_pipeline_stage_progress_covers_all_stages() -> None:
    names = {row[0] for row in PIPELINE_STAGE_PROGRESS}
    assert "stage_ingest_pdf" in names
    assert "stage_compute_document_profile" in names
    assert "stage_build_book_structure" in names
    percents = [row[2] for row in PIPELINE_STAGE_PROGRESS]
    assert percents == sorted(percents)
