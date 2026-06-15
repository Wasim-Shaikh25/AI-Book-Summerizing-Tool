"""Tests for single-section parent-mirror collapse."""

from __future__ import annotations

from src.modules.structure.final_structuring.subheading_refinement import fix_parent_mirror_chapters


def _section(sid: str, heading: str, *, subs: list | None = None) -> dict:
    return {
        "section_id": sid,
        "heading": heading,
        "page_number": 5,
        "fragment": {"preview": f"Preview about {heading} and related topics."},
        "subheadings": subs or [],
    }


def test_single_section_mirror_promotes_subheadings() -> None:
    hierarchy = {
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Topic Alpha",
                "sections": [
                    _section(
                        "S1",
                        "Topic Alpha",
                        subs=[
                            {"topic_id": "S1_T1", "heading": "Subtopic One", "fragment": {"preview": "one"}},
                            {"topic_id": "S1_T2", "heading": "Subtopic Two", "fragment": {"preview": "two"}},
                        ],
                    )
                ],
            }
        ]
    }
    changed = fix_parent_mirror_chapters(hierarchy)
    ch = hierarchy["chapters"][0]
    assert changed >= 1
    assert ch["heading"] != "Topic Alpha" or len(ch.get("sections") or []) == 2
    if len(ch.get("sections") or []) == 2:
        assert ch["sections"][0]["heading"] == "Subtopic One"


def test_title_pdf_anchor_rejects_unanchored_llm_title() -> None:
    from types import SimpleNamespace

    from src.modules.structure.final_structuring.title_pdf_anchor import accept_edited_title

    lines = [
        SimpleNamespace(line_id=1, text="Local heading from source document", page_number=3),
    ]
    accepted = accept_edited_title(
        "Invented cloud title not in PDF",
        "Local heading from source document",
        lines=lines,
        page_number=3,
        require_strict=True,
    )
    assert accepted == "Local heading from source document"
