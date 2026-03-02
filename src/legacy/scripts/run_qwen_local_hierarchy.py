from __future__ import annotations

import json
import os
import sys

from llama_cpp import Llama


MODEL_PATH_DEFAULT = os.path.join("models", "Qwen2.5-0.5B-Instruct-mate-q4_k_m.gguf")


def _fail(msg: str) -> None:
    raise SystemExit(msg)


def _extract_first_json_object(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None

    if s.startswith("{") and s.endswith("}"):
        return s

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


def main() -> None:
    prompt = sys.stdin.read()
    if not (prompt or "").strip():
        _fail("Empty prompt on stdin")

    model_path = os.getenv("QWEN_GGUF_PATH", MODEL_PATH_DEFAULT)
    if not os.path.exists(model_path):
        _fail(f"Model not found: {model_path}. Set QWEN_GGUF_PATH or place GGUF under models/")

    llm = Llama(
        model_path=model_path,
        n_ctx=int(os.getenv("QWEN_CTX", "4096")),
        n_threads=int(os.getenv("QWEN_THREADS", "8")),
        n_gpu_layers=0,
        logits_all=False,
        verbose=False,
    )

    out = llm(
        prompt,
        max_tokens=int(os.getenv("QWEN_MAX_TOKENS", "1024")),
        temperature=float(os.getenv("QWEN_TEMPERATURE", "0")),
        top_p=1.0,
        stop=None,
    )

    text = ""
    if isinstance(out, dict):
        text = str(out.get("choices", [{}])[0].get("text", ""))
    else:
        text = str(out)

    json_obj = _extract_first_json_object(text)
    if not json_obj:
        print(json.dumps({"tree": []}, ensure_ascii=False))
        return

    try:
        _ = json.loads(json_obj)
    except Exception:
        print(json.dumps({"tree": []}, ensure_ascii=False))
        return

    print(json_obj)


if __name__ == "__main__":
    main()
