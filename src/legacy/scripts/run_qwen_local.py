from __future__ import annotations

import json
import os
import sys
from typing import Any

from llama_cpp import Llama


MODEL_PATH_DEFAULT = os.path.join("models", "Qwen2.5-0.5B-Instruct-mate-q4_k_m.gguf")


def _read_stdin() -> str:
    return sys.stdin.read()


def _fail(msg: str) -> None:
    raise SystemExit(msg)


def _extract_first_json_object(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None

    # Fast-path
    if s.startswith("{") and s.endswith("}"):
        return s

    # Best-effort brace matching to get the first top-level JSON object
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1].strip()

    return None


def _looks_like_json_but_broken(s: str) -> bool:
    """
    Heuristic: model started a JSON object but produced invalid JSON, e.g.
      {"headings:[]}
    """
    t = (s or "").strip()
    return t.startswith("{") and ("}" in t)


def _repair_common_json_issues(raw: str) -> str:
    """
    Minimal non-LLM repair for common Qwen slip-ups.
    We keep this conservative on purpose.

    Repairs:
      - {"headings:[]}  -> {"headings":[]}
      - smart quotes -> normal quotes
    """
    s = (raw or "").strip()

    # Normalize smart quotes
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

    # Fix the specific frequent pattern: {"headings:[]}
    s = s.replace('{"headings:[]}', '{"headings": []}')

    return s


def _wrap_prompt_json_only(prompt: str) -> str:
    """
    Strong wrapper that pushes the model into emitting *only* a JSON object.

    Key point: we MUST NOT allow the model to invent arbitrary schemas.
    We instruct it to emit EXACTLY the JSON object already present in the prompt.
    """
    p = (prompt or "").strip()
    return (
        "Return JSON only. No prose. No markdown.\n"
        "CRITICAL:\n"
        "- Your entire response MUST be exactly ONE valid JSON object.\n"
        "- You MUST output EXACTLY the JSON object provided below.\n"
        "- Do NOT add keys. Do NOT remove keys. Do NOT rename keys. Do NOT change any values.\n"
        "- Do NOT wrap in additional JSON.\n\n"
        "JSON TO ECHO (output exactly this):\n"
        f"{p}\n"
    )


def main() -> None:
    prompt = _read_stdin()
    if not prompt.strip():
        _fail("Empty prompt on stdin")

    # Determine an expected top-level JSON shape from the prompt if possible (optional).
    expected_keys: set[str] | None = None
    try:
        maybe = json.loads(prompt.strip())
        if isinstance(maybe, dict):
            expected_keys = set(maybe.keys())
    except Exception:
        expected_keys = None

    model_path = os.getenv("QWEN_GGUF_PATH", MODEL_PATH_DEFAULT)
    if not os.path.exists(model_path):
        _fail(f"Model not found: {model_path}. Set QWEN_GGUF_PATH or place GGUF under models/")

    # Keep this deterministic + CPU-only
    llm = Llama(
        model_path=model_path,
        n_ctx=int(os.getenv("QWEN_CTX", "4096")),
        n_threads=int(os.getenv("QWEN_THREADS", "8")),
        n_gpu_layers=0,
        logits_all=False,
        verbose=False,
    )

    # Use chat completion (best for instruct-tuned Qwen). Enforce JSON-only output.
    # We also wrap the user prompt to be extra strict about JSON-only.
    messages = [
        {"role": "system", "content": "You are a document structure extractor. Return JSON only."},
        {"role": "user", "content": _wrap_prompt_json_only(prompt)},
    ]

    def run_once() -> str:
        out = llm.create_chat_completion(
            messages=messages,
            temperature=float(os.getenv("QWEN_TEMPERATURE", "0")),
            top_p=1.0,
            max_tokens=int(os.getenv("QWEN_MAX_TOKENS", "1024")),
        )

        # If you need to debug the raw model output, set QWEN_DEBUG_RAW=1
        if os.getenv("QWEN_DEBUG_RAW", "").strip() == "1":
            print(json.dumps(out, ensure_ascii=False), file=sys.stderr)

        text = ""
        if isinstance(out, dict):
            # chat_completion format
            choice0 = (out.get("choices") or [{}])[0] or {}
            msg = choice0.get("message") or {}
            if isinstance(msg, dict) and "content" in msg:
                text = str(msg.get("content") or "")
            else:
                # fallback: non-chat format
                text = str(choice0.get("text", ""))
        else:
            text = str(out)
        return text

    def validate_or_none(text: str) -> dict[str, Any] | None:
        # First, try to extract a JSON object
        json_str = _extract_first_json_object(text)
        if json_str:
            try:
                obj = json.loads(json_str)
                if isinstance(obj, dict) and expected_keys is not None:
                    # Enforce exact key set: do not allow invented schemas.
                    if set(obj.keys()) != expected_keys:
                        return None
                return obj
            except Exception:
                pass

        # If it looked like JSON but was broken, try conservative repairs and re-parse
        if _looks_like_json_but_broken(text):
            repaired = _repair_common_json_issues(text)
            json_str2 = _extract_first_json_object(repaired) or repaired.strip()
            try:
                obj = json.loads(json_str2)
                if isinstance(obj, dict) and expected_keys is not None:
                    if set(obj.keys()) != expected_keys:
                        return None
                return obj
            except Exception:
                pass

        return None

    # Retry once with a stronger corrective nudge if needed
    text1 = run_once()
    obj = validate_or_none(text1)

    if obj is None:
        if os.getenv("QWEN_DEBUG_TEXT", "").strip() == "1":
            print(text1, file=sys.stderr)

        # Append an explicit correction message for retry
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous response was not valid JSON OR did not match the required schema.\n"
                    "Return ONLY the JSON object with EXACTLY the same top-level keys as provided.\n"
                    "Do not change key names. Do not add/remove keys.\n"
                ),
            }
        )
        text2 = run_once()
        obj = validate_or_none(text2)

        if obj is None:
            if os.getenv("QWEN_DEBUG_TEXT", "").strip() == "1":
                print(text2, file=sys.stderr)

            # Last resort: if the prompt itself was JSON, echo it back exactly.
            if expected_keys is not None:
                try:
                    echo = json.loads(prompt.strip())
                    print(json.dumps(echo, ensure_ascii=False))
                    return
                except Exception:
                    pass

            print(json.dumps({"headings": []}, ensure_ascii=False))
            return

    # Ensure we output JSON only (normalized)
    print(json.dumps(obj, ensure_ascii=False))


if __name__ == "__main__":
    main()
