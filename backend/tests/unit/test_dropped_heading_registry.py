"""Unit tests for dropped heading registry."""
from __future__ import annotations

from src.modules.structure.dropped_heading_registry import (
    DroppedHeadingRegistry,
    is_sentence_like_title,
)


def test_is_sentence_like_title_detects_prose() -> None:
    assert is_sentence_like_title("He must have resided in India for not less than five years")
    assert is_sentence_like_title("It will be seen that items (a), (b) and (c) above refer to modes.")
    assert not is_sentence_like_title("Citizenship by descent (Art. 5)")


def test_registry_bans_dropped_text() -> None:
    reg = DroppedHeadingRegistry()
    reg.register(text="He must have resided in India")
    assert not reg.is_allowed_title("He must have resided in India")
    assert reg.is_allowed_title("Citizenship by descent (Art. 5)")


def test_registry_from_gate_log() -> None:
    reg = DroppedHeadingRegistry()
    reg.extend_from_gate_log(
        [
            {"action": "drop_heading_validity_gate", "text": "He must have resided in India", "line_id": 42},
            {"action": "keep", "text": "Fundamental Rights"},
        ]
    )
    assert reg.is_banned_text("He must have resided in India")
    assert not reg.is_banned_text("Fundamental Rights")
