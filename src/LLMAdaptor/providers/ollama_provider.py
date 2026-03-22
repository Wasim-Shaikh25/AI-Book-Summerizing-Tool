from __future__ import annotations

import json
import os
from typing import Optional

import requests

from .base import LLMResult


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _truncate(s: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 3)] + "..."


class OllamaProvider:
    """
    Local Ollama provider.

    This provider can run any Ollama model (Qwen, Gemma, etc.).

    Requires:
      - Ollama running at http://localhost:11434
      - A Qwen model pulled, e.g. `ollama pull qwen2.5:7b`

    Uses Ollama's /api/chat endpoint.
    """

    name = "OLLAMA"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout_s: float = 600.0,
    ):
        # Some configs accidentally include a leading "a" (e.g. http://localhost:11434/a).
        # Normalize that so we don't hit /aapi/*.
        bu = (base_url or "").rstrip("/")
        if bu.endswith("/a"):
            bu = bu[:-2]
        self.base_url = bu
        self.model = os.getenv("OLLAMA_MODEL") or model
        self.timeout_s = timeout_s

    def generate(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        response_mime_type: Optional[str] = None,
    ) -> LLMResult:
        """
        Uses Ollama's /api/generate endpoint.

        NOTE:
        - Some versions expose /api/chat as well, but /api/generate is the most compatible.
        """
        url = f"{self.base_url}/api/generate"
        prompt = f"{system}\n\n{user}"

        # Keep generations short for pipeline classification tasks; the smaller model can
        # otherwise take a long time and even hit read timeouts.
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "96") or "96"),
            },
        }

        # Terminal debug logging (opt-in):
        #   set OLLAMA_HTTP_DEBUG=1
        # Optional:
        #   OLLAMA_HTTP_DEBUG_MAX_CHARS=4000
        debug = _bool_env("OLLAMA_HTTP_DEBUG", False)
        max_chars = int(os.getenv("OLLAMA_HTTP_DEBUG_MAX_CHARS", "4000") or "4000")
        if debug:
            safe_payload = dict(payload)
            safe_payload["prompt"] = _truncate(prompt, max_chars)
            print("\n[OLLAMA] Request")
            print(f"[OLLAMA] POST {url}")
            print("[OLLAMA] payload=" + json.dumps(safe_payload, ensure_ascii=False))

        # Ollama's max tokens option is `num_predict`
        if max_tokens is not None:
            payload["options"]["num_predict"] = int(max_tokens)

        # Prefer JSON mode when the caller expects JSON (our pipeline parsers do).
        # Ollama's JSON mode enforces a top-level JSON *object*, so prompts that expect a top-level
        # array would be incompatible. Our prompts (validity/hierarchy/etc.) are object-shaped.
        payload["format"] = "json"

        # Requests timeout expects seconds or (connect, read). Use (connect, read) so
        # we don't fail on long generations.
        try:
            r = requests.post(url, json=payload, timeout=(10.0, self.timeout_s))
            if debug:
                print(f"[OLLAMA] Status: {r.status_code}")
            r.raise_for_status()
        except requests.RequestException as e:
            if debug:
                print(f"[OLLAMA] Request failed: {e!r}")
                try:
                    if hasattr(e, "response") and e.response is not None:
                        print("[OLLAMA] Error body=" + _truncate(e.response.text, max_chars))
                except Exception:
                    pass
            raise

        data = r.json()
        msg = data.get("response")
        if not isinstance(msg, str):
            msg = ""

        if debug:
            # Drop huge token context arrays to keep terminal readable.
            safe_response = dict(data) if isinstance(data, dict) else {"response": data}
            if isinstance(safe_response, dict) and "context" in safe_response:
                safe_response.pop("context", None)
            if isinstance(safe_response, dict) and "response" in safe_response and isinstance(
                safe_response["response"], str
            ):
                safe_response["response"] = _truncate(safe_response["response"], max_chars)
            print("[OLLAMA] Response=" + json.dumps(safe_response, ensure_ascii=False))

        return LLMResult(text=msg, raw=data, usage=data.get("eval_count"))
