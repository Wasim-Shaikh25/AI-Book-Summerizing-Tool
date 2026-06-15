"""Unit tests for notes quality audit helpers."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.quality.analyzer import (  # noqa: E402
    _title_grounded_in_source,
    aggregate_batch_summary,
    dynamic_sample_section_ids,
    pdf_match_heading,
)
from src.modules.quality.heuristics import (  # noqa: E402
    chapter_mirrors_first_section,
    classify_heading,
    compute_verdict_scores,
    detect_syllabus_noise_in_body,
    find_parent_mirror_chapters,
)
from src.modules.quality.models import BookAuditResult  # noqa: E402


def test_title_grounded_in_source() -> None:
    src = "This provision includes electronic and digital records within the meaning of documents."
    assert _title_grounded_in_source("Electronic and Digital Records as Documents", src)
    assert not _title_grounded_in_source("Maritime Piracy and Naval Jurisdiction", src)


def test_pdf_match_clean_title_grounded_in_source_not_failure() -> None:
    # Title is clean (looks_ok) and absent from the PDF page, but its content
    # words are covered by the section source -> grounded_in_source (not a failure).
    page_text = ["totally unrelated page content about administrative procedures"]
    source = "This provision includes electronic and digital records within the meaning of documents."
    status, _ = pdf_match_heading(
        "Electronic and Digital Records as Documents",
        None,
        page_text,
        source_preview=source,
    )
    assert status == "grounded_in_source"


def test_pdf_match_ungrounded_clean_title_still_not_in_pdf() -> None:
    page_text = ["totally unrelated page content"]
    status, _ = pdf_match_heading(
        "Maritime Piracy and Naval Jurisdiction",
        None,
        page_text,
        source_preview="This provision includes electronic and digital records as documents.",
    )
    assert status == "not_in_pdf"


def test_dynamic_sample_section_ids_picks_quintiles() -> None:
    ids = [f"S{i}" for i in range(1, 53)]
    samples = dynamic_sample_section_ids(ids)
    assert samples[0] == ("S1", "first")
    assert samples[-1][0] == "S52"
    assert len(samples) == 5


def test_dynamic_sample_section_ids_handles_small_list() -> None:
    samples = dynamic_sample_section_ids(["S1", "S2"])
    sample_ids = [s[0] for s in samples]
    assert "S1" in sample_ids
    assert "S2" in sample_ids


def test_detect_syllabus_noise_in_body() -> None:
    body = "Course Outcomes:\n- Understand family law basics."
    flags = detect_syllabus_noise_in_body(body)
    assert "syllabus_admin" in flags

    clean = "- Mahr is mandatory payment to the wife."
    assert detect_syllabus_noise_in_body(clean) == []


def test_detect_syllabus_noise_module_and_also_cover() -> None:
    body = "Also cover: divorce rules.\nMODULE 2 topics listed here."
    flags = detect_syllabus_noise_in_body(body)
    assert "also_cover_checklist" in flags
    assert "module_unit_ref" in flags


def test_classify_heading_flags_module() -> None:
    assert classify_heading("MODULE 1") == "structural_partition"
    assert classify_heading("Course Outcomes") == "syllabus_heading"


def test_compute_verdict_scores_pass_case() -> None:
    scores = compute_verdict_scores(
        mapped_count=50,
        total_sections=50,
        inversions=0,
        dup_chapter_count=0,
        avg_overlap=0.4,
        repeated_pairs=2,
        weak_heading_count=2,
        title_noise_count=1,
        syllabus_body_hits=0,
        pdf_match_failures=1,
    )
    assert scores["coverage"] == "PASS"
    assert scores["overall"] == "PASS"


def test_title_from_fragment_preview_uses_source_line() -> None:
    from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

    sec = {
        "fragment": {
            "preview": "Custody (Wali) and Hijnat under Muslim law define guardianship roles.",
        }
    }
    title = title_from_fragment_preview(sec)
    assert title
    assert "Custody" in title
    assert "Section topic" not in title


def test_chapter_mirrors_first_section_detects_parent_copy() -> None:
    assert chapter_mirrors_first_section("Marriage in Muslim Law", "Marriage in Muslim Law")
    assert chapter_mirrors_first_section("Divorce", "Meaning of Divorce") is False


def test_find_parent_mirror_chapters() -> None:
    chapters = [
        {"heading": "Mahr", "sections": [{"heading": "Mahr"}]},
        {"heading": "Divorce", "sections": [{"heading": "Types of Divorce"}]},
    ]
    mirrors = find_parent_mirror_chapters(chapters)
    assert len(mirrors) == 1
    assert "Mahr" in mirrors[0]


def test_aggregate_batch_summary() -> None:
    results = [
        BookAuditResult(
            label="family-law",
            pdf_path="a.pdf",
            md_path="a.md",
            log_dir="logs/a",
            total_sections=53,
            mapped_count=53,
            coverage_ratio=1.0,
            verdict_scores={"overall": "PASS"},
            top_issues=["issue1"],
            strong_sections=["S1 | Marriage"],
        ),
        BookAuditResult(
            label="environmental-law",
            pdf_path="b.pdf",
            md_path="b.md",
            log_dir="logs/b",
            total_sections=47,
            mapped_count=47,
            coverage_ratio=1.0,
            verdict_scores={"overall": "OK"},
            top_issues=["MODULE title"],
            strong_sections=[],
        ),
    ]
    summary = aggregate_batch_summary(results)
    assert summary["book_count"] == 2
    assert summary["overall"]["pass"] == 1
    assert summary["overall"]["ok"] == 1
    assert summary["books"][0]["label"] == "family-law"
