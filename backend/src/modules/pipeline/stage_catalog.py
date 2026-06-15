"""Human-readable pipeline stage catalog (semantic log keys + legacy aliases).



Canonical log keys use semantic names (``group_chapters``, ``resolve_doubted_toc``).

On-disk artifact filenames (``s15e_…``, ``s15b_…``) stay stable for older run folders.

"""



from __future__ import annotations



from dataclasses import dataclass

from typing import Dict, FrozenSet, Tuple





@dataclass(frozen=True)

class StageSpec:

    """One pipeline step: semantic log key + display metadata."""



    semantic_id: str

    display_name: str

    log_key: str | None  # None = no JSON artifact (in-memory only)

    artifact_file: str | None

    phase: str

    logical_group: str

    purpose: str

    legacy_fn: str | None = None  # deprecated stages.py function name





# --- Top-level pipeline (stages.py) ---

PIPELINE_STAGES: Tuple[StageSpec, ...] = (

    StageSpec(

        "ingest_pdf",

        "Ingest PDF",

        None,

        None,

        "ingest",

        "ingest",

        "Extract text, layout, and visuals from the PDF (OCR when needed).",

        "stage_extract",

    ),

    StageSpec(

        "log_layout",

        "Log layout",

        "layout_lines",

        "s01_layout_lines.json",

        "ingest",

        "ingest",

        "Persist per-line layout metadata for structure stages.",

        "stage_layout_log",

    ),

    StageSpec(

        "filter_noise",

        "Filter noise",

        "noise_filter",

        "s02_noise_filter.json",

        "detect",

        "heading_detect",

        "Drop headers, footers, page numbers, and junk lines.",

        "stage_noise",

    ),

    StageSpec(

        "score_candidates",

        "Score heading candidates",

        "candidate_scoring",

        "s03_candidate_scoring.json",

        "detect",

        "heading_detect",

        "Score lines as potential section headings.",

        "stage_candidates",

    ),

    StageSpec(

        "gate_headings",

        "Validate heading candidates",

        "heading_validity_gate",

        "s04_heading_validity_gate.json",

        "detect",

        "heading_detect",

        "Reject statute fragments, syllabus noise, and weak candidates.",

        "stage_heading_gate",

    ),

    StageSpec(

        "filter_continuity",

        "Continuity filter",

        "continuity_filter",

        "s06_continuity_filter.json",

        "detect",

        "heading_detect",

        "Remove isolated false-positive headings using page continuity.",

        "stage_continuity",

    ),

    StageSpec(

        "build_fragments",

        "Build fragments",

        "fragments",

        "s05_fragments.json",

        "detect",

        "heading_detect",

        "Slice body text between headings into rewrite fragments.",

        "stage_fragments",

    ),

    StageSpec(

        "clean_toc",

        "Clean TOC headings",

        None,

        None,

        "toc",

        "toc",

        "Normalize table-of-contents heading candidates.",

        "stage_toc_clean",

    ),

    StageSpec(

        "detect_toc",

        "Detect TOC structure",

        "deterministic_toc",

        "s08_deterministic_toc.json",

        "toc",

        "toc",

        "Find TOC spans, PDF outline supplements, and metadata blocks.",

        "stage_deterministic_toc",

    ),

    StageSpec(

        "flag_doubted_toc",

        "Flag doubtful TOC",

        "doubted_sections",

        "s12_doubted_sections.json",

        "toc",

        "toc",

        "Mark late TOC / metadata lines that may be misclassified.",

        "stage_doubted_sections",

    ),

    StageSpec(

        "resolve_doubted_toc",

        "Resolve doubtful TOC",

        "resolve_doubted_toc",

        "s15b_doubted_resolved.json",

        "toc",

        "toc",

        "Revalidate or fast-resolve doubtful TOC/metadata segments.",

        "stage_15b_resolver",

    ),

    StageSpec(

        "finalize_headings",

        "Finalize heading list",

        "final_headings",

        "s07_final_headings.json",

        "detect",

        "heading_detect",

        "Emit full and TOC-stripped heading lists + book metadata.",

        "stage_finalize_headings",

    ),

    StageSpec(

        "validate_early_titles",

        "Early title validation",

        "heading_title_validation",

        "s13_heading_title_validation.json",

        "detect",

        "heading_detect",

        "Rules-based title filter before book structure.",

        "stage_heading_title_validation",

    ),

    StageSpec(

        "compute_document_profile",

        "Compute document profile",

        "document_profile",

        "s00_document_profile.json",

        "ingest",

        "ingest",

        "Measure document shape signals and derive universal tuning knobs.",

        "stage_compute_document_profile",

    ),

    StageSpec(

        "build_book_structure",

        "Build book structure",

        None,

        None,

        "structure",

        "structure",

        "Run consolidated structure phases (partition → chapters → titles → publish).",

        "stage_final_structuring",

    ),

)



# --- Final structure logical phases (structure_orchestrator.py) ---

