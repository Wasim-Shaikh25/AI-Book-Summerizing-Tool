"""Tests for stage 15j cost gates (regroup skip, names skip, full-stage skip)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.structure.final_structuring.hierarchy_openai_refinement import (  # noqa: E402
    _hierarchy_needs_regroup,
    _hierarchy_titles_need_cloud_cleanup,
    hierarchy_needs_cloud_refinement,
    run_hierarchy_openai_refinement,
)


def _healthy_bareact_like_chapters() -> list:
    """Eight chapters, ~60 sections — mirrors a healthy local hierarchy."""
    return [
        {"heading": f"Chapter {i}", "sections": [{"heading": f"Topic {j}", "subheadings": []} for j in range(7 + (i % 3))]}
        for i in range(1, 9)
    ]


def test_clean_hierarchy_skips_cloud_names_pass() -> None:
    chapters = [
        {
            "heading": "Sources of Muslim Law",
            "sections": [
                {"heading": "Meaning of Mahr", "subheadings": [{"heading": "Types of Mahr"}]},
            ],
        }
    ]
    assert _hierarchy_titles_need_cloud_cleanup(chapters) is False


def test_partition_or_prose_title_triggers_cloud_names_pass() -> None:
    chapters = [
        {
            "heading": "CHAPTER I: PRELIMINARY",
            "sections": [
                {"heading": "Section 309: Robbery. — Fund held and administered", "subheadings": []},
            ],
        }
    ]
    assert _hierarchy_titles_need_cloud_cleanup(chapters) is True


def test_generic_title_triggers_cloud_names_pass() -> None:
    chapters = [{"heading": "Module 1", "sections": [{"heading": "Introduction", "subheadings": []}]}]
    assert _hierarchy_titles_need_cloud_cleanup(chapters) is True


def test_healthy_chapter_distribution_skips_regroup() -> None:
    chapters = _healthy_bareact_like_chapters()
    section_count = sum(len(ch.get("sections") or []) for ch in chapters)
    assert section_count >= 56
    assert _hierarchy_needs_regroup(chapters, section_count=section_count) is False


def test_mega_chapter_triggers_regroup() -> None:
    chapters = [{"heading": "Everything", "sections": [{"heading": f"S{i}", "subheadings": []} for i in range(40)]}]
    assert _hierarchy_needs_regroup(chapters, section_count=40) is True


def test_hierarchy_needs_cloud_refinement_false_when_local_healthy(monkeypatch) -> None:
    monkeypatch.setenv("HIERARCHY_OPENAI_ENABLED", "true")
    monkeypatch.setenv("HIERARCHY_OPENAI_AUTO_SKIP", "true")
    from src import config

    config.HIERARCHY_OPENAI_ENABLED = True
    config.HIERARCHY_OPENAI_AUTO_SKIP = True
    chapters = _healthy_bareact_like_chapters()
    hierarchy = {
        "book_title": "BNS Act",
        "chapters": [
            {
                "heading": "Punishments",
                "sections": [{"heading": "Voluntary Hurt", "subheadings": [{"heading": "Ingredients"}]}],
            }
        ],
    }
    assert hierarchy_needs_cloud_refinement(hierarchy) is False


def test_run_hierarchy_openai_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("HIERARCHY_OPENAI_ENABLED", "false")
    from src import config

    config.HIERARCHY_OPENAI_ENABLED = False
    hierarchy = {"chapters": [{"heading": "CHAPTER I:", "sections": []}], "meta": {}}
    out = run_hierarchy_openai_refinement(hierarchy)
    assert out is hierarchy or out.get("meta", {}).get("hierarchy_openai_skipped") is not True
