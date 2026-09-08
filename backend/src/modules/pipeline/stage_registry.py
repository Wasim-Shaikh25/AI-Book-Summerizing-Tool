"""Single source of truth: pipeline stage log keys → JSON artifact filenames."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, FrozenSet, Optional

from src.modules.pipeline.stage_catalog import (
    STAGE_RESOLVE_DOUBTED_REVALIDATION,
    normalize_log_key,
)

# Canonical log key → artifact file under {LOGS_FOLDER}/run_<id>/
# Semantic keys (``group_chapters``, ``resolve_doubted_toc``) are canonical.
# On-disk filenames keep the s15* prefix for backward compatibility with old runs.
STAGE_LOG_FILES: Dict[str, str] = {
    # --- Measured document profile (s00) ---
    "document_profile": "s00_document_profile.json",
    # --- Ingestion + deterministic structure (s01–s13) ---
    "layout_lines": "s01_layout_lines.json",
    "noise_filter": "s02_noise_filter.json",
    "candidate_scoring": "s03_candidate_scoring.json",
    "heading_validity_gate": "s04_heading_validity_gate.json",
    "fragments": "s05_fragments.json",
    "continuity_filter": "s06_continuity_filter.json",
    "final_headings": "s07_final_headings.json",
    "deterministic_toc": "s08_deterministic_toc.json",
    "book_metadata": "s09_book_metadata.json",
    "final_headings_2": "s10_final_headings_2.json",
    "visual_elements": "s11_visual_elements.json",
    "doubted_sections": "s12_doubted_sections.json",
    "heading_title_validation": "s13_heading_title_validation.json",
    "validated_headings": "s13b_validated_headings.json",
    # --- TOC resolution (legacy files s15b_*) ---
    "resolve_doubted_toc": "s15b_doubted_resolved.json",
    STAGE_RESOLVE_DOUBTED_REVALIDATION: "s15b_revalidation.json",
    # --- Book structure (legacy files s15a–s15j, s16) ---
    "partition_tree": "s15a_heading_hierarchy.json",
    "partition_sections": "s15d_ultimate_sections.json",
    "group_chapters": "s15e_chapter_hierarchy.json",
    "place_chapters": "s15h_chapter_placement.json",
    "clean_titles": "s15f_heading_cleanup.json",
    "refine_titles": "s15i_heading_refinement.json",
    "cloud_hierarchy": "s15j_hierarchy_openai.json",
    "synced_hierarchy": "s15k_synced_hierarchy.json",
    "validate_titles": "s15g_title_validation.json",
    "assemble_book": "s15c_final_book.json",
    "rag_snapshot": "s16_rag_snapshot.json",
}

# Pre-rename filenames (read fallback for older run folders).
LEGACY_STAGE_LOG_FILES: Dict[str, str] = {
    "layout_lines": "01_layout_lines.json",
    "noise_filter": "02_noise_filter.json",
    "candidate_scoring": "03_candidate_scoring.json",
    "heading_validity_gate": "03b_heading_validity_gate.json",
    "fragments": "07_fragments.json",
    "continuity_filter": "08b_continuity_filter.json",
    "final_headings": "09_final_headings.json",
    "deterministic_toc": "10_deterministic_toc.json",
    "book_metadata": "11_book_metadata.json",
    "final_headings_2": "12_final_headings_2.json",
    "visual_elements": "13_visual_elements.json",
    "doubted_sections": "14_doubted_sections.json",
    "resolve_doubted_toc": "15b_doubted_resolved.json",
    STAGE_RESOLVE_DOUBTED_REVALIDATION: "15b_revalidation.json",
    "partition_tree": "15a_heading_hierarchy.json",
    "assemble_book": "15c_final_book.json",
    "partition_sections": "15d_ultimate_sections.json",
    "group_chapters": "15e_chapter_hierarchy.json",
    "clean_titles": "15f_heading_cleanup.json",
    "rag_snapshot": "16_rag_snapshot.json",
}

ALLOWED_LOG_FILES: FrozenSet[str] = frozenset(STAGE_LOG_FILES.values())

# Subset produced on every full pipeline run (sample PDF integration contract).
CORE_STAGE_FILES: FrozenSet[str] = frozenset(
    {
        "s01_layout_lines.json",
        "s02_noise_filter.json",
        "s03_candidate_scoring.json",
        "s04_heading_validity_gate.json",
        "s05_fragments.json",
        "s06_continuity_filter.json",
        "s07_final_headings.json",
        "s08_deterministic_toc.json",
        "s09_book_metadata.json",
        "s10_final_headings_2.json",
        "s11_visual_elements.json",
        "s12_doubted_sections.json",
        "s13_heading_title_validation.json",
    }
)

# --- Semantic stage log keys (preferred in code) ---
STAGE_DOCUMENT_PROFILE = "document_profile"
STAGE_PARTITION_TREE = "partition_tree"
STAGE_RESOLVE_DOUBTED_TOC = "resolve_doubted_toc"
STAGE_PARTITION_SECTIONS = "partition_sections"
STAGE_GROUP_CHAPTERS = "group_chapters"
STAGE_PLACE_CHAPTERS = "place_chapters"
STAGE_CLEAN_TITLES = "clean_titles"
STAGE_REFINE_TITLES = "refine_titles"
STAGE_CLOUD_HIERARCHY = "cloud_hierarchy"
STAGE_VALIDATE_TITLES = "validate_titles"
STAGE_ASSEMBLE_BOOK = "assemble_book"
STAGE_RAG_SNAPSHOT = "rag_snapshot"

# Deprecated numeric aliases — still accepted by normalize_log_key().
STAGE_15A = STAGE_PARTITION_TREE
STAGE_15B = STAGE_RESOLVE_DOUBTED_TOC
STAGE_15B_REVALIDATION = STAGE_RESOLVE_DOUBTED_REVALIDATION
STAGE_15C = STAGE_ASSEMBLE_BOOK
STAGE_15D = STAGE_PARTITION_SECTIONS
STAGE_15E = STAGE_GROUP_CHAPTERS
STAGE_15F = STAGE_CLEAN_TITLES
STAGE_15G = STAGE_VALIDATE_TITLES
STAGE_15H = STAGE_PLACE_CHAPTERS
STAGE_15I = STAGE_REFINE_TITLES
STAGE_15J = STAGE_CLOUD_HIERARCHY
STAGE_16 = STAGE_RAG_SNAPSHOT

# Per-stage upload progress: (function_name, progress_id, message, percent).
PIPELINE_STAGE_PROGRESS: tuple[tuple[str, str, int, str], ...] = (
    ("stage_ingest_pdf", "ingest", 5, "Ingesting PDF (text, layout, OCR)…"),
    ("stage_log_layout", "layout", 10, "Logging page layout…"),
    ("stage_filter_noise", "noise", 15, "Filtering noise lines…"),
    ("stage_score_heading_candidates", "candidates", 22, "Scoring heading candidates…"),
    ("stage_gate_heading_candidates", "gate", 30, "Validating heading candidates…"),
    ("stage_filter_continuity", "continuity", 36, "Applying continuity filter…"),
    ("stage_build_fragments", "fragments", 42, "Building text fragments…"),
    ("stage_clean_toc", "toc", 48, "Cleaning table of contents…"),
    ("stage_detect_toc", "toc", 52, "Detecting TOC structure…"),
    ("stage_flag_doubted_toc", "toc", 58, "Flagging doubtful TOC sections…"),
    ("stage_resolve_doubted_toc", "toc", 64, "Resolving doubtful TOC…"),
    ("stage_finalize_heading_list", "finalize", 72, "Finalizing heading list…"),
    ("stage_validate_early_titles", "validate", 78, "Early title validation (rules)…"),
    ("stage_compute_document_profile", "profile", 82, "Computing document profile…"),
    ("stage_build_book_structure", "structure", 88, "Building book structure (chapters + titles)…"),
)

_PROGRESS_BY_FN = {row[0]: (row[1], row[3], row[2]) for row in PIPELINE_STAGE_PROGRESS}


def stage_progress_for(fn_name: str) -> tuple[str, str, int] | None:
    """Return (stage_id, message, percent) for a pipeline stage function name."""
    from src.modules.pipeline.stage_catalog import LEGACY_FN_ALIASES

    resolved = LEGACY_FN_ALIASES.get(fn_name, fn_name)
    return _PROGRESS_BY_FN.get(resolved) or _PROGRESS_BY_FN.get(fn_name)


def semantic_stage_id(log_key: str) -> str:
    """Map a log key (semantic or legacy) to its human-readable semantic ID."""
    from src.modules.pipeline.stage_catalog import LOG_KEY_TO_SEMANTIC

    return LOG_KEY_TO_SEMANTIC.get(normalize_log_key(log_key), log_key)


PIPELINE_STAGE_FUNCTIONS: tuple[str, ...] = tuple(row[0] for row in PIPELINE_STAGE_PROGRESS)


def get_pipeline_stages():
    """Return ordered stage callables from ``stages.py``."""
    from src.modules.pipeline import stages as stages_mod

    return [getattr(stages_mod, name) for name in PIPELINE_STAGE_FUNCTIONS]


def stage_log_filename(stage_key: str) -> str:
    """Return canonical JSON filename for a stage log key."""
    key = normalize_log_key(stage_key)
    try:
        return STAGE_LOG_FILES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown pipeline stage log key: {stage_key}") from exc


def artifact_path(run_dir: Path | str, stage_key: str, *, for_write: bool = False) -> Path:
    """Resolve artifact path under a run directory."""
    key = normalize_log_key(stage_key)
    base = Path(run_dir)
    canonical = base / stage_log_filename(key)
    if for_write:
        return canonical
    if canonical.exists():
        return canonical
    legacy_name = LEGACY_STAGE_LOG_FILES.get(key)
    if legacy_name:
        legacy = base / legacy_name
        if legacy.exists():
            return legacy
    return canonical


def resolve_existing_artifact(run_dir: Path | str, stage_key: str) -> Optional[Path]:
    """Return path if canonical or legacy artifact exists; else None."""
    key = normalize_log_key(stage_key)
    base = Path(run_dir)
    canonical = base / stage_log_filename(key)
    if canonical.exists():
        return canonical
    legacy_name = LEGACY_STAGE_LOG_FILES.get(key)
    if legacy_name:
        legacy = base / legacy_name
        if legacy.exists():
            return legacy
    return None


def resolve_chapter_hierarchy_artifact(run_dir: Path | str) -> Optional[Path]:
    """Prefer latest hierarchy polish: cloud → refine → place → clean → validate → group."""
    for stage_key in (
        STAGE_CLOUD_HIERARCHY,
        STAGE_REFINE_TITLES,
        STAGE_PLACE_CHAPTERS,
        STAGE_CLEAN_TITLES,
        STAGE_VALIDATE_TITLES,
        STAGE_GROUP_CHAPTERS,
    ):
        path = resolve_existing_artifact(run_dir, stage_key)
        if path is not None:
            return path
    return None


def require_artifact(run_dir: Path | str, stage_key: str) -> Path:
    """Return canonical or legacy artifact path; raise if missing."""
    path = resolve_existing_artifact(run_dir, stage_key)
    if path is None:
        key = normalize_log_key(stage_key)
        raise FileNotFoundError(
            f"Missing stage artifact {stage_key!r} under {Path(run_dir)} "
            f"(expected {stage_log_filename(key)} or legacy name)"
        )
    return path
