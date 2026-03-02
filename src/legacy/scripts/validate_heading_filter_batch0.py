import os
import re
import sys

# Allow running as: python scripts/xxx.py
sys.path.insert(0, os.getcwd())

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.utils.debug_logger import debug_log
from src.core.ai.ai_adapter import GeminiAdapter
from src.core.ai.heading_filter_prompt import build_heading_filter_prompt
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.raw_span_builder import build_raw_spans
from src.utils.json_utils import safe_json_parse
from src.utils.pdf_reader import PDFReader


def clean_model_output(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
    return text.strip()


def _parse_json(text: str):
    """
    Parse model output that may include:
      - plain JSON
      - ```json fenced JSON
      - additional prose before/after JSON
    """
    raw = clean_model_output(text)

    # 1) fast path: direct
    data = safe_json_parse(raw)
    if data is not None:
        return data

    # 2) try to pull out a fenced JSON block
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fence:
        inner = fence.group(1).strip()
        data = safe_json_parse(inner)
        if data is not None:
            return data

    # 3) fallback: extract first JSON object
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    return safe_json_parse(m.group(0))


def _get_key():
    # Prefer shared config loader which falls back to `.env`
    return GEMINI_API_KEY or ""


def main():
    key = _get_key()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY / GOOGLE_API_KEY in environment")

    pages, _ = PDFReader("reference_files").read_all_pdfs(
        specific_file="reference_files/law_of_tort.pdf"
    )
    res = PDFTextNormalizer().normalize(pages)
    lines = res["lines"]
    heading_indices = sorted(
        int(h["index"]) for h in res.get("heading_metadata", []) if "index" in h
    )
    spans = build_raw_spans(lines, heading_indices)

    batch = spans[:20]

    adapter = GeminiAdapter(api_key=key, model_name=GEMINI_MODEL)

    # We currently have ONLY the validator prompt in build_heading_filter_prompt.
    # So we treat this as a single pass validator that checks a *previous model output*.
    # Since we don't have a separate classifier prompt wired here anymore, we validate against a
    # simple baseline decision: everything invalid, reason="" (this is enough to surface contradictions
    # like: "invalid but clearly a heading with blank lines/numbering").
    baseline_results = {"results": [{"span_id": s.span_id, "is_valid": False, "reason": ""} for s in batch]}

    val_system, val_user = build_heading_filter_prompt(lines, batch_spans=batch, model_results=baseline_results)
    val_out = adapter.generate(val_system, val_user)

    # Persist full raw output for debugging (terminal truncation was hiding JSON end)
    os.makedirs("output", exist_ok=True)
    with open("output/heading_filter_batch0_raw.txt", "w", encoding="utf-8") as f:
        f.write(val_out or "")

    val_data = _parse_json(val_out) or {}

    debug_log("VALIDATOR RAW OUTPUT (prefix)", (val_out or "")[:1200])
    debug_log("VALIDATOR PARSED JSON", val_data)

    print("\n=== VALIDATION RESULTS (parsed) ===")
    vr = val_data.get("validation_results")
    if vr is None:
        # Sometimes models return a different key; fall back if needed.
        vr = val_data.get("results")
    vr = vr or []

    # New strict prompt returns: {results:[{span_id,is_valid,reason}]}
    if vr and "is_valid" in (vr[0] or {}):
        for item in vr:
            sid = item.get("span_id")
            is_valid = item.get("is_valid")
            reason = item.get("reason")
            print(f"{sid}: is_valid={is_valid} - {reason}")

        focus = {12, 18, 19}
        print("\n=== FOCUS (12/18/19) ===")
        for item in vr:
            if item.get("span_id") in focus:
                print(f"{item.get('span_id')}: is_valid={item.get('is_valid')} - {item.get('reason')}")
    else:
        # Legacy validator mode: {validation_results:[{span_id,status,validation_reason}]}
        for item in vr:
            sid = item.get("span_id")
            status = item.get("status")
            reason = item.get("validation_reason")
            print(f"{sid}: {status} - {reason}")

        needs_review = [i for i in vr if i.get("status") == "needs_review"]
        approved = [i for i in vr if i.get("status") == "approved"]
        print(f"\nTOTAL approved={len(approved)} needs_review={len(needs_review)}")


if __name__ == "__main__":
    main()
