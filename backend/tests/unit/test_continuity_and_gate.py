"""Unit checks for gate helpers (no full PDF)."""

from src.modules.structure.continuity_filter import parse_line_id_from_heading_id
from src.modules.structure.heading_heuristics import should_force_invalid_enumerated_list_item


def test_parse_line_id_from_heading_id() -> None:
    assert parse_line_id_from_heading_id("L42:foo") == 42
    assert parse_line_id_from_heading_id("x") is None
    assert parse_line_id_from_heading_id(None) is None


def test_heading_heuristics_section_vs_list() -> None:
    assert should_force_invalid_enumerated_list_item("1.2 Topic name here") is False
    assert should_force_invalid_enumerated_list_item("3. Long body text " + "x" * 60) is True
