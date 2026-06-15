"""Full-book pipeline: PDF → structure → LLM rewrite → Markdown + DOCX.

Canonical entry point. See module docstring in ``run_full_openai_pipeline.py``.

Legacy alias: ``run_full_openai_pipeline.py``.
"""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "run_full_openai_pipeline.py"
    runpy.run_path(str(target), run_name="__main__")
