"""Re-export notes from saved logs → Markdown + DOCX. Legacy: ``reexport_docx.py``."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "reexport_docx.py"), run_name="__main__")
