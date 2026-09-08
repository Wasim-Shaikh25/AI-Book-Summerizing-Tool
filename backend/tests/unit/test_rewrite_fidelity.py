"""Tests for rewrite fidelity overlap scoring."""

from __future__ import annotations

from src.modules.generation.rewrite_fidelity import (
    needs_regeneration,
    reset_fidelity_stats,
    section_overlap_score,
    source_is_low_grounding,
    source_real_content_chars,
)


def test_section_overlap_score_matches_source_tokens() -> None:
    source = "The quick brown fox jumps over the lazy dog repeatedly."
    generated = "A quick brown fox jumps over the lazy dog in the field."
    score = section_overlap_score(source=source, generated=generated)
    assert score > 0.5


def test_low_overlap_triggers_regeneration() -> None:
    source = "Alpha beta gamma delta epsilon zeta eta theta."
    generated = "Completely unrelated content about widgets and gears."
    score = section_overlap_score(source=source, generated=generated)
    assert needs_regeneration(score, min_overlap=0.30)


def test_fidelity_stats_reset() -> None:
    stats = reset_fidelity_stats()
    assert stats.drift_regenerated == 0
    assert stats.low_grounding_sections == 0
    assert stats.attempts_per_section == {}


def test_index_contents_source_flagged_low_grounding() -> None:
    # An index/contents page: enumerated list of titles, no real body text.
    source = (
        "169. Candidate, electoral right defined.\n"
        "170. Bribery.\n"
        "171. Undue influence at elections.\n"
        "172. Personation at elections.\n"
        "173. Punishment for bribery.\n"
    )
    assert source_is_low_grounding(source)


def test_substantive_prose_not_low_grounding() -> None:
    source = (
        "A person commits this offence when they knowingly take property "
        "belonging to another without consent and with intent to deprive them "
        "permanently. The punishment depends on the value involved and whether "
        "force was used during the act."
    )
    assert not source_is_low_grounding(source)


def test_real_content_chars_excludes_enumerated_titles() -> None:
    source = "1. First Title\n2. Second Title\nActual sentence with real content here."
    # Only the prose line contributes letters.
    assert source_real_content_chars(source) == sum(
        1 for ch in "Actual sentence with real content here." if ch.isalpha()
    )


def test_thin_source_flagged_low_grounding() -> None:
    assert source_is_low_grounding("Short note.")
