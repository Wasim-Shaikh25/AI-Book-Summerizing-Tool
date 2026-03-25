from __future__ import annotations

import json
import time
from typing import Optional

import requests

from .base import LLMResult




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
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
    ):
        from src import config as cfg

        base_url = (base_url or getattr(cfg, "OLLAMA_BASE_URL", "") or getattr(cfg, "LLM_BASE_URL", "") or "http://localhost:11434").strip()
        model = (model or getattr(cfg, "OLLAMA_MODEL", "") or getattr(cfg, "LLM_MODEL", "") or "llama3.2:3b").strip()
        timeout_s = float(timeout_s if timeout_s is not None else getattr(cfg, "OLLAMA_TIMEOUT_S", None) or getattr(cfg, "LLM_TIMEOUT_S", 600.0))

        # Some configs accidentally include a trailing "/a" (e.g. http://localhost:11434/a).
        # Normalize that so we don't hit /aapi/*.
        bu = (base_url or "").rstrip("/")
        if bu.endswith("/a"):
            bu = bu[:-2]
        self.base_url = bu
        self.model = model
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
        from src import config as cfg

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": float(temperature),
            },
        }

        debug = bool(getattr(cfg, "OLLAMA_HTTP_DEBUG", None) if getattr(cfg, "OLLAMA_HTTP_DEBUG", None) is not None else getattr(cfg, "LLM_HTTP_DEBUG", False))
        max_chars = int(getattr(cfg, "OLLAMA_HTTP_DEBUG_MAX_CHARS", None) or 4000)
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
        t0 = time.perf_counter()
        try:
            r = requests.post(url, json=payload, timeout=(10.0, self.timeout_s))
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if debug:
                print(f"[OLLAMA] Status: {r.status_code}")
                print(f"[OLLAMA] latency_ms={latency_ms}")
            r.raise_for_status()
        except requests.RequestException as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if debug:
                print(f"[OLLAMA] latency_ms={latency_ms}")
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

        # Ollama typically includes the resolved model name in `model` in the response.
        resolved_model = None
        if isinstance(data, dict):
            resolved_model = data.get("model")

        return LLMResult(
            text=msg,
            raw=data,
            usage=data.get("eval_count"),
            model=str(resolved_model or self.model),
            latency_ms=latency_ms,
        )
