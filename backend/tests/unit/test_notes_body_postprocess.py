"""Unit tests for rewritten section body post-processing."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.generation.notes_body_postprocess import postprocess_rewritten_section  # noqa: E402


def test_postprocess_removes_meta_filler_and_heading_echo() -> None:
    body = """This section covers marriage law basics.

Marriage Law

- Mahr is a mandatory payment.
"""
    out = postprocess_rewritten_section(body, heading="Marriage Law")
    assert "This section covers" not in out
    assert "Marriage Law" not in out
    assert "Mahr is a mandatory payment" in out


def test_postprocess_removes_syllabus_line() -> None:
    body = "Instructional hours: 45\n\n- Divorce rules apply in family courts."
    out = postprocess_rewritten_section(body, heading="Divorce")
    assert "Instructional hours" not in out
    assert "Divorce rules" in out


def test_postprocess_drops_thin_bullets() -> None:
    body = "- Yes\n- No\n- Valid point with enough words here."
    out = postprocess_rewritten_section(body, heading="Topic")
    assert "- Yes" not in out
    assert "Valid point with enough words here." in out


def test_postprocess_never_empties_real_content() -> None:
    """Robustness guard: filtering must not silently destroy a section with real content."""
    body = (
        "Theft is the dishonest taking of movable property without consent.\n"
        "It is punishable under the relevant provision."
    )
    out = postprocess_rewritten_section(body, heading="Theft")
    assert out.strip()
    assert "dishonest taking" in out


def test_postprocess_guard_keeps_short_paragraph_when_all_bullets_thin() -> None:
    body = "Robbery is theft accompanied by force or the threat of force against a person."
    out = postprocess_rewritten_section(body, heading="Robbery")
    assert "Robbery is theft" in out
