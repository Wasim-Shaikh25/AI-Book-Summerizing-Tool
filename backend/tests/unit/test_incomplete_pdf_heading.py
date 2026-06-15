"""Tests for incomplete PDF fragment heading detection."""

from __future__ import annotations

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.quality.heuristics import classify_heading
from src.modules.structure.dropped_heading_registry import (
    is_acceptable_study_title,
    is_incomplete_pdf_heading,
    is_noisy_fragment_heading,
)


def test_bareact_fragment_headings_flagged() -> None:
    samples = [
        "Section 118: Voluntarily causing hurt or grievous hurt by dangerous",
        "341 (4) Punishment for Fraudulently or dishonestly uses as genuine any",
        "Rs.10 lakh",
        "Rs.10 lakh — 111 BNS.",
        "E I L P a g e |",
        "punishment) in section BNS 109(2) (attempt to murder) and BNS",
        "Classification – Non-Cognizable. Bailable. Any Magistrate.",
        "apprehension has been ordered",
        "OF KIDNAPPING, ABDUCTION, SLAVERY AND FORCED (p. 235)",
        "Which would constitute an offence if committed in India",
        "111 BNS.\"",
        "Section (1)",
        "Non-Cognizable. Bailable. Any Magistrate.",
        "E I L P a g e",
        "seal, plate or other instrument E I L",
        "be of either description, it shall be competent",
        "A intentionally by his own bodily power causes such motion in the boiling",
        "weapons or means",
        "Section 317: Stolen property. — Section 318: Cheating.",
    ]
    for title in samples:
        assert is_incomplete_pdf_heading(title), title
        assert not is_acceptable_study_title(title), title


def test_good_statute_headings_not_flagged() -> None:
    good = [
        "Section 106: Causing death by negligence.",
        "Defamation (S – 356)",
        "Ingredients of organized crime",
    ]
    for title in good:
        assert not is_incomplete_pdf_heading(title), title
