from __future__ import annotations

from pathlib import Path

import pytest

from src.modules.pipeline.stage_registry import (
    ALLOWED_LOG_FILES,
    CORE_STAGE_FILES,
    LEGACY_STAGE_LOG_FILES,
    STAGE_CLOUD_HIERARCHY,
    STAGE_LOG_FILES,
    STAGE_RESOLVE_DOUBTED_REVALIDATION,
    STAGE_VALIDATE_TITLES,
    artifact_path,
    require_artifact,
    resolve_chapter_hierarchy_artifact,
    resolve_existing_artifact,
    stage_log_filename,
)


def test_stage_log_files_are_unique() -> None:
    filenames = list(STAGE_LOG_FILES.values())
    assert len(filenames) == len(set(filenames))


def test_allowed_log_files_matches_registry_values() -> None:
    assert ALLOWED_LOG_FILES == frozenset(STAGE_LOG_FILES.values())


def test_core_stage_files_subset_of_allowed() -> None:
    assert CORE_STAGE_FILES <= ALLOWED_LOG_FILES


def test_canonical_stage_filenames_use_s_prefix() -> None:
    assert stage_log_filename("layout_lines") == "s01_layout_lines.json"
    assert stage_log_filename("partition_sections") == "s15d_ultimate_sections.json"
    assert stage_log_filename("resolve_doubted_toc") == "s15b_doubted_resolved.json"


def test_legacy_log_keys_still_resolve_filenames() -> None:
    assert stage_log_filename("15e_chapter_hierarchy") == "s15e_chapter_hierarchy.json"
    assert stage_log_filename("15b_revalidation") == "s15b_revalidation.json"


def test_renamed_resolve_doubted_stage_keys() -> None:
    assert stage_log_filename(STAGE_RESOLVE_DOUBTED_REVALIDATION) == "s15b_revalidation.json"


def test_legacy_stage_keys_removed() -> None:
    for legacy in (
        "doubted_resolved",
        "revalidation",
        "llm_heading_validation",
        "llm_toc_classification",
        "hierarchy",
        "toc_candidate_gate",
    ):
        with pytest.raises(ValueError, match="Unknown pipeline stage log key"):
            stage_log_filename(legacy)


def test_no_legacy_artifact_filenames_in_canonical_registry() -> None:
    legacy_only = {
        "04_llm_heading_validation.json",
        "04b_toc_candidate_gate.json",
        "05_llm_toc_classification.json",
        "06_toc_section_eval.json",
        "08_hierarchy.json",
        "decision_trace.json",
    }
    assert legacy_only.isdisjoint(ALLOWED_LOG_FILES)


def test_resolve_existing_artifact_prefers_canonical(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    canonical = run_dir / stage_log_filename("partition_sections")
    legacy = run_dir / LEGACY_STAGE_LOG_FILES["partition_sections"]
    legacy.write_text("{}", encoding="utf-8")
    assert resolve_existing_artifact(run_dir, "partition_sections") == legacy
    canonical.write_text("{}", encoding="utf-8")
    assert resolve_existing_artifact(run_dir, "partition_sections") == canonical
    assert resolve_existing_artifact(run_dir, "15d_ultimate_sections") == canonical


def test_artifact_path_for_write_uses_canonical(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    path = artifact_path(run_dir, "fragments", for_write=True)
    assert path.name == "s05_fragments.json"


def test_require_artifact_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        require_artifact(tmp_path, "fragments")


def test_resolve_chapter_hierarchy_prefers_cloud_over_validate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    g = run_dir / stage_log_filename(STAGE_VALIDATE_TITLES)
    j = run_dir / stage_log_filename(STAGE_CLOUD_HIERARCHY)
    g.write_text("{}", encoding="utf-8")
    j.write_text("{}", encoding="utf-8")
    assert resolve_chapter_hierarchy_artifact(run_dir) == j
