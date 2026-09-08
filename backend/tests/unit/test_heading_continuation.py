"""Unit tests for _continuation_context_check and its wiring into the gate."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.structure.heading_validity_gate import (  # noqa: E402
    _continuation_context_check,
    gate_heading_validity_candidates,
)
from src.shared.models import HeadingCandidate, NormalizedLine  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    text: str,
    *,
    cid: str = "C1",
    start_line: int = 10,
    before: list[str] | None = None,
    after: list[str] | None = None,
) -> HeadingCandidate:
    return HeadingCandidate(
        id=cid,
        text=text,
        start_line=start_line,
        end_line=start_line,
        before_context=before or [],
        after_context=after or [],
        full_context_preview="",
        is_valid=True,
        valid_reason="",
        is_toc=False,
        toc_reason="",
        confidence=0.9,
    )


def _make_line(
    line_id: int,
    text: str,
    *,
    is_bold: bool = False,
    large_font: bool = False,
    large_gap: bool = False,
    centered: bool = False,
    source: str = "body",
    page_number: int = 1,
) -> NormalizedLine:
    ln = MagicMock(spec=NormalizedLine)
    ln.line_id = line_id
    ln.text = text
    ln.is_bold = is_bold
    ln.large_font = large_font
    ln.large_gap = large_gap
    ln.centered = centered
    ln.is_mix_bold = False
    ln.is_noise = False
    ln.source = source
    ln.page_number = page_number
    return ln


# ---------------------------------------------------------------------------
# Test 1: previous line ends without terminal punctuation, candidate lowercase
# ---------------------------------------------------------------------------

def test_continuation_check_drops_lowercase_after_open_sentence() -> None:
    """Signal 1: prev line ends mid-sentence AND candidate starts lowercase → True."""
    result = _continuation_context_check(
        candidate_text="such rules are binding upon all parties",
        before_lines=["The general principle is very clear"],
        after_lines=[],
    )
    assert result is True


# ---------------------------------------------------------------------------
# Test 2: previous line ends with ".", candidate Title Case → keep
# ---------------------------------------------------------------------------

def test_continuation_check_keeps_heading_after_complete_sentence() -> None:
    """Signal 1 absent: prev line ends with period → candidate is not a continuation."""
    result = _continuation_context_check(
        candidate_text="Liability Under Contract",
        before_lines=["This is a complete sentence."],
        after_lines=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Test 3: next line starts lowercase AND candidate is >5 words → drop
# ---------------------------------------------------------------------------

def test_continuation_check_drops_when_next_line_is_lowercase_continuation() -> None:
    """Signal 2: next line starts lowercase AND candidate >5 words → True."""
    result = _continuation_context_check(
        candidate_text="and the terms of the agreement apply broadly",
        before_lines=[],
        after_lines=["including all subsidiary clauses that were mentioned"],
    )
    assert result is True


# ---------------------------------------------------------------------------
# Test 4: no before/after context at all → keep
# ---------------------------------------------------------------------------

def test_continuation_check_ignores_empty_context() -> None:
    """No context lines: cannot determine continuation → False (conservative)."""
    result = _continuation_context_check(
        candidate_text="something that might look suspicious",
        before_lines=[],
        after_lines=[],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Test 5: next line lowercase but candidate is ≤5 words → keep
# ---------------------------------------------------------------------------

def test_continuation_check_keeps_short_candidate_even_if_lowercase_next() -> None:
    """Signal 2 requires >5 words; short candidate is exempt even if next line is lowercase."""
    result = _continuation_context_check(
        candidate_text="Offer and Acceptance",          # 3 words
        before_lines=[],
        after_lines=["the offeror must communicate clearly"],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Test 6: full gate call — continuation fragment dropped with correct reason
# ---------------------------------------------------------------------------

def test_gate_wires_continuation_check_into_drop_log() -> None:
    """Integration: gate drops a fragment and logs reason containing 'continuation_fragment'."""
    candidate = _make_candidate(
        text="such provisions are enforceable by either party",
        cid="C1",
        start_line=20,
        before=["The statute does not specify otherwise"],   # open sentence
        after=[],
    )
    line = _make_line(20, candidate.text, is_bold=False)
    kept, log = gate_heading_validity_candidates([candidate], lines=[line])

    assert len(kept) == 0, "Fragment must be dropped"
    assert len(log) == 1
    assert "continuation_fragment" in log[0]["reason"]


# ---------------------------------------------------------------------------
# Test 7: strong_layout_heading fast-path keeps bold Title Case heading
#          even when previous line is open (safety guard)
# ---------------------------------------------------------------------------

def test_gate_keeps_bold_title_case_even_with_open_previous_line() -> None:
    """Safety: bold + Title Case + ≤13 words short-circuits before continuation check."""
    candidate = _make_candidate(
        text="Rights and Remedies",
        cid="C2",
        start_line=30,
        before=["The following section covers important aspects"],  # open sentence
        after=[],
    )
    line = _make_line(30, candidate.text, is_bold=True)
    kept, log = gate_heading_validity_candidates([candidate], lines=[line])

    assert any(c.id == "C2" for c in kept), (
        "Bold Title Case heading must be kept regardless of continuation context"
    )
    # Drop log must NOT mention this candidate
    assert all(entry.get("heading_id") != "C2" for entry in log)


# ---------------------------------------------------------------------------
# Test 8: conjunction opener after open sentence → drop
# ---------------------------------------------------------------------------

def test_continuation_check_conjunction_start_after_open_sentence() -> None:
    """Signal 1 variant: candidate starts with conjunction after open sentence → True."""
    for conjunction in ("and", "but", "which", "because", "although"):
        result = _continuation_context_check(
            candidate_text=f"{conjunction} the consequences flow from this rule",
            before_lines=["Each obligation carries certain weight"],   # open
            after_lines=[],
        )
        assert result is True, (
            f"Conjunction '{conjunction}' after open sentence must be flagged"
        )
