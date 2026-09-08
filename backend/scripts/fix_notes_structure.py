"""Post-process generated notes Markdown to fix structural defects.

Runs *after* the rewrite/export stage. It repairs noisy section headings,
flags (optionally merges) near-duplicate sections, and flags (optionally drops)
sections whose source was an index/contents-style list. Section body prose is
never edited. The Table of Contents is regenerated from the repaired headings.

Also invoked automatically by ``run_full_openai_pipeline.py`` when
``NOTES_STRUCTURE_FIX_ENABLED=1`` (default).

Examples (PowerShell):
  python scripts/fix_notes_structure.py --md output/book.md
  python scripts/fix_notes_structure.py --md output/book.md --engine minilm
  python scripts/fix_notes_structure.py --md output/book.md `
      --log-dir logs/run_2026-06-15_07-46-09 --drop-low-grounding --merge-duplicates
"""
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

from src.modules.generation.structure_fix_runner import (  # noqa: E402
    build_source_by_id_from_log_dir,
    build_structure_fix_chat,
    run_structure_fix,
    write_structure_fix_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix structural defects in notes Markdown")
    parser.add_argument("--md", required=True, help="Generated markdown notes path")
    parser.add_argument(
        "--engine",
        choices=["hybrid", "minilm", "api"],
        default="hybrid",
        help="Heading-repair engine (default: hybrid = LLM with MiniLM/offline fallback)",
    )
    parser.add_argument("--log-dir", default="", help="Pipeline log dir (enables low-grounding check)")
    parser.add_argument("--out", default="", help="Output MD path (default: <stem>.fixed.md)")
    parser.add_argument("--report", default="", help="Change report JSON path (default: <stem>.structure_fix.json)")
    parser.add_argument("--merge-duplicates", action="store_true", help="Actually merge near-identical adjacent sections")
    parser.add_argument("--drop-low-grounding", action="store_true", help="Drop index/contents-style sections (needs --log-dir)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the input MD instead of writing <stem>.fixed.md")
    args = parser.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"[!] Missing markdown: {md_path}")
        return 1

    md_text = md_path.read_text(encoding="utf-8")
    log_dir = Path(args.log_dir) if args.log_dir else None
    if log_dir and log_dir.exists():
        try:
            source_count = len(build_source_by_id_from_log_dir(log_dir))
            print(f"[i] Loaded source text for {source_count} sections from {log_dir}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[!] Could not reconstruct source text: {exc}")
    elif args.drop_low_grounding:
        print("[!] --drop-low-grounding ignored: requires --log-dir to detect grounding.")

    if args.engine == "api":
        chat, model_label = build_structure_fix_chat("api")
        if chat is None:
            print("[!] engine=api requires an LLM provider, but chat is not enabled.")
            return 1
    elif args.engine == "hybrid":
        chat, model_label = build_structure_fix_chat("hybrid")
        if chat is None:
            print("[i] LLM chat not enabled — heading repair falls back to MiniLM/offline.")
    else:
        chat, model_label = None, "offline"

    new_md, report = run_structure_fix(
        md_text,
        log_dir=log_dir if log_dir and log_dir.exists() else None,
        engine=args.engine,
        merge_duplicates=args.merge_duplicates,
        drop_low_grounding=args.drop_low_grounding,
    )

    out_path = md_path if args.in_place else (Path(args.out) if args.out else md_path.with_suffix(".fixed.md"))
    report_path = Path(args.report) if args.report else md_path.with_suffix(".structure_fix.json")

    out_path.write_text(new_md, encoding="utf-8")
    write_structure_fix_report(report, report_path)

    print("=" * 60)
    print(f"Engine:               {report.engine} (heading model: {report.heading_model})")
    print(f"Sections:             {report.sections_total}")
    print(f"Noisy headings:       {report.headings_noisy}")
    print(f"Headings repaired:    {report.headings_repaired}")
    print(f"Duplicate pairs:      {report.duplicate_pairs} (merged: {report.duplicates_merged})")
    print(f"Low-grounding:        {report.low_grounding_flagged} flagged (dropped: {report.low_grounding_dropped})")
    for note in report.notes:
        print(f"  note: {note}")
    print(f"Fixed MD:             {out_path}")
    print(f"Change report:        {report_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
