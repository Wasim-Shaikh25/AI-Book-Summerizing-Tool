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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "config"
_DEFAULT_YAML = _CONFIG_DIR / "default.yaml"

_PROVIDER_ALIASES = {"CHATGPT": "OPENAI", "GOOGLE": "GEMINI", "LOCAL": "LLAMACPP"}
_PROVIDER_TO_BACKEND = {
    "OPENAI": "openai",
    "GEMINI": "gemini",
    "LLAMACPP": "llamacpp",
    "OLLAMA": "ollama",
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
    env_path = _REPO_ROOT / ".env"
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
    p = (raw or "LLAMACPP").strip().upper()
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
BASE_DIR = str(_REPO_ROOT)
PDF_FOLDER = str(_REPO_ROOT / _cfg_get(_YAML, "paths", "pdf_folder", default="pdfs"))
OUTPUT_FOLDER = str(_REPO_ROOT / _cfg_get(_YAML, "paths", "output_folder", default="output"))
REFERENCE_DOCX_PATH = str(_REPO_ROOT / _cfg_get(_YAML, "paths", "reference_docx", default="reference.docx"))
MODELS_DIR = str(_REPO_ROOT / _cfg_get(_YAML, "paths", "models_dir", default="models"))

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Chunking
CHUNK_SIZE_WORDS = _env_int("CHUNK_SIZE_WORDS", int(_cfg_get(_YAML, "chunking", "chunk_size_words", default=1500)))
CHUNK_OVERLAP_WORDS = _env_int(
    "CHUNK_OVERLAP_WORDS", int(_cfg_get(_YAML, "chunking", "chunk_overlap_words", default=150))
)

# System
DEBUG_STRUCTURE = _env_bool("DEBUG_STRUCTURE", bool(_cfg_get(_YAML, "system", "debug_structure", default=True)))

# LLM generic
LLM_PROVIDER = _normalize_llm_provider(
    _env("LLM_PROVIDER", str(_cfg_get(_YAML, "llm", "provider", default="LLAMACPP")))
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

OLLAMA_BASE_URL = (
    _env("OLLAMA_BASE_URL", str(_cfg_get(_YAML, "ollama", "base_url", default="http://localhost:11434")))
    or LLM_BASE_URL
)
OLLAMA_MODEL = _env("OLLAMA_MODEL", str(_cfg_get(_YAML, "ollama", "model", default="llama3.2:3b"))) or LLM_MODEL
OLLAMA_TIMEOUT_S = _env_float("OLLAMA_TIMEOUT_S", LLM_TIMEOUT_S)

# Rewrite
REWRITE_MAX_TOKENS = _env_int("REWRITE_MAX_TOKENS", int(_cfg_get(_YAML, "rewrite", "max_tokens", default=15000)))
_raw_rewrite_provider_order = _env("REWRITE_PROVIDER_ORDER", str(_cfg_get(_YAML, "rewrite", "provider_order", default=""))).strip().lower()
REWRITE_PROVIDER_ORDER = (
    _raw_rewrite_provider_order if _raw_rewrite_provider_order else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "llamacpp")
)
REWRITE_LLAMACPP_MODEL_PATH = _env(
    "REWRITE_LLAMACPP_MODEL_PATH", str(_cfg_get(_YAML, "rewrite", "llamacpp_model_path", default=""))
).strip()
REWRITE_LLAMACPP_MODEL_URLS = _env(
    "REWRITE_LLAMACPP_MODEL_URLS", str(_cfg_get(_YAML, "rewrite", "llamacpp_model_urls", default=""))
).strip()

# llama.cpp
LLAMACPP_MODEL_PATH = _env("LLAMACPP_MODEL_PATH", str(_cfg_get(_YAML, "llamacpp", "model_path", default="")))
LLAMACPP_N_CTX = _env_int("LLAMACPP_N_CTX", int(_cfg_get(_YAML, "llamacpp", "n_ctx", default=2048)))
LLAMACPP_N_GPU_LAYERS = _env_int(
    "LLAMACPP_N_GPU_LAYERS", int(_cfg_get(_YAML, "llamacpp", "n_gpu_layers", default=0))
)

# Doubted resolver
_raw_doubted_resolver_llm = _env(
    "DOUBTED_RESOLVER_LLM", str(_cfg_get(_YAML, "doubted", "resolver_llm", default=""))
).strip().lower()
DOUBTED_RESOLVER_LLM = (
    _raw_doubted_resolver_llm if _raw_doubted_resolver_llm else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "llamacpp")
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

# Stage 15e — chapter hierarchy (LLM + optional BigBird fallback)
_raw_chapter_hierarchy_llm = _env(
    "CHAPTER_HIERARCHY_LLM", str(_cfg_get(_YAML, "chapter_hierarchy", "llm", default=""))
).strip().lower()
CHAPTER_HIERARCHY_LLM = (
    _raw_chapter_hierarchy_llm if _raw_chapter_hierarchy_llm else _PROVIDER_TO_BACKEND.get(LLM_PROVIDER, "openai")
)
CHAPTER_HIERARCHY_USE_LLM = _env(
    "CHAPTER_HIERARCHY_USE_LLM", str(_cfg_get(_YAML, "chapter_hierarchy", "use_llm", default="1"))
).strip()
CHAPTER_HIERARCHY_USE_BIGBIRD = _env(
    "CHAPTER_HIERARCHY_USE_BIGBIRD", str(_cfg_get(_YAML, "chapter_hierarchy", "use_bigbird", default="1"))
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

FULL_REWRITE_MAX_CHUNKS = _env_int(
    "FULL_REWRITE_MAX_CHUNKS", int(_cfg_get(_YAML, "rewrite", "full_rewrite_max_chunks", default=0))
)
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
    order = (REWRITE_PROVIDER_ORDER or LLM_PROVIDER or "openai").strip().lower()
    backend = order.split(",")[0].strip()
    if backend in {"openai", "gemini"}:
        return "large"
    if backend in {"ollama"}:
        return "medium"
    if backend in {"llamacpp", "local"}:
        return "small"
    return "medium"


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
