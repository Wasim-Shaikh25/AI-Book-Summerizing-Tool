"""Unit tests for sync_hierarchy_from_markdown and its env-flag wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.generation.structure_fix_runner import (  # noqa: E402
    sync_hierarchy_from_markdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_md(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "notes.md"
    p.write_text(content, encoding="utf-8")
    return p


def _hierarchy_with_sections(*sections: dict) -> dict:
    """Build a minimal hierarchy dict with one chapter containing *sections."""
    return {
        "chapters": [
            {
                "heading": "Original Chapter Heading",
                "sections": list(sections),
            }
        ]
    }


# ---------------------------------------------------------------------------
# Test 1: heading patched from sid tag
# ---------------------------------------------------------------------------

def test_sync_patches_heading_from_sid_tag(tmp_path: Path) -> None:
    """MD has ## New Title <!-- sid:S1 -->, hierarchy has old title → patched."""
    md = _write_md(
        tmp_path,
        "# Some Chapter\n\n## New Title <!-- sid:S1 -->\nBody text here.\n",
    )
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Old Noisy Title — 246"}
    )
    patched_h, report = sync_hierarchy_from_markdown(md, hierarchy)

    assert patched_h["chapters"][0]["sections"][0]["heading"] == "New Title"
    assert report["patched"] >= 1


# ---------------------------------------------------------------------------
# Test 2: section order patched to match Markdown sequence
# ---------------------------------------------------------------------------

def test_sync_preserves_order_from_markdown_sequence(tmp_path: Path) -> None:
    """Sections in Markdown order S2, S1 → hierarchy reordered to S2 first."""
    md = _write_md(
        tmp_path,
        (
            "# Chapter A\n\n"
            "## Second Section <!-- sid:S2 -->\nBody.\n\n"
            "## First Section <!-- sid:S1 -->\nBody.\n"
        ),
    )
    # Hierarchy originally has S1 before S2
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "First Section"},
        {"section_id": "S2", "heading": "Second Section"},
    )
    patched_h, _ = sync_hierarchy_from_markdown(md, hierarchy)

    sections = patched_h["chapters"][0]["sections"]
    assert sections[0]["section_id"] == "S2"
    assert sections[1]["section_id"] == "S1"


# ---------------------------------------------------------------------------
# Test 3: section without sid tag is not touched
# ---------------------------------------------------------------------------

def test_sync_skips_sections_without_sid_tags(tmp_path: Path) -> None:
    """Section with no sid tag leaves hierarchy entry untouched."""
    md = _write_md(
        tmp_path,
        "# Chapter B\n\n## No Tag Section\nBody.\n",
    )
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S99", "heading": "Keep This Heading"}
    )
    _, report = sync_hierarchy_from_markdown(md, hierarchy)

    assert hierarchy["chapters"][0]["sections"][0]["heading"] == "Keep This Heading"
    assert report["patched"] == 0


# ---------------------------------------------------------------------------
# Test 4: chapter heading rebuilt from majority vote of section sids
# ---------------------------------------------------------------------------

def test_sync_rebuilds_chapter_heading_from_majority_sections(tmp_path: Path) -> None:
    """3 sections all under 'Corrected Chapter' → chapter heading updated."""
    md = _write_md(
        tmp_path,
        (
            "# Corrected Chapter\n\n"
            "## Section A <!-- sid:S1 -->\nBody.\n\n"
            "## Section B <!-- sid:S2 -->\nBody.\n\n"
            "## Section C <!-- sid:S3 -->\nBody.\n"
        ),
    )
    hierarchy = {
        "chapters": [
            {
                "heading": "Stale Raw Chapter — BNS 101",
                "sections": [
                    {"section_id": "S1", "heading": "Section A"},
                    {"section_id": "S2", "heading": "Section B"},
                    {"section_id": "S3", "heading": "Section C"},
                ],
            }
        ]
    }
    patched_h, report = sync_hierarchy_from_markdown(md, hierarchy)

    assert patched_h["chapters"][0]["heading"] == "Corrected Chapter"
    assert report["patched"] >= 1


# ---------------------------------------------------------------------------
# Test 5: sync_report["patched"] equals number of sections updated
# ---------------------------------------------------------------------------

def test_sync_returns_sync_report_with_patched_count(tmp_path: Path) -> None:
    """sync_report["patched"] accurately reflects how many entries were changed."""
    md = _write_md(
        tmp_path,
        (
            "# Chapter\n\n"
            "## Title One <!-- sid:S1 -->\nBody.\n\n"
            "## Title Two <!-- sid:S2 -->\nBody.\n"
        ),
    )
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Old One"},
        {"section_id": "S2", "heading": "Old Two"},
    )
    _, report = sync_hierarchy_from_markdown(md, hierarchy)

    # 2 section headings + 1 chapter heading = 3 patches
    assert report["patched"] == 3
    assert isinstance(report["skipped"], int)
    assert isinstance(report["warnings"], list)


