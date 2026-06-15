"""Notes quality audit CLI. Legacy: ``run_notes_quality_audit.py``."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "run_notes_quality_audit.py"), run_name="__main__")
