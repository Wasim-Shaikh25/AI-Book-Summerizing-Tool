"""Ingestion profile overrides for web upload (fast_local / quality_cloud / debug)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from src import config as cfg

# Keys applied to os.environ + mirrored on config module for direct reads.
_PROFILE_ENV_KEYS = (
    "UPLOAD_SKIP_RAG",
    "OCR_ZOOM",
    "INGESTION_LAYOUT_BACKEND",
    "INGESTION_LAYOUT_DOCLING_ALWAYS",
    "DOUBTED_RESOLVER_LLM",
    "DOUBTED_RESOLVER_MODE",
    "CHAPTER_HIERARCHY_USE_LLM",
    "HEADING_CLEANUP_BACKEND",
    "HEADING_CLEANUP_USE_LLM",
    "HEADING_CLEANUP_MINILM_PICK_THRESHOLD",
    "HIERARCHY_OPENAI_ENABLED",
    "HIERARCHY_OPENAI_AUTO_SKIP",
    "HEADING_REFINEMENT_OPENAI_FALLBACK",
    "USE_LLM_INTENT",
    "NOTES_QUALITY_LLM",
)

_CONFIG_ATTR_MAP = {
    "UPLOAD_SKIP_RAG": None,  # env-only; ingestion_service reads via helper
    "OCR_ZOOM": "OCR_ZOOM",
    "INGESTION_LAYOUT_BACKEND": "INGESTION_LAYOUT_BACKEND",
    "INGESTION_LAYOUT_DOCLING_ALWAYS": "INGESTION_LAYOUT_DOCLING_ALWAYS",
    "DOUBTED_RESOLVER_LLM": "DOUBTED_RESOLVER_LLM",
    "DOUBTED_RESOLVER_MODE": "DOUBTED_RESOLVER_MODE",
    "CHAPTER_HIERARCHY_USE_LLM": "CHAPTER_HIERARCHY_USE_LLM",
    "HEADING_CLEANUP_BACKEND": "HEADING_CLEANUP_BACKEND",
    "HEADING_CLEANUP_USE_LLM": "HEADING_CLEANUP_USE_LLM",
    "HEADING_CLEANUP_MINILM_PICK_THRESHOLD": "HEADING_CLEANUP_MINILM_PICK_THRESHOLD",
    "HIERARCHY_OPENAI_ENABLED": "HIERARCHY_OPENAI_ENABLED",
    "HIERARCHY_OPENAI_AUTO_SKIP": "HIERARCHY_OPENAI_AUTO_SKIP",
    "HEADING_REFINEMENT_OPENAI_FALLBACK": "HEADING_REFINEMENT_OPENAI_FALLBACK",
    "USE_LLM_INTENT": "USE_LLM_INTENT",
    "NOTES_QUALITY_LLM": "NOTES_QUALITY_LLM",
}

_BUILTIN_PROFILES: Dict[str, Dict[str, str]] = {
    "fast_local": {
        "UPLOAD_SKIP_RAG": "true",
        "OCR_ZOOM": "1.5",
        "DOUBTED_RESOLVER_LLM": "off",
        "DOUBTED_RESOLVER_MODE": "fast",
        "CHAPTER_HIERARCHY_USE_LLM": "false",
        "HEADING_CLEANUP_BACKEND": "rules_only",
        "HEADING_CLEANUP_USE_LLM": "false",
        "HIERARCHY_OPENAI_ENABLED": "false",
        "HIERARCHY_OPENAI_AUTO_SKIP": "true",
        "HEADING_REFINEMENT_OPENAI_FALLBACK": "false",
        "USE_LLM_INTENT": "false",
        "NOTES_QUALITY_LLM": "false",
    },
    "quality_cloud": {
        "UPLOAD_SKIP_RAG": "false",
        "OCR_ZOOM": "2.0",
        "DOUBTED_RESOLVER_LLM": "openai",
        "DOUBTED_RESOLVER_MODE": "revalidate_selected",
        "CHAPTER_HIERARCHY_USE_LLM": "true",
        "HEADING_CLEANUP_BACKEND": "openai",
        "HEADING_CLEANUP_USE_LLM": "true",
        "HIERARCHY_OPENAI_ENABLED": "true",
        "HIERARCHY_OPENAI_AUTO_SKIP": "true",
        "HEADING_REFINEMENT_OPENAI_FALLBACK": "true",
        "USE_LLM_INTENT": "true",
        "NOTES_QUALITY_LLM": "true",
        "INGESTION_LAYOUT_BACKEND": "auto",
        "INGESTION_LAYOUT_DOCLING_ALWAYS": "true",
    },
    "debug": {
        "UPLOAD_SKIP_RAG": "false",
        "OCR_ZOOM": "2.0",
        "DOUBTED_RESOLVER_LLM": "openai",
        "DOUBTED_RESOLVER_MODE": "revalidate_selected",
        "CHAPTER_HIERARCHY_USE_LLM": "true",
        "HEADING_CLEANUP_BACKEND": "openai",
        "HEADING_CLEANUP_USE_LLM": "true",
    },
}


def _active_profile_name(explicit: Optional[str] = None) -> str:
    raw = (explicit or os.getenv("INGESTION_PROFILE") or getattr(cfg, "INGESTION_PROFILE", "fast_local")).strip()
    return raw or "fast_local"


def profile_overrides(profile_name: Optional[str] = None) -> Dict[str, str]:
    """Return env overrides for a profile (YAML profiles merge over builtins)."""
    name = _active_profile_name(profile_name)
    yaml_profiles = getattr(cfg, "INGESTION_PROFILES", {}) or {}
    merged: Dict[str, str] = dict(_BUILTIN_PROFILES.get(name, _BUILTIN_PROFILES["fast_local"]))
    if isinstance(yaml_profiles.get(name), dict):
        for key, value in yaml_profiles[name].items():
            env_key = key.upper() if not key.isupper() else key
            if isinstance(value, bool):
                merged[env_key] = "true" if value else "false"
            else:
                merged[env_key] = str(value)
    return merged


def _coerce_config_value(attr: str, raw: str) -> Any:
    if attr == "OCR_ZOOM":
        return float(raw)
    if attr == "HEADING_CLEANUP_MINILM_PICK_THRESHOLD":
        return float(raw)
    if attr in {
        "HIERARCHY_OPENAI_ENABLED",
        "HIERARCHY_OPENAI_AUTO_SKIP",
        "HEADING_REFINEMENT_OPENAI_FALLBACK",
        "USE_LLM_INTENT",
        "NOTES_QUALITY_LLM",
        "INGESTION_LAYOUT_DOCLING_ALWAYS",
    }:
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    return raw


def _apply_overrides(overrides: Dict[str, str]) -> None:
    for key, value in overrides.items():
        os.environ[key] = value
        attr = _CONFIG_ATTR_MAP.get(key)
        if attr:
            setattr(cfg, attr, _coerce_config_value(attr, value))


def _restore_env(saved: Dict[str, Optional[str]]) -> None:
    for key in _PROFILE_ENV_KEYS:
        prev = saved.get(key)
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev
        attr = _CONFIG_ATTR_MAP.get(key)
        if not attr:
            continue
        if prev is None:
            # Re-read from YAML/env defaults via module reload is heavy; keep prior config value.
            continue
        setattr(cfg, attr, _coerce_config_value(attr, prev))


@contextmanager
def ingestion_profile_context(profile_name: Optional[str] = None) -> Iterator[str]:
    """Apply ingestion profile for the duration of a single upload/pipeline run."""
    name = _active_profile_name(profile_name)
    overrides = profile_overrides(name)
    saved = {key: os.environ.get(key) for key in _PROFILE_ENV_KEYS}
    saved_config = {
        attr: getattr(cfg, attr, None)
        for key, attr in _CONFIG_ATTR_MAP.items()
        if attr
    }
    try:
        _apply_overrides(overrides)
        yield name
    finally:
        _restore_env(saved)
        for attr, value in saved_config.items():
            if value is not None:
                setattr(cfg, attr, value)


def upload_skip_rag_default() -> bool:
    """Whether upload should skip RAG index build (profile-aware)."""
    raw = os.getenv("UPLOAD_SKIP_RAG", getattr(cfg, "UPLOAD_SKIP_RAG_DEFAULT", "true"))
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
