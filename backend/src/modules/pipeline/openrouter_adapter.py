"""OpenRouter chat completions adapter (OpenAI-compatible API).

Docs: https://openrouter.ai/docs/quickstart
Free router model: https://openrouter.ai/openrouter/free  → ``openrouter/free``
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import List, Optional

from src import config

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_FREE_MODEL = "openrouter/free"


def openrouter_api_key() -> str:
    return (os.getenv("OPENROUTER_API_KEY") or getattr(config, "OPENROUTER_API_KEY", "") or "").strip()


def openrouter_base_url() -> str:
    return (
        os.getenv("OPENROUTER_BASE_URL") or getattr(config, "OPENROUTER_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
    ).rstrip("/")


def openrouter_model_candidates(model_override: str = "") -> List[str]:
    preferred = (
        (model_override or "").strip()
        or os.getenv("OPENROUTER_MODEL")
        or getattr(config, "OPENROUTER_MODEL", "")
        or os.getenv("LLM_MODEL")
        or getattr(config, "LLM_MODEL", "")
        or DEFAULT_FREE_MODEL
    ).strip()
    candidates = [preferred, DEFAULT_FREE_MODEL]
    out: List[str] = []
    seen = set()
    for m in candidates:
        if not m or m in seen:
            continue
        seen.add(m)
        out.append(m)
    return out


def chat_completions_url() -> str:
    base = openrouter_base_url()
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def chat_openrouter(
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float = 0.2,
    model_override: str = "",
) -> tuple[Optional[str], str]:
    """Return (response_text, model_used)."""
    api_key = openrouter_api_key()
    if not api_key:
        logger.warning("[LLM/OpenRouter] OPENROUTER_API_KEY not set.")
        return None, ""

    timeout_s = float(os.getenv("OPENROUTER_TIMEOUT_S") or getattr(config, "OPENROUTER_TIMEOUT_S", 90) or 90)
    referer = (os.getenv("OPENROUTER_HTTP_REFERER") or getattr(config, "OPENROUTER_HTTP_REFERER", "") or "").strip()
    app_title = (os.getenv("OPENROUTER_APP_TITLE") or getattr(config, "OPENROUTER_APP_TITLE", "") or "").strip()

    for model_name in openrouter_model_candidates(model_override):
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": int(max_tokens),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if referer:
            headers["HTTP-Referer"] = referer
        if app_title:
            headers["X-OpenRouter-Title"] = app_title

        req = urllib.request.Request(
            chat_completions_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices") or []
            if not choices:
                continue
            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()
            if not text:
                continue
            return text, model_name
        except urllib.error.HTTPError as e:
            if e.code in {404, 400, 403, 429}:
                try:
                    err = e.read().decode("utf-8", "ignore")[:300]
                except Exception:
                    err = ""
                logger.warning("OpenRouter HTTP %s for %s: %s", e.code, model_name, err)
                continue
            logger.warning("OpenRouter HTTP error %s for %s", e.code, model_name)
            return None, ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.warning("OpenRouter request failed for %s: %s", model_name, exc)
            continue
    return None, ""
