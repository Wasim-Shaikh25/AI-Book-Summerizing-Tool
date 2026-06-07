from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = (
    REPO_ROOT
    / "src"
    / "modules"
    / "debug"
    / "pdf_files"
    / "The Law of Torts 2018 by Jhabwala.pdf"
)


def sample_pdf_path() -> str:
    if not FIXTURE_PDF.exists():
        pytest.skip(f"Bundled PDF missing: {FIXTURE_PDF}")
    return str(FIXTURE_PDF)


@pytest.fixture(autouse=True)
def _run_in_tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline writes logs relative to cwd; keep integration tests isolated."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    yield
