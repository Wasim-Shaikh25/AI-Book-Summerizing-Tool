from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from src import config

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
except Exception:  # pragma: no cover
    Llama = None  # type: ignore

_DEFAULT_3B_FILENAME = "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
_DEFAULT_3B_URLS = [
    "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf?download=true",
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf?download=true",
]
_DEFAULT_15B_FILENAME = "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
_DEFAULT_15B_URLS = [
    "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf?download=true",
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf?download=true",
]

_CHAT_PROVIDERS = frozenset({"llamacpp", "ollama", "openai", "chatgpt", "gemini"})


def normalize_chat_provider(raw: str) -> str:
    p = (raw or "").strip().lower()
    aliases = {"chatgpt": "openai", "google": "gemini", "local": "llamacpp"}
    return aliases.get(p, p)


def _models_dir() -> str:
    p = os.path.join(config.BASE_DIR, "models")
    os.makedirs(p, exist_ok=True)
    return p


def _download_gguf(url: str, dest: str, timeout_s: int = 600) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())
        return os.path.exists(dest) and os.path.getsize(dest) > 1024 * 1024
    except Exception:
        return False


def ensure_local_rewrite_model() -> str:
    rewrite_model_path = (config.REWRITE_LLAMACPP_MODEL_PATH or "").strip()
    if rewrite_model_path and os.path.exists(rewrite_model_path):
        return rewrite_model_path

    models_dir = _models_dir()
    path_3b = os.path.join(models_dir, _DEFAULT_3B_FILENAME)
    path_15b = os.path.join(models_dir, _DEFAULT_15B_FILENAME)
    path_05b = os.path.join(models_dir, "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf")

    if os.path.exists(path_3b):
        return path_3b
    if os.path.exists(path_15b):
        return path_15b

    generic_model_path = (config.LLAMACPP_MODEL_PATH or "").strip()
    if generic_model_path and os.path.exists(generic_model_path):
        return generic_model_path

    fail_marker = os.path.join(models_dir, ".rewrite_model_download_failed")
    if os.path.exists(fail_marker):
        try:
            age_s = time.time() - os.path.getmtime(fail_marker)
            if age_s < 12 * 3600:
                if os.path.exists(path_05b):
                    return path_05b
                if os.path.exists(path_15b):
                    return path_15b
        except Exception:
            pass

    configured_urls = [u.strip() for u in (config.REWRITE_LLAMACPP_MODEL_URLS or "").split(",") if u.strip()]
    if configured_urls:
        for url in configured_urls:
            name = os.path.basename(urllib.parse.urlparse(url).path) or _DEFAULT_3B_FILENAME
            if "?" in name:
                name = name.split("?")[0]
            target = os.path.join(models_dir, name) if name.endswith(".gguf") else path_3b
            if _download_gguf(url, target, timeout_s=600):
                return target
    else:
        for url in _DEFAULT_3B_URLS:
            if _download_gguf(url, path_3b, timeout_s=600):
                return path_3b
        for url in _DEFAULT_15B_URLS:
            if _download_gguf(url, path_15b, timeout_s=300):
                return path_15b

    try:
        with open(fail_marker, "w", encoding="utf-8") as f:
            f.write("failed\n")
    except Exception:
        pass

    if os.path.exists(path_05b):
        return path_05b
    if os.path.exists(path_15b):
        return path_15b
    return path_3b


