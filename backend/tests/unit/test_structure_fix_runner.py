"""Unit tests for pipeline structural-fix runner."""
from __future__ import annotations

import json

from src.modules.generation.structure_fix_runner import (
    propagate_titles_to_hierarchy,
    resolve_structure_fix_engine,
    run_structure_fix,
    structure_fix_enabled,
)


def test_structure_fix_enabled_default(monkeypatch) -> None:
    monkeypatch.delenv("NOTES_STRUCTURE_FIX_ENABLED", raising=False)
    assert structure_fix_enabled() is True


def test_resolve_structure_fix_engine_hybrid_default(monkeypatch) -> None:
    monkeypatch.delenv("NOTES_STRUCTURE_FIX_ENGINE", raising=False)
    assert resolve_structure_fix_engine() == "hybrid"


def test_run_structure_fix_renumbers_lists_offline() -> None:
    md = (
        "# Chapter One\n\n"
        "## Topic A <!-- sid:S1 -->\n"
        "1. One\n"
        "2. Two\n\n"
        "## Topic B <!-- sid:S2 -->\n"
        "6. Six\n"
        "7. Seven\n"
    )
    out, report = run_structure_fix(md, engine="minilm", log_dir=None)
    assert "1. Six" in out
    assert "2. Seven" in out
    assert report.engine == "minilm"


_FIXED_MD = (
    "# Banking Offences\n\n"
    "## Counterfeiting Bank Notes <!-- sid:S1 -->\n"
    "Body about counterfeiting.\n\n"
    "## Government Stamp Misuse <!-- sid:S2 -->\n"
    "Body about stamps.\n"
)


def test_propagate_titles_updates_in_memory_hierarchy() -> None:
    hierarchy = {
        "chapters": [
            {
                "heading": "CHAPTER X — 246 to 249, 255",
                "sections": [
                    {"section_id": "S1", "heading": "BANK-NOTES, AND GOVERNMENT STAMPS — 246"},
                    {"section_id": "S2", "heading": "Section topic — 255"},
                ],
            }
        ]
    }
    updated = propagate_titles_to_hierarchy(_FIXED_MD, hierarchy)
    assert updated == 3  # chapter + 2 sections
    ch = hierarchy["chapters"][0]
    assert ch["heading"] == "Banking Offences"
    assert ch["sections"][0]["heading"] == "Counterfeiting Bank Notes"
    assert ch["sections"][1]["heading"] == "Government Stamp Misuse"


def test_propagate_titles_rewrites_on_disk_artifact(tmp_path) -> None:
    artifact = tmp_path / "s15j_hierarchy_openai.json"
    artifact.write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "heading": "raw noisy chapter — 246",
                        "sections": [
                            {"section_id": "S1", "heading": "raw noisy 246"},
                            {"section_id": "S2", "heading": "raw noisy 255"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    propagate_titles_to_hierarchy(_FIXED_MD, None, hierarchy_path=artifact)
    disk = json.loads(artifact.read_text(encoding="utf-8"))
    secs = disk["chapters"][0]["sections"]
    assert disk["chapters"][0]["heading"] == "Banking Offences"
    assert secs[0]["heading"] == "Counterfeiting Bank Notes"
    assert secs[1]["heading"] == "Government Stamp Misuse"


def test_propagate_titles_matches_chapter_by_section_vote() -> None:
    # On-disk chapter order differs from Markdown; sid vote still picks right title.
    hierarchy = {
        "chapters": [
            {
                "heading": "reordered chapter",
                "sections": [
                    {"section_id": "S2", "heading": "noisy"},
                    {"section_id": "S1", "heading": "noisy"},
                ],
            }
        ]
    }
    propagate_titles_to_hierarchy(_FIXED_MD, hierarchy)
    assert hierarchy["chapters"][0]["heading"] == "Banking Offences"


def test_propagate_titles_noop_when_no_match() -> None:
    hierarchy = {
        "chapters": [
            {"heading": "Untouched", "sections": [{"section_id": "S9", "heading": "Keep Me"}]}
        ]
    }
    updated = propagate_titles_to_hierarchy(_FIXED_MD, hierarchy)
    assert updated == 0
    assert hierarchy["chapters"][0]["sections"][0]["heading"] == "Keep Me"
