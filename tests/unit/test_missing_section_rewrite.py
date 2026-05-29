"""Tests for auto-retry of missing rewrite sections."""
from __future__ import annotations

from src.modules.generation.missing_section_rewrite import retry_missing_sections


def test_retry_missing_sections_fills_gaps() -> None:
    hierarchy = {
        "chapters": [
            {
                "heading": "Ch",
                "sections": [
                    {"section_id": "S1", "heading": "One", "subheadings": []},
                    {"section_id": "S2", "heading": "Two", "subheadings": []},
                ],
            }
        ]
    }
    sections = [
        {"section_id": "S1", "heading": "One", "text": "alpha content here"},
        {"section_id": "S2", "heading": "Two", "text": "beta content here"},
    ]
    rewritten = {"S1": "notes-one"}

    def fake_generate(system: str, user: str) -> str:
        if "Section to rewrite: Two" in user:
            return "notes-two"
        return ""

    out, report = retry_missing_sections(
        hierarchy=hierarchy,
        rewritten=rewritten,
        sections=sections,
        user_instruction="short notes",
        generate=fake_generate,
        max_rounds=2,
    )
    assert out["S1"] == "notes-one"
    assert out["S2"] == "notes-two"
    assert report.ok