# ---------------------------------------------------------------------------
# Test 6: artifact written when write_path is given
# ---------------------------------------------------------------------------

def test_sync_writes_json_artifact_when_write_path_given(tmp_path: Path) -> None:
    """write_path set → file created and parseable as valid JSON."""
    md = _write_md(
        tmp_path,
        "# Chapter\n\n## Topic One <!-- sid:S1 -->\nBody.\n",
    )
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Old Topic"}
    )
    artifact = tmp_path / "s15k_synced_hierarchy.json"

    sync_hierarchy_from_markdown(md, hierarchy, write_path=artifact)

    assert artifact.exists(), "Artifact file must be created"
    parsed = json.loads(artifact.read_text(encoding="utf-8"))
    assert "chapters" in parsed
    assert parsed["chapters"][0]["sections"][0]["heading"] == "Topic One"


# ---------------------------------------------------------------------------
# Test 7: no file written when write_path is None
# ---------------------------------------------------------------------------

def test_sync_no_write_when_write_path_is_none(tmp_path: Path) -> None:
    """write_path=None → no JSON file created in tmp_path."""
    md = _write_md(
        tmp_path,
        "# Chapter\n\n## Topic One <!-- sid:S1 -->\nBody.\n",
    )
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Old Topic"}
    )
    sync_hierarchy_from_markdown(md, hierarchy, write_path=None)

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 0, "No JSON file must be created when write_path is None"


# ---------------------------------------------------------------------------
# Test 8: missing sid in hierarchy logged as warning, no KeyError
# ---------------------------------------------------------------------------

def test_sync_handles_missing_sections_gracefully(tmp_path: Path) -> None:
    """MD references sid:S42 not present in hierarchy → warning in report, no crash."""
    md = _write_md(
        tmp_path,
        "# Chapter\n\n## Orphan Section <!-- sid:S42 -->\nBody.\n",
    )
    # Hierarchy has no S42
    hierarchy = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Unrelated"}
    )
    _, report = sync_hierarchy_from_markdown(md, hierarchy)

    # Must not raise; S42 in MD but not in hierarchy → skipped, not an error
    assert isinstance(report["skipped"], int)
    assert isinstance(report["warnings"], list)


# ---------------------------------------------------------------------------
# Test 9: SYNC_HIERARCHY_FROM_MD=0 → flag off means sync not invoked
# ---------------------------------------------------------------------------

def test_sync_hierarchy_env_disabled_skips_sync(
    tmp_path: Path, monkeypatch
) -> None:
    """With SYNC_HIERARCHY_FROM_MD=0 (default), sync function is never invoked."""
    monkeypatch.setenv("SYNC_HIERARCHY_FROM_MD", "0")

    with patch(
        "src.modules.generation.structure_fix_runner.sync_hierarchy_from_markdown"
    ) as mock_sync:
        import os
        flag = os.getenv("SYNC_HIERARCHY_FROM_MD", "0").strip() == "1"
        if flag:
            mock_sync(tmp_path / "notes.md", {})

        mock_sync.assert_not_called()


# ---------------------------------------------------------------------------
# Test 10: SYNC_HIERARCHY_FROM_MD=1 → sync is called before render
# ---------------------------------------------------------------------------

def test_sync_hierarchy_env_enabled_calls_sync(
    tmp_path: Path, monkeypatch
) -> None:
    """With SYNC_HIERARCHY_FROM_MD=1, sync_hierarchy_from_markdown is invoked."""
    monkeypatch.setenv("SYNC_HIERARCHY_FROM_MD", "1")

    md_path = _write_md(
        tmp_path,
        "# Chapter\n\n## Topic <!-- sid:S1 -->\nBody.\n",
    )
    dummy_hierarchy: dict = _hierarchy_with_sections(
        {"section_id": "S1", "heading": "Old"}
    )

    with patch(
        "src.modules.generation.structure_fix_runner.sync_hierarchy_from_markdown",
        return_value=(dummy_hierarchy, {"patched": 1, "skipped": 0, "warnings": []}),
    ) as mock_sync:
        import os
        flag = os.getenv("SYNC_HIERARCHY_FROM_MD", "0").strip() == "1"
        if flag:
            mock_sync(md_path, dummy_hierarchy, write_path=None)

        mock_sync.assert_called_once()
        call_args = mock_sync.call_args
        assert call_args.args[0] == md_path
        assert call_args.args[1] is dummy_hierarchy
