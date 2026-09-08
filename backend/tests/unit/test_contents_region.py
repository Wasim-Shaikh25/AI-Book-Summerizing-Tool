"""Unit tests for document-wide contents/index page detection."""
from __future__ import annotations

from src.shared.models import NormalizedLine
from src.modules.structure.contents_region import detect_contents_regions


def _line(lid: int, text: str, page: int, *, noise: bool = False) -> NormalizedLine:
    return NormalizedLine(line_id=lid, text=text, page_number=page, is_noise=noise)


def test_detects_enumeration_dominated_page() -> None:
    lines = [
        _line(1, "CHAPTER V OF SEXUAL OFFENCES", 3),
        _line(2, "63. Rape.", 3),
        _line(3, "64. Punishment for rape.", 3),
        _line(4, "65. Punishment for rape in certain cases.", 3),
        _line(5, "66. Punishment for causing death.", 3),
        _line(6, "67. Sexual intercourse by husband.", 3),
        _line(7, "68. Sexual intercourse by a person in authority.", 3),
    ]
    region_ids, log = detect_contents_regions(lines)
    assert region_ids == {1, 2, 3, 4, 5, 6, 7}
    assert log and log[0]["kind"] == "contents_region_page"
    assert log[0]["enumerated_line_count"] == 6


def test_ignores_prose_page() -> None:
    lines = [
        _line(10, "Rape is defined as non-consensual intercourse and is punishable.", 4),
        _line(11, "The section sets out aggravating circumstances in detail.", 4),
        _line(12, "63. One enumerated row among prose.", 4),
        _line(13, "Courts have interpreted consent strictly over the years.", 4),
        _line(14, "Punishment ranges depending on the severity of the offence.", 4),
    ]
    region_ids, log = detect_contents_regions(lines)
    assert region_ids == set()
    assert log == []


def test_skips_short_pages() -> None:
    lines = [
        _line(20, "1. A", 5),
        _line(21, "2. B", 5),
        _line(22, "3. C", 5),
    ]
    region_ids, _ = detect_contents_regions(lines)
    assert region_ids == set()


def test_excludes_noise_lines_from_region() -> None:
    lines = [
        _line(30, "Page footer 12", 6, noise=True),
        _line(31, "1. Definitions.", 6),
        _line(32, "2. Application.", 6),
        _line(33, "3. Interpretation.", 6),
        _line(34, "4. Repeal.", 6),
        _line(35, "5. Savings.", 6),
    ]
    region_ids, _ = detect_contents_regions(lines)
    assert 30 not in region_ids
    assert region_ids == {31, 32, 33, 34, 35}
