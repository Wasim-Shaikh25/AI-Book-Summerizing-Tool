"""Configuration loader — YAML defaults + env + .env overlay.

Authoritative spec: /spec/modules/parameters-config.md
MESO Rule 12: tunables live in /config/default.yaml, not in business logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.shared.errors import ConfigError

try:
    import yaml  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(_BACKEND_ROOT.parent)))
_CONFIG_DIR = _BACKEND_ROOT / "config"
_DEFAULT_YAML = _CONFIG_DIR / "default.yaml"

_PROVIDER_ALIASES = {"CHATGPT": "OPENAI"}
_PROVIDER_TO_BACKEND = {
    "OPENAI": "openai",
    "OPENROUTER": "openrouter",
}


def _require_yaml() -> None:
    if yaml is None:
        raise ConfigError(
            "PyYAML is required to load configuration. Install with `pip install PyYAML`.",
            ctx={"package": "PyYAML"},
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    _require_yaml()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Expected mapping in {path}")
    return data


def _load_dotenv_value(key: str) -> str:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() != key:
                continue
            return v.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _env(key: str, default: str = "") -> str:
    return os.getenv(key) or _load_dotenv_value(key) or default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _normalize_llm_provider(raw: str) -> str:
    p = (raw or "OPENAI").strip().upper()
    return _PROVIDER_ALIASES.get(p, p)


def _cfg_get(cfg: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node: Any = cfg
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key, default)
        if node is default and key != keys[-1]:
            return default
    return node if node is not None else default


_YAML = _load_yaml(_DEFAULT_YAML)

# Paths
BASE_DIR = str(_PROJECT_ROOT)
PDF_FOLDER = str(_PROJECT_ROOT / _cfg_get(_YAML, "paths", "pdf_folder", default="pdfs"))
OUTPUT_FOLDER = str(_PROJECT_ROOT / _cfg_get(_YAML, "paths", "output_folder", default="output"))
LOGS_FOLDER = str(_PROJECT_ROOT / _cfg_get(_YAML, "paths", "logs_folder", default="logs"))
REFERENCE_DOCX_PATH = str(_PROJECT_ROOT / _cfg_get(_YAML, "paths", "reference_docx", default="reference.docx"))
MODELS_DIR = str(_PROJECT_ROOT / _cfg_get(_YAML, "paths", "models_dir", default="models"))
KNOWLEDGE_DB_PATH = str(Path(OUTPUT_FOLDER) / "knowledge_base.db")
EXPORTS_FOLDER = str(Path(OUTPUT_FOLDER) / "exports")
UPLOADS_FOLDER = str(Path(OUTPUT_FOLDER) / "uploads")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Chunking
CHUNK_SIZE_WORDS = _env_int("CHUNK_SIZE_WORDS", int(_cfg_get(_YAML, "chunking", "chunk_size_words", default=1500)))
CHUNK_OVERLAP_WORDS = _env_int(
    "CHUNK_OVERLAP_WORDS", int(_cfg_get(_YAML, "chunking", "chunk_overlap_words", default=150))
)

# System
DEBUG_STRUCTURE = _env_bool("DEBUG_STRUCTURE", bool(_cfg_get(_YAML, "system", "debug_structure", default=True)))
ENGLISH_ONLY = _env_bool("ENGLISH_ONLY", bool(_cfg_get(_YAML, "system", "english_only", default=True)))
DOCX_THEME = _env("DOCX_THEME", str(_cfg_get(_YAML, "export", "docx_theme", default="color"))).strip().lower()
DOCX_FONT_FAMILY = _env(
    "DOCX_FONT_FAMILY",
    str(_cfg_get(_YAML, "export", "font_family", default="Times New Roman")),
).strip()
NOTES_EXPORT_STYLE = _env(
    "NOTES_EXPORT_STYLE",
    str(_cfg_get(_YAML, "export", "notes_style", default="book")),
).strip().lower()

# LLM generic
LLM_PROVIDER = _normalize_llm_provider(
    _env("LLM_PROVIDER", str(_cfg_get(_YAML, "llm", "provider", default="OPENAI")))
)
LLM_MODEL = _env("LLM_MODEL", str(_cfg_get(_YAML, "llm", "model", default="")))
LLM_BASE_URL = _env("LLM_BASE_URL", str(_cfg_get(_YAML, "llm", "base_url", default="")))
LLM_TIMEOUT_S = _env_float("LLM_TIMEOUT_S", float(_cfg_get(_YAML, "llm", "timeout_s", default=600)))
LLM_HTTP_DEBUG = _env_bool("LLM_HTTP_DEBUG", bool(_cfg_get(_YAML, "llm", "http_debug", default=False)))
LLM_VALIDITY_BATCH_SIZE = _env_int(
    "LLM_VALIDITY_BATCH_SIZE", int(_cfg_get(_YAML, "llm", "validity_batch_size", default=20))
)
LLM_TOC_BATCH_SIZE = _env_int("LLM_TOC_BATCH_SIZE", int(_cfg_get(_YAML, "llm", "toc_batch_size", default=20)))

# Provider secrets / overrides
GEMINI_API_KEY = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
GEMINI_MODEL = _env(
    "GEMINI_MODEL",
    str(_cfg_get(_YAML, "gemini", "model", default="models/gemini-3.1-flash-lite-preview")),
) or LLM_MODEL
GEMINI_TIMEOUT_S = _env_float("GEMINI_TIMEOUT_S", LLM_TIMEOUT_S)

OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_MODEL = _env("OPENAI_MODEL", str(_cfg_get(_YAML, "openai", "model", default="gpt-4o-mini"))) or LLM_MODEL
OPENAI_BASE_URL = (
    _env("OPENAI_BASE_URL", str(_cfg_get(_YAML, "openai", "base_url", default="https://api.openai.com")))
    or LLM_BASE_URL
)
OPENAI_TIMEOUT_S = _env_float("OPENAI_TIMEOUT_S", LLM_TIMEOUT_S)
OPENAI_MAX_RETRIES = _env_int("OPENAI_MAX_RETRIES", 2)
OPENAI_RETRY_BACKOFF_S = _env_float("OPENAI_RETRY_BACKOFF_S", 1.5)

OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _env(
    "OPENROUTER_MODEL",
    str(_cfg_get(_YAML, "openrouter", "model", default="openrouter/free")),
)
OPENROUTER_BASE_URL = (
    _env(
        "OPENROUTER_BASE_URL",
        str(_cfg_get(_YAML, "openrouter", "base_url", default="https://openrouter.ai/api/v1")),
    ).strip()
    or "https://openrouter.ai/api/v1"
)
OPENROUTER_TIMEOUT_S = _env_float("OPENROUTER_TIMEOUT_S", LLM_TIMEOUT_S)
OPENROUTER_HTTP_REFERER = _env(
    "OPENROUTER_HTTP_REFERER",
    str(_cfg_get(_YAML, "openrouter", "http_referer", default="")),
).strip()
OPENROUTER_APP_TITLE = _env(
    "OPENROUTER_APP_TITLE",
    str(_cfg_get(_YAML, "openrouter", "app_title", default="AI Notes Creator")),
).strip()

# Rewrite
REWRITE_MAX_TOKENS = _env_int("REWRITE_MAX_TOKENS", int(_cfg_get(_YAML, "rewrite", "max_tokens", default=15000)))
_raw_rewrite_provider_order = _env("REWRITE_PROVIDER_ORDER", str(_cfg_get(_YAML, "rewrite", "provider_order", default=""))).strip().lower()
REWRITE_PROVIDER_ORDER = (
    _raw_rewrite_provider_order if _raw_rewrite_provider_order else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
)

# Doubted resolver
_raw_doubted_resolver_llm = _env(
    "DOUBTED_RESOLVER_LLM", str(_cfg_get(_YAML, "doubted", "resolver_llm", default=""))
).strip().lower()
DOUBTED_RESOLVER_LLM = (
    _raw_doubted_resolver_llm if _raw_doubted_resolver_llm else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
)
DOUBTED_RESOLVER_MODE = _env(
    "DOUBTED_RESOLVER_MODE", str(_cfg_get(_YAML, "doubted", "resolver_mode", default="revalidate_selected"))
).strip().lower()
DOUBTED_REVALIDATION_MODEL = _env(
    "DOUBTED_REVALIDATION_MODEL", str(_cfg_get(_YAML, "doubted", "revalidation_model", default=""))
).strip()
DOUBTED_REVALIDATION_CONFIDENCE = _env_float(
    "DOUBTED_REVALIDATION_CONFIDENCE", float(_cfg_get(_YAML, "doubted", "revalidation_confidence", default=0.85))
)
DOUBTED_REVALIDATION_MAX = _env_int(
    "DOUBTED_REVALIDATION_MAX", int(_cfg_get(_YAML, "doubted", "revalidation_max", default=40))
)

# Stage 15e — chapter hierarchy (LLM or rules; 15j regroups when enabled)
_raw_chapter_hierarchy_llm = _env(
    "CHAPTER_HIERARCHY_LLM", str(_cfg_get(_YAML, "chapter_hierarchy", "llm", default=""))
).strip().lower()
CHAPTER_HIERARCHY_LLM = (
    _raw_chapter_hierarchy_llm if _raw_chapter_hierarchy_llm else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
)
CHAPTER_HIERARCHY_USE_LLM = _env(
    "CHAPTER_HIERARCHY_USE_LLM", str(_cfg_get(_YAML, "chapter_hierarchy", "use_llm", default="1"))
).strip()
CHAPTER_HIERARCHY_BATCH_SIZE = _env_int(
    "CHAPTER_HIERARCHY_BATCH_SIZE", int(_cfg_get(_YAML, "chapter_hierarchy", "batch_size", default=25))
)
CHAPTER_HIERARCHY_MAX_SECTIONS = _env_int(
    "CHAPTER_HIERARCHY_MAX_SECTIONS", int(_cfg_get(_YAML, "chapter_hierarchy", "max_sections", default=0))
)
CHAPTER_HIERARCHY_MIN_SECTIONS_PER_CHAPTER = _env_int(
    "CHAPTER_HIERARCHY_MIN_SECTIONS_PER_CHAPTER",
    int(_cfg_get(_YAML, "chapter_hierarchy", "min_sections_per_chapter", default=6)),
)

# Stage 15f — heading cleanup (weak titles + duplicate chapters)
_raw_heading_cleanup_llm = _env(
    "HEADING_CLEANUP_LLM", str(_cfg_get(_YAML, "heading_cleanup", "llm", default=""))
).strip().lower()
HEADING_CLEANUP_LLM = (
    _raw_heading_cleanup_llm if _raw_heading_cleanup_llm else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
)
HEADING_CLEANUP_USE_LLM = _env(
    "HEADING_CLEANUP_USE_LLM", str(_cfg_get(_YAML, "heading_cleanup", "use_llm", default="1"))
).strip()
HEADING_CLEANUP_BATCH_SIZE = _env_int(
    "HEADING_CLEANUP_BATCH_SIZE", int(_cfg_get(_YAML, "heading_cleanup", "batch_size", default=20))
)
HEADING_CLEANUP_BACKEND = _env(
    "HEADING_CLEANUP_BACKEND", str(_cfg_get(_YAML, "heading_cleanup", "backend", default=""))
).strip().lower() or _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
HEADING_CLEANUP_MINILM_PICK_THRESHOLD = _env_float(
    "HEADING_CLEANUP_MINILM_PICK_THRESHOLD",
    float(_cfg_get(_YAML, "heading_cleanup", "minilm_pick_threshold", default=0.82)),
)
TITLE_VALIDATION_ENABLED = _env_bool(
    "TITLE_VALIDATION_ENABLED",
    bool(_cfg_get(_YAML, "title_validation", "enabled", default=True)),
)
# Stage 15h — chapter placement (MODULE splits, MiniLM reassignment, chapter titles)
CHAPTER_PLACEMENT_ENABLED = _env_bool(
    "CHAPTER_PLACEMENT_ENABLED",
    bool(_cfg_get(_YAML, "chapter_placement", "enabled", default=True)),
)
CHAPTER_PLACEMENT_REASSIGN = _env_bool(
    "CHAPTER_PLACEMENT_REASSIGN",
    bool(_cfg_get(_YAML, "chapter_placement", "reassign_sections", default=True)),
)
CHAPTER_PLACEMENT_RENAME_CHAPTERS = _env_bool(
    "CHAPTER_PLACEMENT_RENAME_CHAPTERS",
    bool(_cfg_get(_YAML, "chapter_placement", "rename_chapters", default=True)),
)
CHAPTER_PLACEMENT_MIN_SECTIONS_FOR_RENAME = _env_int(
    "CHAPTER_PLACEMENT_MIN_SECTIONS_FOR_RENAME",
    int(_cfg_get(_YAML, "chapter_placement", "min_sections_for_rename", default=5)),
)
CHAPTER_PLACEMENT_COHESION_THRESHOLD = _env_float(
    "CHAPTER_PLACEMENT_COHESION_THRESHOLD",
    float(_cfg_get(_YAML, "chapter_placement", "cohesion_threshold", default=0.48)),
)
CHAPTER_PLACEMENT_REASSIGN_MARGIN = _env_float(
    "CHAPTER_PLACEMENT_REASSIGN_MARGIN",
    float(_cfg_get(_YAML, "chapter_placement", "reassign_margin", default=0.06)),
)
CHAPTER_PLACEMENT_PAGE_MARGIN = _env_int(
    "CHAPTER_PLACEMENT_PAGE_MARGIN",
    int(_cfg_get(_YAML, "chapter_placement", "page_margin", default=8)),
)
CHAPTER_PLACEMENT_MAX_SECTIONS_PER_CHAPTER = _env_int(
    "CHAPTER_PLACEMENT_MAX_SECTIONS_PER_CHAPTER",
    int(_cfg_get(_YAML, "chapter_placement", "max_sections_per_chapter", default=10)),
)
CHAPTER_PLACEMENT_PAGE_GAP_SPLIT = _env_int(
    "CHAPTER_PLACEMENT_PAGE_GAP_SPLIT",
    int(_cfg_get(_YAML, "chapter_placement", "page_gap_split", default=12)),
)

# Stage 15i — chapter, section, and subheading title refinement (before rewrite)
HEADING_REFINEMENT_ENABLED = _env_bool(
    "HEADING_REFINEMENT_ENABLED",
    bool(_cfg_get(_YAML, "heading_refinement", "enabled", default=True)),
)
HEADING_REFINEMENT_USE_TRANSFORMERS = _env_bool(
    "HEADING_REFINEMENT_USE_TRANSFORMERS",
    bool(_cfg_get(_YAML, "heading_refinement", "use_transformers", default=True)),
)
HEADING_REFINEMENT_DEDUPE = _env_bool(
    "HEADING_REFINEMENT_DEDUPE",
    bool(_cfg_get(_YAML, "heading_refinement", "dedupe", default=True)),
)
HEADING_REFINEMENT_DROP_EMPTY = _env_bool(
    "HEADING_REFINEMENT_DROP_EMPTY",
    bool(_cfg_get(_YAML, "heading_refinement", "drop_empty", default=True)),
)
HEADING_REFINEMENT_MINILM_THRESHOLD = _env_float(
    "HEADING_REFINEMENT_MINILM_THRESHOLD",
    float(_cfg_get(_YAML, "heading_refinement", "minilm_threshold", default=0.8)),
)
HEADING_REFINEMENT_OPENAI_FALLBACK = _env_bool(
    "HEADING_REFINEMENT_OPENAI_FALLBACK",
    bool(_cfg_get(_YAML, "heading_refinement", "openai_fallback", default=False)),
)

# Stage 15j — OpenAI hierarchy regroup + title correction (2 calls)
HIERARCHY_OPENAI_ENABLED = _env_bool(
    "HIERARCHY_OPENAI_ENABLED",
    bool(_cfg_get(_YAML, "hierarchy_openai", "enabled", default=False)),
)
HIERARCHY_OPENAI_AUTO_SKIP = _env_bool(
    "HIERARCHY_OPENAI_AUTO_SKIP",
    bool(_cfg_get(_YAML, "hierarchy_openai", "auto_skip", default=True)),
)
HIERARCHY_OPENAI_PROVIDER = _env(
    "HIERARCHY_OPENAI_PROVIDER",
    str(_cfg_get(_YAML, "hierarchy_openai", "provider", default="")),
).strip() or _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
HIERARCHY_OPENAI_TARGET_MAX_CHAPTERS = _env_int(
    "HIERARCHY_OPENAI_TARGET_MAX_CHAPTERS",
    int(_cfg_get(_YAML, "hierarchy_openai", "target_max_chapters", default=8)),
)
HIERARCHY_OPENAI_MIN_SECTIONS_PER_CHAPTER = _env_int(
    "HIERARCHY_OPENAI_MIN_SECTIONS_PER_CHAPTER",
    int(_cfg_get(_YAML, "hierarchy_openai", "min_sections_per_chapter", default=3)),
)
CHAPTER_COHESION_MIN_SECTIONS = _env_int(
    "CHAPTER_COHESION_MIN_SECTIONS",
    int(_cfg_get(_YAML, "chapter_cohesion", "min_sections_per_chapter", default=3)),
)
CHAPTER_COHESION_MIN_CHARS = _env_int(
    "CHAPTER_COHESION_MIN_CHARS",
    int(_cfg_get(_YAML, "chapter_cohesion", "min_chars", default=400)),
)
CHAPTER_COHESION_MAX_SECTIONS = _env_int(
    "CHAPTER_COHESION_MAX_SECTIONS",
    int(_cfg_get(_YAML, "chapter_cohesion", "max_sections_per_chapter", default=12)),
)
CHAPTER_COHESION_THRESHOLD = _env_float(
    "CHAPTER_COHESION_THRESHOLD",
    float(_cfg_get(_YAML, "chapter_cohesion", "merge_threshold", default=0.52)),
)
HIERARCHY_OPENAI_MIN_CHAPTER_CHARS = _env_int(
    "HIERARCHY_OPENAI_MIN_CHAPTER_CHARS",
    int(_cfg_get(_YAML, "hierarchy_openai", "min_chapter_chars", default=400)),
)
HIERARCHY_OPENAI_REGROUP_BATCH_SIZE = _env_int(
    "HIERARCHY_OPENAI_REGROUP_BATCH_SIZE",
    int(_cfg_get(_YAML, "hierarchy_openai", "regroup_batch_size", default=22)),
)
CHAPTER_PLACEMENT_MIN_SECTIONS_PER_CHAPTER = _env_int(
    "CHAPTER_PLACEMENT_MIN_SECTIONS_PER_CHAPTER",
    int(_cfg_get(_YAML, "chapter_placement", "min_sections_per_chapter", default=3)),
)
CHAPTER_PLACEMENT_MIN_CHAPTER_CHARS = _env_int(
    "CHAPTER_PLACEMENT_MIN_CHAPTER_CHARS",
    int(_cfg_get(_YAML, "chapter_placement", "min_chapter_chars", default=400)),
)
EXPORT_APPEND_SUBTOPIC_CHECKLIST = _env_bool(
    "EXPORT_APPEND_SUBTOPIC_CHECKLIST",
    bool(_cfg_get(_YAML, "export", "append_subtopic_checklist", default=False)),
)
EXPORT_MISSING_BODY_MODE = _env(
    "EXPORT_MISSING_BODY_MODE",
    str(_cfg_get(_YAML, "export", "missing_body_mode", default="placeholder")),
).strip().lower()
NOTES_STRUCTURE_FIX_ENABLED = _env_bool(
    "NOTES_STRUCTURE_FIX_ENABLED",
    bool(_cfg_get(_YAML, "export", "structure_fix_enabled", default=True)),
)
NOTES_STRUCTURE_FIX_ENGINE = _env(
    "NOTES_STRUCTURE_FIX_ENGINE",
    str(_cfg_get(_YAML, "export", "structure_fix_engine", default="hybrid")),
).strip().lower()
NOTES_STRUCTURE_FIX_MERGE_DUPLICATES = _env_bool(
    "NOTES_STRUCTURE_FIX_MERGE_DUPLICATES",
    bool(_cfg_get(_YAML, "export", "structure_fix_merge_duplicates", default=False)),
)
NOTES_STRUCTURE_FIX_DROP_LOW_GROUNDING = _env_bool(
    "NOTES_STRUCTURE_FIX_DROP_LOW_GROUNDING",
    bool(_cfg_get(_YAML, "export", "structure_fix_drop_low_grounding", default=False)),
)

DOCUMENT_PROFILE_SHORT_BODY_CHARS = _env_int(
    "DOCUMENT_PROFILE_SHORT_BODY_CHARS",
    int(_cfg_get(_YAML, "document_profile", "short_body_chars", default=400)),
)
DOCUMENT_PROFILE_BASE_MIN_SECTION_BODY_CHARS = _env_int(
    "DOCUMENT_PROFILE_BASE_MIN_SECTION_BODY_CHARS",
    int(_cfg_get(_YAML, "document_profile", "base_min_section_body_chars", default=200)),
)
DOCUMENT_PROFILE_BASE_REWRITE_OVERLAP_CHARS = _env_int(
    "DOCUMENT_PROFILE_BASE_REWRITE_OVERLAP_CHARS",
    int(_cfg_get(_YAML, "document_profile", "base_rewrite_overlap_chars", default=600)),
)
DOCUMENT_PROFILE_BASE_REWRITE_MAX_TOKENS = _env_int(
    "DOCUMENT_PROFILE_BASE_REWRITE_MAX_TOKENS",
    int(_cfg_get(_YAML, "document_profile", "base_rewrite_max_tokens", default=1800)),
)
DOCUMENT_PROFILE_BASE_MEDIAN_SECTION_BODY_CHARS = _env_int(
    "DOCUMENT_PROFILE_BASE_MEDIAN_SECTION_BODY_CHARS",
    int(_cfg_get(_YAML, "document_profile", "base_median_section_body_chars", default=1200)),
)

# Ingestion profiles (web upload)
INGESTION_PROFILE = _env(
    "INGESTION_PROFILE", str(_cfg_get(_YAML, "ingestion", "profile", default="fast_local"))
).strip().lower()
_ingestion_profiles_raw = _cfg_get(_YAML, "ingestion", "profiles", default={}) or {}
INGESTION_PROFILES: dict[str, dict[str, Any]] = (
    dict(_ingestion_profiles_raw) if isinstance(_ingestion_profiles_raw, dict) else {}
)
_fast_local_skip = _cfg_get(_YAML, "ingestion", "profiles", "fast_local", "upload_skip_rag", default=True)
UPLOAD_SKIP_RAG_DEFAULT = "true" if bool(_fast_local_skip) else "false"

FULL_REWRITE_MAX_CHUNKS = _env_int(
    "FULL_REWRITE_MAX_CHUNKS", int(_cfg_get(_YAML, "rewrite", "full_rewrite_max_chunks", default=0))
)
REWRITE_PARALLEL_WORKERS = _env_int(
    "REWRITE_PARALLEL_WORKERS", int(_cfg_get(_YAML, "rewrite", "parallel_workers", default=8))
)
REWRITE_CONTEXT_OVERLAP_CHARS = _env_int(
    "REWRITE_CONTEXT_OVERLAP_CHARS", int(_cfg_get(_YAML, "rewrite", "context_overlap_chars", default=600))
)
REWRITE_AUTO_RETRY_ENABLED = _env(
    "REWRITE_AUTO_RETRY_ENABLED",
    str(_cfg_get(_YAML, "rewrite", "auto_retry_enabled", default="true")),
).strip()
REWRITE_AUTO_RETRY_MAX_PASSES = _env_int(
    "REWRITE_AUTO_RETRY_MAX_PASSES",
    int(_cfg_get(_YAML, "rewrite", "auto_retry_max_passes", default=1)),
)
REWRITE_AUTO_RETRY_MIN_COVERAGE = _env_float(
    "REWRITE_AUTO_RETRY_MIN_COVERAGE",
    float(_cfg_get(_YAML, "rewrite", "auto_retry_min_coverage", default=0.95)),
)
REWRITE_FIDELITY_MIN_OVERLAP = _env_float(
    "REWRITE_FIDELITY_MIN_OVERLAP",
    float(_cfg_get(_YAML, "rewrite", "fidelity_min_overlap", default=0.30)),
)
REWRITE_FIDELITY_REGENERATE_TEMPERATURE = _env_float(
    "REWRITE_FIDELITY_REGENERATE_TEMPERATURE",
    float(_cfg_get(_YAML, "rewrite", "fidelity_regenerate_temperature", default=0.1)),
)
REWRITE_MIN_GROUNDING_CHARS = _env_int(
    "REWRITE_MIN_GROUNDING_CHARS",
    int(_cfg_get(_YAML, "rewrite", "min_grounding_chars", default=160)),
)
# Partition grounding gate: drop sections whose reconstructed body is an
# index/contents listing (enumeration-dominated or near-empty of prose) so the
# rewrite never receives an ungrounded source. Disable to keep legacy behavior.
PARTITION_DROP_LOW_GROUNDING = _env_bool(
    "PARTITION_DROP_LOW_GROUNDING",
    bool(_cfg_get(_YAML, "structure", "partition_drop_low_grounding", default=True)),
)
# Document-wide contents/index page detection: flag enumeration-dominated pages
# so their headings are excluded from section partitioning (not just the
# front-matter TOC). Disable to keep legacy behavior.
CONTENTS_REGION_DETECTION = _env_bool(
    "CONTENTS_REGION_DETECTION",
    bool(_cfg_get(_YAML, "structure", "contents_region_detection", default=True)),
)
REWRITE_AUTO_RETRY_MISSING = _env(
    "REWRITE_AUTO_RETRY_MISSING", str(_cfg_get(_YAML, "rewrite", "auto_retry_missing", default="1"))
).strip()
REWRITE_MISSING_MAX_ROUNDS = _env_int(
    "REWRITE_MISSING_MAX_ROUNDS", int(_cfg_get(_YAML, "rewrite", "missing_max_rounds", default=3))
)
COMPACT_EXAM = _env(
    "COMPACT_EXAM", str(_cfg_get(_YAML, "rewrite", "compact_exam", default="0"))
).strip()
REWRITE_BUNDLE_SIZE = _env_int(
    "REWRITE_BUNDLE_SIZE", int(_cfg_get(_YAML, "rewrite", "bundle_size", default=1))
)
REWRITE_BUNDLE_MAX_CHARS = _env_int(
    "REWRITE_BUNDLE_MAX_CHARS", int(_cfg_get(_YAML, "rewrite", "bundle_max_chars", default=12000))
)
REWRITE_BUNDLE_EXPORT = _env(
    "REWRITE_BUNDLE_EXPORT", str(_cfg_get(_YAML, "rewrite", "bundle_export", default="1"))
).strip()
REWRITE_CHAPTER_PAGE_BREAKS = _env(
    "REWRITE_CHAPTER_PAGE_BREAKS",
    str(_cfg_get(_YAML, "rewrite", "chapter_page_breaks", default="auto")),
).strip()
PIPELINE_MAX_PAGES = _env_int(
    "PIPELINE_MAX_PAGES", int(_cfg_get(_YAML, "system", "pipeline_max_pages", default=0))
)
ULTIMATE_MIN_PARENT_FRAGMENT_CHARS = _env_int(
    "ULTIMATE_MIN_PARENT_FRAGMENT_CHARS",
    int(_cfg_get(_YAML, "ultimate", "min_parent_fragment_chars", default=520)),
)
ULTIMATE_MIN_SECTION_CHARS_FOR_NESTING = _env_int(
    "ULTIMATE_MIN_SECTION_CHARS_FOR_NESTING",
    int(_cfg_get(_YAML, "ultimate", "min_section_chars_for_nesting", default=380)),
)
ULTIMATE_MIN_HEADING_FRAGMENT_CHARS = _env_int(
    "ULTIMATE_MIN_HEADING_FRAGMENT_CHARS",
    int(_cfg_get(_YAML, "ultimate", "min_heading_fragment_chars", default=140)),
)
ULTIMATE_MAX_REWRITE_SECTION_CHARS = _env_int(
    "ULTIMATE_MAX_REWRITE_SECTION_CHARS",
    int(_cfg_get(_YAML, "ultimate", "max_rewrite_section_chars", default=2200)),
)
ULTIMATE_MAX_SECTIONS_PAGE_RATIO = _env_float(
    "ULTIMATE_MAX_SECTIONS_PAGE_RATIO",
    float(_cfg_get(_YAML, "ultimate", "max_sections_page_ratio", default=0.45)),
)
ULTIMATE_MIN_SECTION_COUNT = _env_int(
    "ULTIMATE_MIN_SECTION_COUNT",
    int(_cfg_get(_YAML, "ultimate", "min_section_count", default=16)),
)
ULTIMATE_MAX_SECTION_COUNT = _env_int(
    "ULTIMATE_MAX_SECTION_COUNT",
    int(_cfg_get(_YAML, "ultimate", "max_section_count", default=0)),
)
SECTION_CONSOLIDATION_ENABLED = _env_bool(
    "SECTION_CONSOLIDATION_ENABLED",
    bool(_cfg_get(_YAML, "section_consolidation", "enabled", default=True)),
)
SECTION_CONSOLIDATION_MIN_CHARS = _env_int(
    "SECTION_CONSOLIDATION_MIN_CHARS",
    int(_cfg_get(_YAML, "section_consolidation", "min_chars", default=200)),
)
SECTION_CONSOLIDATION_MAX_CHARS = _env_int(
    "SECTION_CONSOLIDATION_MAX_CHARS",
    int(_cfg_get(_YAML, "section_consolidation", "max_merged_chars", default=12000)),
)

_ULTIMATE_PROFILES: dict[str, dict[str, int]] = {
    # Large-context cloud models: fewer rewrite calls, bigger source windows
    "large": {
        "min_parent_fragment_chars": 900,
        "min_section_chars_for_nesting": 600,
        "min_heading_fragment_chars": 220,
        "max_rewrite_section_chars": 6000,
    },
    # Default / mid-size local or API models
    "medium": {
        "min_parent_fragment_chars": 520,
        "min_section_chars_for_nesting": 380,
        "min_heading_fragment_chars": 140,
        "max_rewrite_section_chars": 2200,
    },
    # Small local models (<2B ctx): more sections, smaller windows
    "small": {
        "min_parent_fragment_chars": 300,
        "min_section_chars_for_nesting": 200,
        "min_heading_fragment_chars": 80,
        "max_rewrite_section_chars": 1500,
    },
}


def _rewrite_backend_for_ultimate() -> str:
    from src.shared.llm_provider import active_chat_provider, rewrite_provider_order

    order = rewrite_provider_order()
    backend = order[0] if order else active_chat_provider()
    if backend in {"openai", "openrouter"}:
        return "large"
    return "large"


def resolve_ultimate_thresholds() -> dict[str, int | str]:
    """Return active 15d character thresholds (env overrides > profile > auto)."""
    profile = _env("ULTIMATE_PROFILE", str(_cfg_get(_YAML, "ultimate", "profile", default="auto"))).strip().lower()
    if profile in {"", "auto"}:
        profile = _rewrite_backend_for_ultimate()
    if profile not in _ULTIMATE_PROFILES:
        profile = "medium"
    base = dict(_ULTIMATE_PROFILES[profile])

    def _pick(env_key: str, field: str) -> int:
        raw = _env(env_key, "").strip()
        if raw:
            return int(raw)
        return int(base[field])

    return {
        "profile": profile,
        "min_parent_fragment_chars": _pick("ULTIMATE_MIN_PARENT_FRAGMENT_CHARS", "min_parent_fragment_chars"),
        "min_section_chars_for_nesting": _pick(
            "ULTIMATE_MIN_SECTION_CHARS_FOR_NESTING", "min_section_chars_for_nesting"
        ),
        "min_heading_fragment_chars": _pick("ULTIMATE_MIN_HEADING_FRAGMENT_CHARS", "min_heading_fragment_chars"),
        "max_rewrite_section_chars": _pick("ULTIMATE_MAX_REWRITE_SECTION_CHARS", "max_rewrite_section_chars"),
    }

# Vector RAG (Q&A retrieval)
RAG_ENABLED = _env_bool("RAG_ENABLED", bool(_cfg_get(_YAML, "rag", "enabled", default=True)))
RAG_EMBEDDING_MODEL = _env(
    "RAG_EMBEDDING_MODEL", str(_cfg_get(_YAML, "rag", "embedding_model", default="all-MiniLM-L6-v2"))
)
RAG_INDEX_DIR = str(
    _PROJECT_ROOT / _cfg_get(_YAML, "rag", "index_dir", default="output/rag_index")
)
RAG_TOP_K = _env_int("RAG_TOP_K", int(_cfg_get(_YAML, "rag", "top_k", default=6)))
RAG_VECTOR_WEIGHT = _env_float("RAG_VECTOR_WEIGHT", float(_cfg_get(_YAML, "rag", "vector_weight", default=0.65)))
RAG_LEXICAL_WEIGHT = _env_float("RAG_LEXICAL_WEIGHT", float(_cfg_get(_YAML, "rag", "lexical_weight", default=0.35)))
RAG_MIN_SCORE = _env_float("RAG_MIN_SCORE", float(_cfg_get(_YAML, "rag", "min_score", default=0.15)))
RAG_CHUNK_SIZE_WORDS = _env_int("RAG_CHUNK_SIZE_WORDS", int(_cfg_get(_YAML, "rag", "chunk_size_words", default=0)))
RAG_CHUNK_OVERLAP_WORDS = _env_int(
    "RAG_CHUNK_OVERLAP_WORDS", int(_cfg_get(_YAML, "rag", "chunk_overlap_words", default=80))
)
RAG_MIN_CHUNK_CHARS = _env_int("RAG_MIN_CHUNK_CHARS", int(_cfg_get(_YAML, "rag", "min_chunk_chars", default=40)))
RAG_RERANK_ENABLED = _env_bool("RAG_RERANK_ENABLED", bool(_cfg_get(_YAML, "rag", "rerank_enabled", default=True)))
RAG_RERANK_MODEL = _env(
    "RAG_RERANK_MODEL",
    str(_cfg_get(_YAML, "rag", "rerank_model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")),
).strip()
RAG_RERANK_CANDIDATES = _env_int(
    "RAG_RERANK_CANDIDATES", int(_cfg_get(_YAML, "rag", "rerank_candidates", default=50))
)
RAG_CONTEXT_MAX_CHARS = _env_int(
    "RAG_CONTEXT_MAX_CHARS", int(_cfg_get(_YAML, "rag", "context_max_chars", default=12000))
)

# Page-level OCR (scanned / two-up PDFs)
OCR_ENABLED = _env_bool("OCR_ENABLED", bool(_cfg_get(_YAML, "ocr", "enabled", default=True)))
OCR_MODE = _env("OCR_MODE", str(_cfg_get(_YAML, "ocr", "mode", default="auto")).strip().lower())
OCR_SPLIT_TWO_UP = _env_bool("OCR_SPLIT_TWO_UP", bool(_cfg_get(_YAML, "ocr", "split_two_up", default=False)))
OCR_MIN_TEXT_CHARS = _env_int("OCR_MIN_TEXT_CHARS", int(_cfg_get(_YAML, "ocr", "min_text_chars", default=40)))
OCR_ZOOM = _env_float("OCR_ZOOM", float(_cfg_get(_YAML, "ocr", "zoom", default=2.0)))
OCR_LANG = _env("OCR_LANG", str(_cfg_get(_YAML, "ocr", "lang", default="eng")))
TESSERACT_CMD = _env("TESSERACT_CMD", "")

os.makedirs(RAG_INDEX_DIR, exist_ok=True)