class LlmChatClient:
    """Unified chat client for all pipeline stages."""

    def __init__(
        self,
        provider: str,
        *,
        model_override: str = "",
        temperature: float = 0.2,
        llamacpp_model_path: str = "",
    ) -> None:
        self.provider = normalize_chat_provider(provider)
        self._model_override = (model_override or "").strip()
        self.temperature = temperature
        self._llama: Any = None
        self._model_path = (llamacpp_model_path or ensure_local_rewrite_model()).strip()
        self._last_model = ""
        self._warned = False
        self._gemini_key = (os.getenv("GEMINI_API_KEY") or config.GEMINI_API_KEY or "").strip()
        self._openai_key = (os.getenv("OPENAI_API_KEY") or config.OPENAI_API_KEY or "").strip()
        self._openai_base_url = (
            os.getenv("OPENAI_BASE_URL") or config.OPENAI_BASE_URL or "https://api.openai.com"
        ).rstrip("/")

    @classmethod
    def from_config(cls, *, model_override: str = "", temperature: float = 0.2) -> "LlmChatClient":
        return cls(config.LLM_PROVIDER, model_override=model_override, temperature=temperature)

    @property
    def chat_enabled(self) -> bool:
        return self.provider in _CHAT_PROVIDERS

    def _resolve_ollama_model(self) -> str:
        if self._model_override:
            return self._model_override
        rev = (getattr(config, "DOUBTED_REVALIDATION_MODEL", None) or "").strip()
        if rev:
            return rev
        return config.OLLAMA_MODEL or "qwen2.5:0.5b-instruct"

    def _llama(self):
        if Llama is None:
            return None
        if self._llama is not None:
            return self._llama
        path = self._model_path
        if not path or not os.path.exists(path):
            generic = (config.LLAMACPP_MODEL_PATH or "").strip()
            if generic and os.path.exists(generic):
                path = generic
            else:
                return None
        try:
            self._llama = Llama(
                model_path=path,
                n_ctx=min(int(config.LLAMACPP_N_CTX or 4096), 8192),
                n_gpu_layers=int(config.LLAMACPP_N_GPU_LAYERS or 0),
                verbose=False,
            )
            self._model_path = path
            return self._llama
        except Exception:
            return None

    def _chat_llamacpp(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        llm = self._llama()
        if llm is None:
            if not self._warned:
                print("[LLM/llama.cpp] Local GGUF model unavailable.")
                self._warned = True
            return None
        try:
            out = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
            )
            self._last_model = self._model_path
            return ((out.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        except Exception as e:
            if not self._warned:
                print(f"[LLM/llama.cpp] {e}")
                self._warned = True
            return None

    def _chat_ollama(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        base = (config.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
        model = self._resolve_ollama_model()
        timeout = min(float(config.OLLAMA_TIMEOUT_S or 120), 90.0)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": self.temperature, "num_predict": max_tokens},
        }
        req = urllib.request.Request(
            f"{base}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self._last_model = model
            return (body.get("message") or {}).get("content") or ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            if not self._warned:
                print(f"[LLM/Ollama] Unavailable ({e}); model={model}")
                self._warned = True
            return None

    def _gemini_candidate_models(self) -> List[str]:
        preferred = (os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL or "").strip()
        candidates = [preferred, "models/gemini-3.1-flash-lite", "models/gemini-2.5-flash", "models/gemini-flash-latest"]
        out: List[str] = []
        seen = set()
        for m in candidates:
            k = (m or "").strip()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

    def _chat_gemini(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        if not self._gemini_key:
            if not self._warned:
                print("[LLM/Gemini] GEMINI_API_KEY not set.")
                self._warned = True
            return None
        payload = {
            "contents": [{"parts": [{"text": f"System:\n{system}\n\nUser:\n{user}"}]}],
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": int(max_tokens)},
        }
        timeout_s = float(os.getenv("GEMINI_TIMEOUT_S") or config.GEMINI_TIMEOUT_S or 90)
        for model_name in self._gemini_candidate_models():
            endpoint = (
                f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent"
                f"?key={self._gemini_key}"
            )
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                candidates = body.get("candidates") or []
                if not candidates:
                    continue
                parts = ((candidates[0].get("content") or {}).get("parts") or [])
                if not parts:
                    continue
                self._last_model = model_name
                return parts[0].get("text")
            except urllib.error.HTTPError as e:
                if e.code in {404, 400}:
                    continue
                try:
                    err = e.read().decode("utf-8", "ignore")[:300]
                except Exception:
                    err = ""
                logger.warning("Gemini HTTP error %s for %s: %s", e.code, model_name, err)
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue
        return None

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
        for model_name in self._openai_candidate_models():
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.temperature,
                "max_tokens": int(max_tokens),
            }
            req = urllib.request.Request(
                self._openai_chat_completions_url(),
                data=json.dumps(payload).encode("utf-8"),
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
                    continue
                message = choices[0].get("message") or {}
                text = (message.get("content") or "").strip()
                if not text:
                    continue
                self._last_model = model_name
                return text
            except urllib.error.HTTPError as e:
                if e.code in {404, 400, 403}:
                    continue
                try:
                    err = e.read().decode("utf-8", "ignore")[:300]
                except Exception:
                    err = ""
                logger.warning("OpenAI HTTP error %s for %s: %s", e.code, model_name, err)
                return None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue
        return None

    def chat_with_provider(
        self,
        provider: str,
        *,
        system: str,
        user: str,
        max_tokens: int,
    ) -> Optional[str]:
        p = normalize_chat_provider(provider)
        if p == "llamacpp":
            return self._chat_llamacpp(system=system, user=user, max_tokens=max_tokens)
        if p == "ollama":
            return self._chat_ollama(system=system, user=user, max_tokens=max_tokens)
        if p == "openai":
            return self._chat_openai(system=system, user=user, max_tokens=max_tokens)
        if p == "gemini":
            return self._chat_gemini(system=system, user=user, max_tokens=max_tokens)
        return None

    def chat(self, *, system: str, user: str, max_tokens: int) -> Optional[str]:
        return self.chat_with_provider(
            self.provider,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )

    def last_model_label(self) -> str:
        if self.provider == "llamacpp":
            return self._last_model or self._model_path
        if self.provider == "openai":
            return self._last_model or (os.getenv("OPENAI_MODEL") or config.OPENAI_MODEL)
        if self.provider == "gemini":
            return self._last_model or (os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL)
        return self._last_model or self._resolve_ollama_model()
