"""Re-export notes markdown to Word using the universal academic format (Times New Roman 11pt).

Usage:
  python backend/scripts/export_universal_docx.py output/notes.md
  python backend/scripts/export_universal_docx.py output/notes.md -o output/notes_formatted.docx --theme bw
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

from src.modules.export.markdown_docx_renderer import export_markdown_file_to_docx
from src.shared.document_format_style import format_spec_summary, resolve_typography


def _apply_universal_env() -> None:
    """Ensure Times New Roman academic defaults unless user already set overrides."""
    os.environ.setdefault("DOCX_FONT_FAMILY", "Times New Roman")
    os.environ.setdefault("DOCX_BODY_SIZE_PT", "11")
    os.environ.setdefault("DOCX_H1_SIZE_PT", "20")
    os.environ.setdefault("DOCX_H2_SIZE_PT", "16")
    os.environ.setdefault("DOCX_H3_SIZE_PT", "13")
    os.environ.setdefault("DOCX_LINE_SPACING", "1.2")
    os.environ.setdefault("DOCX_FIRST_LINE_INDENT", "1")
    os.environ.setdefault("DOCX_FIRST_LINE_INDENT_IN", "0.3")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export markdown notes to universal-format DOCX.")
    parser.add_argument("markdown", type=Path, help="Path to .md notes file")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .docx path")
    parser.add_argument(
        "--theme",
        choices=("color", "bw"),
        default=os.environ.get("DOCX_THEME", "color"),
        help="Word color theme (headings accent vs black & white)",
    )
    args = parser.parse_args()

    md_path = args.markdown.resolve()
    if not md_path.is_file():
        print(f"Not found: {md_path}", file=sys.stderr)
        return 1

    _apply_universal_env()
    os.environ["DOCX_THEME"] = args.theme

    out_path = (args.output or md_path.with_suffix(".docx")).resolve()
    md_text = md_path.read_text(encoding="utf-8")
    export_markdown_file_to_docx(md_text, out_path, theme=args.theme)

    typo = resolve_typography()
    print(f"Wrote: {out_path}")
    print(f"Typography: {format_spec_summary()}")
    print(f"  body={typo.body_font} {typo.body_size_pt}pt | H1/H2/H3={typo.h1_size_pt}/{typo.h2_size_pt}/{typo.h3_size_pt}pt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
