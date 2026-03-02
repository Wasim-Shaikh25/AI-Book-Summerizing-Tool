import json
import os
import pathlib
import re
import sys

# Allow running as: python scripts/xxx.py
sys.path.insert(0, os.getcwd())

from src.core.text_normalizer import PDFTextNormalizer
from src.structure.raw_span_builder import build_raw_spans
from src.utils.pdf_reader import PDFReader


def main() -> None:
    # Rebuild spans to map span_id -> heading_text
    pages, _ = PDFReader("reference_files").read_all_pdfs(
        specific_file="reference_files/law_of_tort.pdf"
    )
    res = PDFTextNormalizer().normalize(pages)
    lines = res["lines"]
    heading_indices = sorted(
        int(h["index"]) for h in res.get("heading_metadata", []) if "index" in h
    )
    spans = build_raw_spans(lines, heading_indices)
    span_by_id = {s.span_id: s for s in spans}

    # Read model output (fenced JSON)
    raw = pathlib.Path("output/heading_filter_batch0_raw.txt").read_text(
        encoding="utf-8"
    )
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.I)
    j = (m.group(1) if m else raw).strip()
    data = json.loads(j)

    valid = [r for r in (data.get("results") or []) if r.get("is_valid") is True]

    print("=== TRUE HEADINGS (batch0) ===")
    for r in valid:
        sid = int(r.get("span_id"))
        heading_text = span_by_id.get(sid).heading_text if sid in span_by_id else ""
        reason = r.get("reason")
        print(f"{sid}: {heading_text} | {reason}")


if __name__ == "__main__":
    main()
