"""Tests for stage 15g title validation."""
from __future__ import annotations

from src.modules.structure.heading_title_validation import is_citation_fragment_title, rule_reject_reason
from src.modules.structure.final_structuring.title_validation import validate_chapter_hierarchy


def test_citation_fragment_detected() -> None:
    assert is_citation_fragment_title("1990 NOC 107)")
    assert is_citation_fragment_title("Vallamantlam v. Union of India, AIR 2003 SC 2902)")
    assert is_citation_fragment_title("Nellore, A.I.R 1952 Mad. 253)")
    assert is_citation_fragment_title("(A.I.R. 1955 S.C. 123) [Art. 13)")
    assert not is_citation_fragment_title("Equality before the law (Art. 14)")
    assert not is_citation_fragment_title("C. Position after the Minerva Mills Case (1980)")
    assert not is_citation_fragment_title("Case No. 20 STATE OF PUNJAB Vs. SAT PAL SINGH")
    assert not is_citation_fragment_title("V. Right To Education (S. 21A)")
    assert not is_citation_fragment_title("Who can be a citizen of India (Arts. 5-8)")


def test_rule_reject_sentence_like() -> None:
    assert rule_reject_reason("He must have resided in India for at least six months") == "sentence_like"


def test_validate_fixes_citation_sections() -> None:
    hierarchy = {
        "meta": {},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Fundamental Rights",
                "sections": [
                    {
                        "section_id": "S11",
                        "heading": "1990 NOC 107)",
                        "page_number": 22,
                        "fragment": {"preview": "Some body about equality."},
                        "subheadings": [{"heading": "Special Courts"}],
                    }
                ],
            }
        ],
    }
    ultimate = [{"section_id": "S11", "heading": "1990 NOC 107)"}]
    out = validate_chapter_hierarchy(
        hierarchy,
        ultimate_sections=ultimate,
    )
    title = out["chapters"][0]["sections"][0]["heading"]
    # Citation fragment must be replaced by the clean subheading label
    # (whether repaired in fix_verbose or the main validation loop).
    assert title == "Special Courts"
    assert "NOC" not in title
