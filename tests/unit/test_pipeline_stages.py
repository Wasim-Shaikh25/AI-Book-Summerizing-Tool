"""Unit tests for plugin pipeline stages (no PDF)."""

from src.modules.pipeline.context import PipelineContext
from src.modules.pipeline.stages import stage_doubted_sections, stage_finalize_headings
from src.modules.structure.logging.pipeline_logger import PipelineLogger


def test_doubted_sections_flags_late_toc() -> None:
    logger = PipelineLogger.create(enabled=False)
    ctx = PipelineContext(pdf_path="x.pdf", logger=logger)
    ctx.det_toc_log_items = [{"kind": "toc_section_span", "page_number_start": 5}]
    ctx.book_metadata_line_ids = {1, 2, 3}
    ctx.toc_seed_ids = {2}
    ctx.toc_section_line_ids = {2, 3}
    stage_doubted_sections(ctx)
    assert ctx.first_toc_page == 5
    assert ctx.doubted_body_ids == {1}
    assert 2 in ctx.doubted_toc_ids


def test_finalize_headings_strips_metadata() -> None:
    from src.shared.models import FinalHeading

    logger = PipelineLogger.create(enabled=False)
    ctx = PipelineContext(pdf_path="x.pdf", logger=logger)
    ctx.toc_out = [
        FinalHeading(id="H1", text="Chapter 1", line_id=10, level=1),
        FinalHeading(id="H2", text="TOC entry", line_id=2, level=1, is_toc=True),
    ]
    ctx.book_metadata_line_ids = {1}
    ctx.layout_by_line_id = {10: {"page_number": 4}, 2: {"page_number": 1}}
    stage_finalize_headings(ctx)
    assert len(ctx.final_headings_items) == 2
    clean = [h for h in ctx.final_headings_items if not h.get("is_toc")]
    assert len(clean) == 1
