"""Unit tests for stage 15d section budgeting and compression."""
from __future__ import annotations

from types import SimpleNamespace

from src.modules.structure.final_structuring.book_assembler import (
    _compress_sections_to_target,
    _merge_two_sections,
    _resolve_section_budget,
    build_ultimate_sections,
)


def test_resolve_section_budget_from_pages() -> None:
    assert _resolve_section_budget(page_count=230, kept_heading_count=500) == 103
    assert _resolve_section_budget(page_count=10, kept_heading_count=500) == 16


def test_compress_sections_merges_to_target() -> None:
    sections = [
        {"section_id": "S1", "heading": "A", "page_number": 1, "fragment": {"chars": 400}, "subheadings": []},
        {"section_id": "S2", "heading": "B", "page_number": 1, "fragment": {"chars": 350}, "subheadings": []},
        {"section_id": "S3", "heading": "C", "page_number": 2, "fragment": {"chars": 500}, "subheadings": []},
        {"section_id": "S4", "heading": "D", "page_number": 2, "fragment": {"chars": 300}, "subheadings": []},
    ]
    out, merges = _compress_sections_to_target(sections, 2)
    assert len(out) == 2
    assert merges == 2
    assert out[0]["section_id"] == "S1"
    assert out[1]["section_id"] == "S2"
    assert len(out[0]["subheadings"]) >= 1


def test_merge_two_sections_keeps_primary_heading() -> None:
    primary = {
        "section_id": "S1",
        "heading": "Fundamental Rights",
        "page_number": 10,
        "fragment": {"chars": 800, "start_line": 1, "end_line": 20},
        "subheadings": [],
    }
    secondary = {
        "section_id": "S2",
        "heading": "Equality (Art. 14)",
        "page_number": 10,
        "fragment": {"chars": 600, "start_line": 21, "end_line": 35},
        "subheadings": [{"heading": "Reasonable classification", "fragment": {"chars": 100}}],
    }
    merged = _merge_two_sections(primary, secondary)
    assert merged["heading"] == "Fundamental Rights"
    assert merged["fragment"]["chars"] == 1400
    assert len(merged["subheadings"]) == 2


def test_dense_book_produces_fewer_sections_than_headings() -> None:
    lines = []
    headings = []
    lid = 0
    for page in range(1, 11):
        for i in range(3):
            lid += 1
            headings.append(
                {
                    "line_id": lid,
                    "text": f"Topic {page}.{i + 1}",
                    "page_number": page,
                }
            )
            lines.append(SimpleNamespace(line_id=lid, text=headings[-1]["text"], page_number=page))
            for _ in range(4):
                lid += 1
                lines.append(
                    SimpleNamespace(
                        line_id=lid,
                        text=f"Body paragraph for page {page} topic {i + 1}. " * 12,
                        page_number=page,
                    )
                )
    hierarchy = [
        {"line_id": h["line_id"], "level": 2, "text": h["text"], "page_number": h["page_number"]} for h in headings
    ]
    ultimate = build_ultimate_sections(
        headings=headings,
        hierarchy=hierarchy,
        lines=lines,
        fragments=[],
        metadata_line_ids=set(),
        toc_seed_ids=set(),
    )
    meta = ultimate["meta"]
    assert meta["page_count"] == 10
    assert meta["section_budget"] == 16
    assert meta["kept_heading_count"] == 30
    assert meta["total_sections"] <= meta["section_budget"]
    assert meta["total_sections"] < meta["kept_heading_count"]


def test_partition_drops_index_listing_section() -> None:
    """A heading whose body is an enumerated contents list must not become a section."""
    lines = []
    headings = []

    # Section 1: heading followed by an enumerated contents/index list (low grounding).
    headings.append({"line_id": 1, "text": "Chapter V Index", "page_number": 1})
    lines.append(SimpleNamespace(line_id=1, text="Chapter V Index", page_number=1))
    index_rows = [
        "63. Rape and the scope of consent under the chapter.",
        "64. Punishment for rape in ordinary circumstances.",
        "65. Punishment for rape in certain aggravated cases.",
        "66. Punishment for causing death of the victim.",
        "67. Sexual intercourse by husband during separation.",
        "68. Sexual intercourse by a person in lawful authority.",
        "69. Sexual intercourse by employing deceitful means.",
        "70. Gang rape and the liability of each participant.",
        "71. Punishment for repeat offenders and prior conviction.",
        "72. Disclosure of identity of the victim is barred.",
    ]
    lid = 1
    for row in index_rows:
        lid += 1
        lines.append(SimpleNamespace(line_id=lid, text=row, page_number=1))

    # Section 2: heading followed by real prose (kept).
    lid += 1
    head2 = lid
    headings.append({"line_id": head2, "text": "Punishment for Rape", "page_number": 2})
    lines.append(SimpleNamespace(line_id=head2, text="Punishment for Rape", page_number=2))
    for _ in range(4):
        lid += 1
        lines.append(
            SimpleNamespace(
                line_id=lid,
                text="Whoever commits rape shall be punished with rigorous imprisonment. " * 4,
                page_number=2,
            )
        )

    hierarchy = [
        {"line_id": h["line_id"], "level": 2, "text": h["text"], "page_number": h["page_number"]}
        for h in headings
    ]
    ultimate = build_ultimate_sections(
        headings=headings,
        hierarchy=hierarchy,
        lines=lines,
        fragments=[],
        metadata_line_ids=set(),
        toc_seed_ids=set(),
    )
    headings_kept = [s["heading"] for s in ultimate["sections"]]
    assert "Chapter V Index" not in headings_kept
    assert "Punishment for Rape" in headings_kept
    assert ultimate["meta"]["low_grounding_dropped"] >= 1
