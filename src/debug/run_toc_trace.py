"""
Debug runner: end-to-end TOC trace with deterministic artifacts.

Goal (triage):
- Show what is sent to Gemini (heading validation request payload)
- Show what is received from Gemini (raw + parsed response)
- Show TOC after:
  1) candidate collection (raw)
  2) Gemini filtering (validated/filtered)
  3) fragment building
  4) hierarchy assignment
  5) TOC cleaning

This is intentionally a debug-only entrypoint. It does NOT try to "fix" logic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as a script: `python src/debug/run_toc_trace.py`
# by ensuring project root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def run(pdf_path: str) -> Path:
    """
    Thin debug wrapper around the production pipeline.

    Behavior:
      - Calls src.core.pipeline.run_pipeline(...) with logging ENABLED
      - Returns the created run folder path from the production logger
    """
    from src.core.pipeline import run_pipeline

    _, logger = run_pipeline(pdf_path, enable_logs=True, persist_to_db=True)
    if logger is None:
        raise RuntimeError("Expected enable_logs=True to return a PipelineLogger")
    return logger.run_dir


if __name__ == "__main__":
    visualize = "--visualize" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--visualize"]

    if len(args) > 0:
        pdf = args[0]
    else:
        pdf = os.getenv("PDF_PATH", "src/debug/pdf_files/input.pdf")

    out = run(pdf)

    # Optional: create a color-marked PDF for quick visual inspection.
    # This is best-effort and should never break the trace run.
    if visualize:
        try:
            from src.debug.visualizer import visualize_run

            visualize_run(pdf_path=pdf, run_dir=str(out))
            print("[+] Visualization PDF generated.")
        except Exception as e:
            print(f"[!] Visualization failed: {e}")

    print(f"[+] TOC trace written to: {out}")
