"""Tests for semantic stage catalog and legacy aliases."""

from __future__ import annotations

from src.modules.pipeline.stage_catalog import (
    LEGACY_FN_ALIASES,
    LOG_KEY_TO_SEMANTIC,
    PIPELINE_STAGES,
    STRUCTURE_LOGICAL_GROUPS,
    STRUCTURE_PHASES,
)
from src.modules.pipeline.stage_registry import PIPELINE_STAGE_FUNCTIONS, semantic_stage_id


def test_pipeline_stage_count() -> None:
    assert len(PIPELINE_STAGES) == 15
    assert len(PIPELINE_STAGE_FUNCTIONS) == 15


def test_structure_phases_grouped_without_gaps() -> None:
    all_keys = set()
    for keys in STRUCTURE_LOGICAL_GROUPS.values():
        all_keys |= keys
    phase_keys = {s.log_key for s in STRUCTURE_PHASES if s.log_key}
    assert all_keys == phase_keys
    assert len(STRUCTURE_PHASES) == 10


def test_legacy_fn_aliases_map_to_progress_functions() -> None:
    semantic_names = set(LEGACY_FN_ALIASES.values())
    for fn in PIPELINE_STAGE_FUNCTIONS:
        assert fn in semantic_names


def test_log_key_to_semantic_round_trip() -> None:
    assert LOG_KEY_TO_SEMANTIC["partition_sections"] == "partition_sections"
    assert semantic_stage_id("15j_hierarchy_openai") == "cloud_hierarchy"
    assert semantic_stage_id("group_chapters") == "group_chapters"


def test_legacy_log_key_normalization() -> None:
    from src.modules.pipeline.stage_catalog import normalize_log_key

    assert normalize_log_key("15e_chapter_hierarchy") == "group_chapters"
    assert normalize_log_key("15b_doubted_resolved") == "resolve_doubted_toc"
