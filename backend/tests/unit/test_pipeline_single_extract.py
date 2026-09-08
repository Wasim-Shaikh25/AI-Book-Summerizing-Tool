from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.modules.pipeline.stages import stage_extract
from src.shared.models import NormalizedLine, PipelineResult


def test_run_pipeline_calls_extract_pdf_once() -> None:
    fake_lines = [
        NormalizedLine(line_id=1, text="Chapter 1", page_number=1),
        NormalizedLine(line_id=2, text="Body text here.", page_number=1),
    ]

    with patch(
        "src.modules.pipeline.stages.extract_pdf",
        return_value=(fake_lines, "Test Book", []),
    ) as extract_mock:
        with patch("src.modules.pipeline.runner.STAGES", [stage_extract]):
            from src.modules.pipeline.runner import run_pipeline

            result, _ = run_pipeline("dummy.pdf", enable_logs=False)

    extract_mock.assert_called_once_with("dummy.pdf")
    assert result.book_title == "Test Book"
    assert result.total_pages == 1
    assert len(result.lines) == 2


def test_ingestion_service_does_not_call_extract_pdf_before_pipeline() -> None:
    pipeline_result = PipelineResult(
        book_title="Test Book",
        total_pages=2,
        lines=[NormalizedLine(line_id=1, text="A", page_number=1)],
    )
    fake_logger = MagicMock()
    fake_logger.run_dir = None

    with patch("src.modules.ingestion.pdf_extractor.extract_pdf") as extract_mock:
        with patch("services.ingestion_service.shutil.copy2"):
            with patch(
                "services.ingestion_service.run_pipeline",
                return_value=(pipeline_result, fake_logger),
            ):
                with patch("services.ingestion_service.KnowledgeStore"):
                    with patch("services.ingestion_service.BookRepository") as book_repo_cls:
                        with patch("services.ingestion_service.TocRepository"):
                            with patch("services.ingestion_service.UserBookRepository") as user_books_cls:
                                book = MagicMock()
                                book.book_id = "book-1"
                                book_repo_cls.return_value.save_book.return_value = book
                                user_books_cls.return_value.link.return_value = None

                                from services.ingestion_service import IngestionService

                                svc = IngestionService()
                                svc.book_repo = book_repo_cls.return_value
                                svc.toc_repo = MagicMock()
                                svc.user_books = user_books_cls.return_value
                                svc.store = MagicMock()

                                out = svc.ingest_upload(
                                    "user-1",
                                    "/tmp/upload.pdf",
                                    "sample.pdf",
                                    skip_rag=True,
                                )

    extract_mock.assert_not_called()
    assert out["title"] == "Test Book"
    assert out["total_pages"] == 2
