"""Run notes quality audit on pipeline outputs (deterministic + optional LLM insights)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.modules.quality.service import run_quality_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated notes vs PDF and structure logs")
    parser.add_argument("--pdf", required=True, help="Source PDF path")
    parser.add_argument("--log-dir", required=True, help="Pipeline log directory (run_YYYY-MM-DD_...)")
    parser.add_argument("--md", required=True, help="Generated markdown notes path")
    parser.add_argument("--docx", default="", help="Optional DOCX path")
    parser.add_argument("--label", default="", help="Book label for report header")
    parser.add_argument("--out-dir", default="", help="Directory for report artifacts (default: MD parent)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    log_dir = Path(args.log_dir)
    md_path = Path(args.md)
    docx_path = Path(args.docx) if args.docx else None
    out_dir = Path(args.out_dir) if args.out_dir else md_path.parent

    for name, p in [("PDF", pdf_path), ("log dir", log_dir), ("markdown", md_path)]:
        if not p.exists():
            print(f"[!] Missing {name}: {p}")
            return 1

    label = args.label or md_path.stem
    _, result, paths = run_quality_audit(
        pdf_path=pdf_path,
        log_dir=log_dir,
        md_path=md_path,
        docx_path=docx_path if docx_path and docx_path.exists() else None,
        label=label,
        out_dir=out_dir,
    )

    print(f"[+] Verdict: {result.verdict_scores.get('overall')}")
    print(f"[+] Report: {paths['txt']}")
    print(f"[+] JSON: {paths['json']}")
    if paths["insights"].exists():
        print(f"[+] LLM insights: {paths['insights']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
