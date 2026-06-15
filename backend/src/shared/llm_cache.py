"""Content-hash disk cache for LLM completions (cost reduction).

Rewriting the same PDF (same instruction + model) should not re-spend on the LLM.
The cache key is derived from the full request (model namespace + system + user +
max_tokens + a version tag), so it is automatically invalidated when the model,
prompt, or parameters change — never returning a stale response for new inputs.

Stored as one JSON file per key under ``<output>/.llm_cache/`` with provenance
(model, created timestamp, token cap) per rules 07/08.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Bump when the cache entry shape or prompt contract changes.
_CACHE_VERSION = "v1"

_lock = threading.Lock()


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_cache_enabled() -> bool:
    """Cache is on by default; set REWRITE_CACHE_ENABLED=0 to disable."""
    raw = os.environ.get("REWRITE_CACHE_ENABLED")
    if raw is None:
        return True
    return _truthy(raw)


def _cache_dir() -> Path:
    override = os.environ.get("LLM_CACHE_DIR")
    if override:
        path = Path(override)
    else:
        from src.shared import config

        path = Path(config.OUTPUT_FOLDER) / ".llm_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _model_namespace() -> str:
    """Identifier that invalidates the cache when the active model changes."""
    from src.shared import config

    return "|".join(
        str(getattr(config, attr, "") or "")
        for attr in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_MODEL")
    )


def cache_key(*, system: str, user: str, max_tokens: int, namespace: str = "") -> str:
    payload = "\x1f".join(
        [
            _CACHE_VERSION,
            namespace or _model_namespace(),
            str(max_tokens),
            system or "",
            user or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get(key: str) -> Optional[str]:
    path = _cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        text = data.get("text")
        return text if isinstance(text, str) and text else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("LLM cache read failed for %s: %s", key[:12], exc)
        return None


def put(key: str, text: str, *, max_tokens: int) -> None:
    if not text:
        return
    path = _cache_dir() / f"{key}.json"
    record = {
        "text": text,
        "model_namespace": _model_namespace(),
        "max_tokens": max_tokens,
        "cache_version": _CACHE_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with _lock:
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.debug("LLM cache write failed for %s: %s", key[:12], exc)


def cached_generate(
    generate: Callable[[str, str], str],
    *,
    max_tokens: int,
    enabled: Optional[bool] = None,
) -> Callable[[str, str], str]:
    """Wrap a ``generate(system, user) -> text`` callable with the disk cache.

    A cache hit returns the stored completion without calling the LLM. Misses call
    through and persist the result. Falls back to the raw callable on any error.
    """
    use_cache = is_cache_enabled() if enabled is None else enabled
    if not use_cache:
        return generate

    def _wrapped(system_prompt: str, user_prompt: str) -> str:
        try:
            key = cache_key(system=system_prompt, user=user_prompt, max_tokens=max_tokens)
        except Exception:  # never let caching break generation
            return generate(system_prompt, user_prompt)
        hit = get(key)
        if hit is not None:
            return hit
        text = generate(system_prompt, user_prompt)
        if text:
            put(key, text, max_tokens=max_tokens)
        return text

    return _wrapped
