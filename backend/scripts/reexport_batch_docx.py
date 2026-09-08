"""Re-export all four batch DOCX with correct covers and chapter placement."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent

EXPORTS = [
    (
        "family-law-43811769208_2026-06-15_11-01-43",
        "run_2026-06-15_10-58-29",
        "family-law-43811769208.pdf",
    ),
    (
        "constitutional-law-i-sem-ii-2022-23-1--43527772408_2026-06-15_11-09-56",
        "run_2026-06-15_11-05-38",
        "constitutional-law-i-sem-ii-2022-23-1--43527772408.pdf",
    ),
    (
        "environmental-law-1--43748672008_2026-06-15_11-18-25",
        "run_2026-06-15_11-15-44",
        "environmental-law-1--43748672008.pdf",
    ),
    (
        "bareact-140_2026-06-15_12-13-57",
        "run_2026-06-15_12-07-50",
        "bareact-140.pdf",
    ),
]

env = os.environ.copy()
for stem, log_run, pdf_name in EXPORTS:
    env.update(
        {
            "NOTES_MD": str(ROOT / "output" / f"{stem}.md"),
            "PIPELINE_LOG_DIR": str(ROOT / "logs" / log_run),
            "SOURCE_PDF_NAME": pdf_name,
            "PIPELINE_PDF": str(env.get("PIPELINE_PDF", pdf_name)),
            "DOCX_NAME": f"{stem}_fixed.docx",
        }
    )
    print(f"\n=== Re-export {stem} ===", flush=True)
    rc = subprocess.call([sys.executable, str(BACKEND / "scripts" / "reexport_docx.py")], env=env, cwd=str(BACKEND))
    if rc != 0:
        raise SystemExit(rc)
print("\nAll re-exports complete.")
