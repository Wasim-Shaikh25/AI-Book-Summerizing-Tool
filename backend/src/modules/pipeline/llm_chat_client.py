from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import List, Optional

from src import config
from src.shared.llm_provider import (  # noqa: F401 — re-exported for callers
    ALL_CHAT_PROVIDERS,
    active_chat_provider,
    normalize_chat_provider,
)

logger = logging.getLogger(__name__)

_CHAT_PROVIDERS = ALL_CHAT_PROVIDERS


class LlmChatClient:
    """Unified chat client — OpenAI and OpenRouter only."""

    def __init__(
        self,
        provider: str,
        *,
        model_override: str = "",
        temperature: float = 0.2,
    ) -> None:
        self.provider = normalize_chat_provider(provider)
        self._model_override = (model_override or "").strip()
        self.temperature = temperature
        self._last_model = ""
        self._openrouter_last_model = ""
        self._warned = False
        self._openai_key = (os.getenv("OPENAI_API_KEY") or config.OPENAI_API_KEY or "").strip()
        self._openai_base_url = (
            os.getenv("OPENAI_BASE_URL") or config.OPENAI_BASE_URL or "https://api.openai.com"
        ).rstrip("/")

    @classmethod
    def from_config(cls, *, model_override: str = "", temperature: float = 0.2) -> "LlmChatClient":
        return cls(active_chat_provider(), model_override=model_override, temperature=temperature)

    @property
    def chat_enabled(self) -> bool:
        return self.provider in _CHAT_PROVIDERS

    def _openai_chat_completions_url(self) -> str:
        base = self._openai_base_url
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _openai_candidate_models(self) -> List[str]:
        preferred = (self._model_override or os.getenv("OPENAI_MODEL") or config.OPENAI_MODEL or "").strip()
        candidates = [preferred, "gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"]
        out: List[str] = []
        seen = set()
        for m in candidates:
            k = (m or "").strip()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

    def _chat_openai(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        if not self._openai_key:
            if not self._warned:
                print("[LLM/OpenAI] OPENAI_API_KEY not set.")
                self._warned = True
            return None
        timeout_s = float(os.getenv("OPENAI_TIMEOUT_S") or config.OPENAI_TIMEOUT_S or 90)
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES") or getattr(config, "OPENAI_MAX_RETRIES", 2) or 2)
        backoff_base = float(os.getenv("OPENAI_RETRY_BACKOFF_S") or getattr(config, "OPENAI_RETRY_BACKOFF_S", 1.5) or 1.5)
        payload_template = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": int(max_tokens),
        }
        for model_name in self._openai_candidate_models():
            payload = {"model": model_name, **payload_template}
            data = json.dumps(payload).encode("utf-8")
            # Retry the SAME model on transient errors (429 / 5xx / timeout) so a
            # rate-limit or network blip does not silently drop a section.
            for attempt in range(max_retries + 1):
                req = urllib.request.Request(
                    self._openai_chat_completions_url(),
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._openai_key}",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    choices = body.get("choices") or []
                    if not choices:
                        break
                    message = choices[0].get("message") or {}
                    text = (message.get("content") or "").strip()
                    if not text:
                        break
                    self._last_model = model_name
                    return text
                except urllib.error.HTTPError as e:
                    if e.code in {404, 400, 403}:
                        break  # model/request problem — try next model, no retry
                    if e.code == 429 or e.code >= 500:
                        if attempt < max_retries:
                            time.sleep(backoff_base * (2 ** attempt))
                            continue
                    try:
                        err = e.read().decode("utf-8", "ignore")[:300]
                    except Exception:
                        err = ""
                    logger.warning("OpenAI HTTP error %s for %s: %s", e.code, model_name, err)
                    break
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                    if attempt < max_retries:
                        time.sleep(backoff_base * (2 ** attempt))
                        continue
                    logger.warning("OpenAI request failed for %s after %s retries: %s", model_name, max_retries, exc)
                    break
        return None

    def _chat_openrouter(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        from src.modules.pipeline.openrouter_adapter import chat_openrouter

        text, model = chat_openrouter(
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=self.temperature,
            model_override=self._model_override,
        )
        if text:
            self._openrouter_last_model = model
            self._last_model = model
        return text

    def chat_with_provider(
        self,
        provider: str,
        *,
        system: str,
        user: str,
        max_tokens: int,
    ) -> Optional[str]:
        p = normalize_chat_provider(provider)
        if p == "openai":
            return self._chat_openai(system=system, user=user, max_tokens=max_tokens)
        if p == "openrouter":
            return self._chat_openrouter(system=system, user=user, max_tokens=max_tokens)
        if not self._warned:
            print(f"[LLM] Unsupported provider '{p}'. Use OPENAI or OPENROUTER.")
            self._warned = True
        return None

    def chat(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        return self.chat_with_provider(
            self.provider,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )

    def last_model_label(self) -> str:
        if self.provider == "openai":
            return self._last_model or (os.getenv("OPENAI_MODEL") or config.OPENAI_MODEL)
        if self.provider == "openrouter":
            return self._last_model or self._openrouter_last_model or (
                os.getenv("OPENROUTER_MODEL") or getattr(config, "OPENROUTER_MODEL", "openrouter/free")
            )
        return self._last_model or ""