STRUCTURE_PHASES: Tuple[StageSpec, ...] = (

    StageSpec(

        "partition_tree",

        "Partition heading tree",

        "partition_tree",

        "s15a_heading_hierarchy.json",

        "structure",

        "partition",

        "Nest validated headings into a parent/child tree.",

    ),

    StageSpec(

        "partition_sections",

        "Partition rewrite sections",

        "partition_sections",

        "s15d_ultimate_sections.json",

        "structure",

        "partition",

        "Size and nest sections for parallel LLM rewrite.",

    ),

    StageSpec(

        "group_chapters",

        "Group chapters",

        "group_chapters",

        "s15e_chapter_hierarchy.json",

        "structure",

        "chapters",

        "Assign sections to chapters (rules/MiniLM; optional cloud when profile allows).",

    ),

    StageSpec(

        "place_chapters",

        "Place & split chapters",

        "place_chapters",

        "s15h_chapter_placement.json",

        "structure",

        "chapters",

        "Split mega-chapters, rebalance by page order, reassign outliers.",

    ),

    StageSpec(

        "clean_titles",

        "Clean titles",

        "clean_titles",

        "s15f_heading_cleanup.json",

        "structure",

        "titles",

        "Disambiguate weak headings and drop generic labels (rules/MiniLM).",

    ),

    StageSpec(

        "refine_titles",

        "Refine titles",

        "refine_titles",

        "s15i_heading_refinement.json",

        "structure",

        "titles",

        "Fix verbose/mirrored section and subheading titles before rewrite.",

    ),

    StageSpec(

        "cloud_hierarchy",

        "Cloud hierarchy polish",

        "cloud_hierarchy",

        "s15j_hierarchy_openai.json",

        "structure",

        "titles",

        "Optional cloud regroup + name + polish when local output is insufficient.",

    ),

    StageSpec(

        "validate_titles",

        "Validate titles",

        "validate_titles",

        "s15g_title_validation.json",

        "structure",

        "publish",

        "Late rules safety net on chapter/section titles.",

    ),

    StageSpec(

        "assemble_book",

        "Assemble final book",

        "assemble_book",

        "s15c_final_book.json",

        "structure",

        "publish",

        "Merge hierarchy + sections into export-ready book JSON.",

    ),

    StageSpec(

        "rag_snapshot",

        "RAG snapshot",

        "rag_snapshot",

        "s16_rag_snapshot.json",

        "structure",

        "publish",

        "Section bodies for vector index build (no embeddings here).",

    ),

)



# Extra artifact for resolve-doubted revalidation audit (same TOC phase as resolve_doubted_toc).

STAGE_RESOLVE_DOUBTED_REVALIDATION = "resolve_doubted_revalidation"



# Old log keys (15a, 15b, …) → canonical semantic log key.

LEGACY_LOG_KEY_ALIASES: Dict[str, str] = {

    "15a_heading_hierarchy": "partition_tree",

    "15b_doubted_resolved": "resolve_doubted_toc",

    "15b_revalidation": STAGE_RESOLVE_DOUBTED_REVALIDATION,

    "15c_final_book": "assemble_book",

    "15d_ultimate_sections": "partition_sections",

    "15e_chapter_hierarchy": "group_chapters",

    "15f_heading_cleanup": "clean_titles",

    "15g_title_validation": "validate_titles",

    "15h_chapter_placement": "place_chapters",

    "15i_heading_refinement": "refine_titles",

    "15j_hierarchy_openai": "cloud_hierarchy",

    "16_rag_snapshot": "rag_snapshot",

}



# Map any log key → semantic_id for readers, UI, and audit reports.

LOG_KEY_TO_SEMANTIC: Dict[str, str] = {

    s.log_key: s.semantic_id for s in (*PIPELINE_STAGES, *STRUCTURE_PHASES) if s.log_key

}

LOG_KEY_TO_SEMANTIC[STAGE_RESOLVE_DOUBTED_REVALIDATION] = "resolve_doubted_revalidation"

for legacy, canonical in LEGACY_LOG_KEY_ALIASES.items():

    LOG_KEY_TO_SEMANTIC[legacy] = LOG_KEY_TO_SEMANTIC.get(canonical, canonical)



# Four consolidated structure groups (documentation + progress).

STRUCTURE_LOGICAL_GROUPS: Dict[str, FrozenSet[str]] = {

    "partition": frozenset({"partition_tree", "partition_sections"}),

    "chapters": frozenset({"group_chapters", "place_chapters"}),

    "titles": frozenset({"clean_titles", "refine_titles", "cloud_hierarchy"}),

    "publish": frozenset({"validate_titles", "assemble_book", "rag_snapshot"}),

}



# Legacy stages.py function → semantic pipeline function name.

LEGACY_FN_ALIASES: Dict[str, str] = {

    "stage_extract": "stage_ingest_pdf",

    "stage_layout_log": "stage_log_layout",

    "stage_noise": "stage_filter_noise",

    "stage_candidates": "stage_score_heading_candidates",

    "stage_heading_gate": "stage_gate_heading_candidates",

    "stage_continuity": "stage_filter_continuity",

    "stage_fragments": "stage_build_fragments",

    "stage_toc_clean": "stage_clean_toc",

    "stage_deterministic_toc": "stage_detect_toc",

    "stage_doubted_sections": "stage_flag_doubted_toc",

    "stage_15b_resolver": "stage_resolve_doubted_toc",

    "stage_finalize_headings": "stage_finalize_heading_list",

    "stage_heading_title_validation": "stage_validate_early_titles",

    "stage_compute_document_profile": "stage_compute_document_profile",

    "stage_final_structuring": "stage_build_book_structure",

}



SEMANTIC_FN_TO_LEGACY: Dict[str, str] = {v: k for k, v in LEGACY_FN_ALIASES.items()}





def normalize_log_key(stage_key: str) -> str:

    """Resolve legacy ``15e_chapter_hierarchy`` style keys to semantic names."""

    return LEGACY_LOG_KEY_ALIASES.get(stage_key, stage_key)


