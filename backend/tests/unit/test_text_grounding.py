"""Unit tests for shared subject-agnostic text-grounding primitives."""
from __future__ import annotations

from src.shared.text_grounding import (
    enumerated_line_ratio,
    is_contents_listing,
    is_enumerated_title_line,
    is_low_grounding,
    real_content_chars,
)


def test_is_enumerated_title_line_matches_index_rows() -> None:
    assert is_enumerated_title_line("65. Punishment for rape in certain cases.")
    assert is_enumerated_title_line("12) Some Title")
    assert is_enumerated_title_line("(7) Another Title")
    assert is_enumerated_title_line("3: Definitions")


def test_is_enumerated_title_line_rejects_prose() -> None:
    assert not is_enumerated_title_line("This section explains the punishment for the offence.")
    assert not is_enumerated_title_line("Bribery is an offence under this chapter.")
    assert not is_enumerated_title_line("")


def test_real_content_chars_excludes_enumerated_lines() -> None:
    text = "65. Punishment for rape\n66. Causing death\nThis is real prose text here."
    # Only the prose line contributes alphabetic characters.
    assert real_content_chars(text) == sum(1 for c in "This is real prose text here" if c.isalpha())


def test_enumerated_line_ratio_counts() -> None:
    enum, total = enumerated_line_ratio(
        ["1. A", "2. B", "real prose line", "  "]
    )
    assert (enum, total) == (2, 3)


def test_is_low_grounding_flags_enumerated_list() -> None:
    text = "65. Punishment for rape\n66. Causing death\n67. Sexual offences"
    assert is_low_grounding(text, min_chars=160)


def test_is_low_grounding_flags_thin_prose() -> None:
    assert is_low_grounding("A short note.", min_chars=160)


def test_is_low_grounding_accepts_real_section() -> None:
    body = "This section sets out the punishment. " * 10
    assert not is_low_grounding(body, min_chars=160)


def test_is_contents_listing_keeps_short_real_section() -> None:
    # ~120 real chars: below the 160 rewrite floor but above the 40 partition floor,
    # and not enumeration-dominated — must be kept by the stricter partition check.
    body = "This short section defines the offence and its scope clearly enough."
    assert real_content_chars(body) >= 40
    assert is_low_grounding(body, min_chars=160)
    assert not is_contents_listing(body)


def test_is_contents_listing_drops_enumerated_body() -> None:
    text = "65. Punishment for rape\n66. Causing death\n67. Sexual offences\n68. Authority"
    assert is_contents_listing(text)


def test_is_contents_listing_drops_near_empty_body() -> None:
    assert is_contents_listing("ab cd")
