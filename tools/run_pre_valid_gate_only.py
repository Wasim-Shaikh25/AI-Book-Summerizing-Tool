from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

# Ensure project root is on sys.path so "import src..." works when running from /tools.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from src.ingestion.pdf_extractor import extract_pdf
from src.ingestion.text_normalizer import normalize_text
from src.structure.candidate_scoring import collect_candidates_scored
from src.structure.noise_filter import mark_noise
from src.structure.pre_llm_gate import gate_heading_validity_candidates


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run pipeline only up to pre-LLM heading validity gate (no Gemini calls)."
    )
    ap.add_argument(
        "pdf",
        nargs="?",
        default="src/debug/pdf_files/law_of_tort.pdf",
        help="Path to PDF (default: src/debug/pdf_files/law_of_tort.pdf)",
    )
    args = ap.parse_args()

    pdf_path = str(args.pdf)
    if not Path(pdf_path).exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    pdf_doc = extract_pdf(pdf_path)
    lines = normalize_text(pdf_doc)

    # Noise stage (never deletes lines, but adds is_noise flags)
    lines, _noise_log = mark_noise(lines)

    # Candidate scoring
    candidates, _scoring_log = collect_candidates_scored(lines)

    # Pre-LLM gate (THIS is what we want to measure)
    kept, gate_log = gate_heading_validity_candidates(candidates, lines=lines)

    reasons = Counter()
    for it in gate_log:
        r = (it.get("reason") or "").strip()
        reasons[r] += 1

    print("== PRE-LLM HEADING VALIDITY GATE (NO GEMINI) ==")
    print(f"pdf: {Path(pdf_path).name}")
    print(f"candidates_total: {len(candidates)}")
    print(f"dropped: {len(gate_log)}")
    print(f"kept_for_llm_validity: {len(kept)}")

    print("\n-- drop reason histogram (top 20) --")
    for reason, count in reasons.most_common(20):
        print(f"{count:>4}  {reason}")

    print("\n-- dropped sample (top 20) --")
    for it in gate_log[:20]:
        hid = it.get("heading_id")
        txt = (it.get("text") or "").strip().replace("\n", " ")
        rsn = it.get("reason")
        print(f"- {hid}: {txt[:120]}  [{rsn}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
