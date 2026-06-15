"""Compare generated notes (MD/DOCX) against PDF structure and ingestion logs.

Thin CLI wrapper around ``src.modules.quality``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.quality.analyzer import (  # noqa: E402
    aggregate_batch_summary,
    build_report,
    dynamic_sample_section_ids,
    run_batch_audit,
)
from src.modules.quality.heuristics import (  # noqa: E402
    classify_heading,
    compute_verdict_scores,
    detect_syllabus_noise_in_body,
)
from src.modules.quality.models import BookAuditResult, Report  # noqa: E402
from src.modules.quality.service import run_quality_audit  # noqa: E402

__all__ = [
    "BookAuditResult",
    "Report",
    "aggregate_batch_summary",
    "build_report",
    "classify_heading",
    "compute_verdict_scores",
    "detect_syllabus_noise_in_body",
    "dynamic_sample_section_ids",
    "run_batch_audit",
    "run_quality_audit",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare notes quality vs PDF and ingestion logs")
    parser.add_argument("--manifest", help="JSON manifest of books to audit")
    parser.add_argument("--audit-dir", default=str(PROJECT_ROOT / "output" / "audit"))
    parser.add_argument("--combined-out", help="Combined markdown summary path")
    parser.add_argument("--json-out", help="Machine-readable JSON summary path")
    parser.add_argument(
        "--pdf",
        default=r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
    )
    parser.add_argument("--log-dir", default=str(PROJECT_ROOT / "logs" / "run_2026-05-28_13-36-46"))
    parser.add_argument(
        "--md",
        default=str(PROJECT_ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-28_14-30-12.md"),
    )
    parser.add_argument("--docx", default="")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "output" / "notes_quality_report.txt"))
    parser.add_argument("--llm", action="store_true", help="Include LLM insights (uses NOTES_QUALITY_LLM env)")
    args = parser.parse_args()

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"[!] Missing manifest: {manifest_path}")
            return 1
        combined = Path(args.combined_out) if args.combined_out else Path(args.audit_dir) / "notes_quality_audit.md"
        json_out = Path(args.json_out) if args.json_out else Path(args.audit_dir) / "notes_quality_audit.json"
        try:
            run_batch_audit(
                manifest_path,
                audit_dir=Path(args.audit_dir),
                combined_out=combined,
                json_out=json_out,
            )
        except FileNotFoundError as exc:
            print(f"[!] {exc}")
            return 1
        return 0

    pdf_path = Path(args.pdf)
    log_dir = Path(args.log_dir)
    md_path = Path(args.md)
    docx_path = Path(args.docx) if args.docx else None

    for label, p in [("PDF", pdf_path), ("log dir", log_dir), ("markdown", md_path)]:
        if not p.exists():
            print(f"[!] Missing {label}: {p}")
            return 1

    if args.llm or os.environ.get("NOTES_QUALITY_LLM", "1").strip().lower() not in {"0", "false", "no", "off"}:
        _, result, paths = run_quality_audit(
            pdf_path=pdf_path,
            log_dir=log_dir,
            md_path=md_path,
            docx_path=docx_path if docx_path and docx_path.exists() else None,
            out_dir=md_path.parent,
        )
        print(f"[+] Verdict: {result.verdict_scores.get('overall')}")
        print(f"[+] Report saved: {paths['txt']}")
        if paths["insights"].exists():
            print(f"[+] Insights: {paths['insights']}")
        return 0

    report, result = build_report(
        pdf_path=pdf_path,
        log_dir=log_dir,
        md_path=md_path,
        docx_path=docx_path if docx_path and docx_path.exists() else None,
    )
    out_path = Path(args.out)
    report.save(out_path)
    print(f"[+] Verdict: {result.verdict_scores.get('overall')}")
    print(f"[+] Report saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
