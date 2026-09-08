"""Unit tests for body_structure_audit — deterministic checks and report counts."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.generation.body_structure_audit import (  # noqa: E402
    BodyAuditReport,
    SectionBodyIssue,
    _bullet_quality_ratio,
    _has_standalone_bold,
    _has_subheadings,
    _source_has_list_content,
    audit_body_structure,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sec(sid: str, heading: str, body: str) -> dict:
    return {"section_id": sid, "heading": heading, "body": body}


LONG_PROSE = "Word " * 130   # > 600 chars, pure prose


# ---------------------------------------------------------------------------
# Test 1: long body with no ### → missing_subheadings
# ---------------------------------------------------------------------------

def test_audit_flags_missing_subheadings_in_long_body() -> None:
    sections = [_sec("S1", "Chapter Intro", LONG_PROSE)]
    report = audit_body_structure(sections, source_by_id={"S1": "some source"})
    types = [i.issue_type for i in report.issues]
    assert "missing_subheadings" in types


# ---------------------------------------------------------------------------
# Test 2: short body with no ### → no issue
# ---------------------------------------------------------------------------

def test_audit_does_not_flag_short_body_without_subheadings() -> None:
    sections = [_sec("S1", "Short", "A brief paragraph of text.")]
    report = audit_body_structure(sections, source_by_id={})
    types = [i.issue_type for i in report.issues]
    assert "missing_subheadings" not in types


# ---------------------------------------------------------------------------
# Test 3: source has numbered list, body has no bullets → missing_bullets
# ---------------------------------------------------------------------------

def test_audit_flags_missing_bullets_when_source_has_list() -> None:
    source = "1. First item\n2. Second item\n3. Third item"
    body = "This section covers three important aspects of the subject."
    sections = [_sec("S1", "Heading", body)]
    report = audit_body_structure(sections, source_by_id={"S1": source})
    types = [i.issue_type for i in report.issues]
    assert "missing_bullets" in types


# ---------------------------------------------------------------------------
# Test 4: source is pure prose, body has no bullets → no missing_bullets
# ---------------------------------------------------------------------------

def test_audit_does_not_flag_when_source_has_no_list() -> None:
    source = "This is a plain prose paragraph with no lists at all."
    body = "Rewritten prose paragraph without any bullet points."
    sections = [_sec("S1", "Heading", body)]
    report = audit_body_structure(sections, source_by_id={"S1": source})
    types = [i.issue_type for i in report.issues]
    assert "missing_bullets" not in types


# ---------------------------------------------------------------------------
# Test 5 & 6: _source_has_list_content
# ---------------------------------------------------------------------------

def test_source_has_list_content_detects_numbered_list() -> None:
    assert _source_has_list_content("1. Item\n2. Item") is True


def test_source_has_list_content_detects_lettered_list() -> None:
    assert _source_has_list_content("a) Item\nb) Item") is True


def test_source_has_list_content_returns_false_for_prose() -> None:
    assert _source_has_list_content("A plain paragraph of prose text.") is False


# ---------------------------------------------------------------------------
# Test 7: standalone bold fragment → bold_fragments
# ---------------------------------------------------------------------------

def test_audit_flags_bold_fragment_lines() -> None:
    body = "Normal prose.\n\n**Key point**\n\nMore prose."
    sections = [_sec("S1", "Heading", body)]
    report = audit_body_structure(sections, source_by_id={})
    types = [i.issue_type for i in report.issues]
    assert "bold_fragments" in types


# ---------------------------------------------------------------------------
# Test 8: > 30 % thin bullets → thin_bullets
# ---------------------------------------------------------------------------

def test_audit_flags_thin_bullets() -> None:
    body = (
        "- See above.\n"
        "- N/A\n"
        "- Refer later.\n"
        "- This is a longer and more informative bullet point.\n"
        "- Also short.\n"
    )
    sections = [_sec("S1", "Heading", body)]
    report = audit_body_structure(sections, source_by_id={})
    types = [i.issue_type for i in report.issues]
    assert "thin_bullets" in types


# ---------------------------------------------------------------------------
# Test 9: all good bullets → no thin_bullets
# ---------------------------------------------------------------------------

def test_audit_does_not_flag_good_bullets() -> None:
    body = (
        "- A well-written bullet with enough words to count.\n"
        "- Another substantive point that provides real value.\n"
        "- This one also contains more than five words.\n"
    )
    sections = [_sec("S1", "Heading", body)]
    report = audit_body_structure(sections, source_by_id={})
    types = [i.issue_type for i in report.issues]
    assert "thin_bullets" not in types


# ---------------------------------------------------------------------------
# Test 10: count accuracy
# ---------------------------------------------------------------------------

def test_audit_report_counts_sections_correctly() -> None:
    good_body = (
        "- This bullet has enough words to pass the threshold check.\n"
        "- Another well-written bullet that provides meaningful context.\n"
        "- A third substantive bullet with plenty of informative content here.\n"
    )
    flagged_body = LONG_PROSE  # missing_subheadings

    sections = [
        _sec("S1", "Good", good_body),
        _sec("S2", "Good2", good_body),
        _sec("S3", "Good3", good_body),
        _sec("S4", "Flagged", flagged_body),
        _sec("S5", "Flagged2", flagged_body),
    ]
    report = audit_body_structure(sections, source_by_id={})
    assert report.sections_checked == 5
    assert report.sections_flagged == 2


# ---------------------------------------------------------------------------
# Test 11: LLM disabled → chat mock never called
# ---------------------------------------------------------------------------

def test_audit_llm_disabled_never_calls_chat(monkeypatch) -> None:
    monkeypatch.setenv("BODY_AUDIT_LLM", "0")
    chat_mock = MagicMock()
    sections = [_sec("S1", "H", LONG_PROSE)]
    audit_body_structure(sections, source_by_id={}, chat=chat_mock)
    chat_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Test 12 & 13: helper function units
# ---------------------------------------------------------------------------

def test_has_subheadings_true_for_triple_hash() -> None:
    assert _has_subheadings("### Subtitle\nSome text") is True


def test_has_subheadings_false_for_double_hash_only() -> None:
    assert _has_subheadings("## Chapter heading\nSome text") is False


# ---------------------------------------------------------------------------
# Test 14: bullet quality ratio calculation
# ---------------------------------------------------------------------------

def test_bullet_quality_ratio_correct_calculation() -> None:
    # 2 thin (< 5 words), 8 substantive (>= 5 words) → ratio = 0.2
    body = (
        "- Short.\n"                                                              # thin: 1 word
        "- Also short here.\n"                                                    # thin: 3 words
        "- A long enough bullet that has five or more words.\n"                   # 10 words
        "- Another good bullet with many words in it.\n"                          # 8 words
        "- Yet another good one with enough content here for the test.\n"         # 12 words
        "- One more good bullet providing real informational value here.\n"       # 9 words
        "- A seventh substantive bullet that adds genuine learning value.\n"      # 10 words
        "- And an eighth bullet with substantial content in this section.\n"      # 11 words
        "- Ninth bullet here with ample descriptive content for the reader.\n"    # 11 words
        "- Tenth and final bullet that contains enough words to qualify.\n"       # 12 words
    )
    ratio = _bullet_quality_ratio(body)
    assert abs(ratio - 0.2) < 0.01


# ---------------------------------------------------------------------------
# Test 15: _has_standalone_bold
# ---------------------------------------------------------------------------

def test_has_standalone_bold_detects_bold_line() -> None:
    assert _has_standalone_bold("Normal line.\n\n**Key Term**\n\nMore text.") is True


def test_has_standalone_bold_ignores_inline_bold() -> None:
    assert _has_standalone_bold("This **word** is bold inline.") is False
