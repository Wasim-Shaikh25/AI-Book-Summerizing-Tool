"""Unit tests for line-by-line notes quality audit."""

from __future__ import annotations

from src.modules.quality.heuristics import compute_verdict_scores
from src.modules.quality.line_audit import (
    audit_all_sections,
    audit_section_body,
    format_line_audit_report,
)


def test_audit_section_flags_meta_filler_and_standalone_bold() -> None:
    body = (
        "This chapter covers the main ideas.\n"
        "**Punishment**\n"
        "Section 198 states that prosecution requires court permission for certain offences."
    )
    result = audit_section_body(
        section_id="S1",
        heading="Prosecution of offences",
        body=body,
        source_preview="Section 198. No Court shall take cognizance of any offence",
    )
    codes = {i.code for i in result.issues}
    assert "meta_filler" in codes
    assert "standalone_bold" in codes
    assert result.verdict in {"OK", "WARN", "FAIL"}


def test_audit_section_passes_clean_prose() -> None:
    body = (
        "Section 198 requires court permission before certain prosecutions begin. "
        "This rule protects accused persons from harassment through private complaints. "
        "The magistrate must examine the complainant before issuing process."
    )
    result = audit_section_body(
        section_id="S2",
        heading="Section 198: Prosecution",
        body=body,
        source_preview="Section 198. No Court shall take cognizance",
    )
    assert result.verdict in {"PASS", "OK"}
    assert result.line_count >= 1


def test_audit_all_sections_aggregates_book_stats() -> None:
    rows = [
        {"section_id": "S1", "heading": "Topic A"},
        {"section_id": "S2", "heading": "Topic B"},
    ]
    bodies = {
        "S1": "Good prose about the legal rule. It explains the requirement clearly.",
        "S2": "This section covers many topics.\n- one\n- two\n- three\n- four",
    }
    book = audit_all_sections(rows, bodies_by_id=bodies, source_by_id={"S1": "legal rule", "S2": "topics"})
    assert book.total_lines >= 2
    assert book.sections_fail + book.sections_warn + book.sections_ok + book.sections_pass == 2
    report_lines = format_line_audit_report(book)
    assert any("Sections line-audited" in ln for ln in report_lines)


def test_low_grounding_source_skips_overlap_checks() -> None:
    # Source is an index/contents listing; the paraphrased body shares no tokens,
    # but overlap/drift must NOT be flagged (already reported as low-grounding).
    body = (
        "Punishment for the offence depends on the circumstances of each case. "
        "The court considers aggravating factors before sentencing the accused."
    )
    result = audit_section_body(
        section_id="S1",
        heading="Punishment provisions",
        body=body,
        source_preview="65. Punishment for rape\n66. Causing death\n67. Sexual offences",
        semantic=False,
        source_low_grounding=True,
    )
    codes = {i.code for i in result.issues}
    assert "low_source_overlap" not in codes
    assert "section_drift" not in codes


def test_literal_overlap_still_flags_when_semantic_off() -> None:
    # With semantic grounding disabled and a real (non-list) source, a line that
    # shares almost nothing with the source is still flagged as drift.
    body = "Quantum entanglement links particles across vast astronomical distances instantly."
    result = audit_section_body(
        section_id="S1",
        heading="Overview",
        body=body,
        source_preview=(
            "Whoever dishonestly takes movable property out of the possession of "
            "another person without consent commits theft and is punishable."
        ),
        semantic=False,
    )
    codes = {i.code for i in result.issues}
    assert "low_source_overlap" in codes


def test_semantic_grounder_noop_when_disabled() -> None:
    from src.modules.quality.line_audit import _SemanticGrounder

    grounder = _SemanticGrounder("some source text here", enabled=False)
    assert grounder.ready is False
    assert grounder.grounded("any line") is False


def test_compute_verdict_includes_line_quality() -> None:
    scores = compute_verdict_scores(
        mapped_count=10,
        total_sections=10,
        inversions=0,
        dup_chapter_count=0,
        avg_overlap=0.4,
        repeated_pairs=0,
        weak_heading_count=0,
        title_noise_count=0,
        outline_body_hits=0,
        pdf_match_failures=0,
        line_audit_fail_sections=2,
        line_audit_warn_sections=3,
    )
    assert scores["line_quality"] == "WARN"
