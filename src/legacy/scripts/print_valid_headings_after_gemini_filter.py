import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

# Allow running as: python scripts/xxx.py (repo root not auto-added on Windows)
sys.path.insert(0, os.getcwd())

from src.config import GEMINI_MODEL
from src.core.ai.ai_adapter import GeminiAdapter
from src.core.ai.heading_filter_prompt import build_heading_filter_prompt
from src.core.text_normalizer import PDFTextNormalizer
from src.structure.raw_span_builder import build_raw_spans
from src.utils.json_utils import safe_json_parse
from src.utils.pdf_reader import PDFReader


def _parse_model_json(text: str):
    data = safe_json_parse(text)
    if data is not None:
        return data

    # Fallback: extract first JSON object from mixed content
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    return safe_json_parse(m.group(0))


def main():
    # Load API key from environment (set it before running)
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
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

    # Batch 0: first 20 candidates
    batch = spans[:20]

    system_prompt, user_prompt = build_heading_filter_prompt(lines, batch)
    out = GeminiAdapter(api_key=key, model_name=GEMINI_MODEL).generate(
        system_prompt, user_prompt
    )

    data = _parse_model_json(out) or {}
    results = {r["span_id"]: bool(r.get("is_valid")) for r in data.get("results", [])}

    valid = [s for s in batch if results.get(s.span_id, False)]

    print("VALID_HEADINGS_AFTER_GEMINI_FILTER (batch0 first20):")
    for s in valid:
        print(f"{s.span_id}: {(s.heading_text or '').strip()}")
    print(f"TOTAL_VALID {len(valid)} OF {len(batch)}")

    print("\nRAW_MODEL_OUTPUT_PREFIX:", (out or "")[:160].replace("\n", " "))


if __name__ == "__main__":
    main()
