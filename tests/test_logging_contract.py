from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

if os.getenv("RUN_INTEGRATION") != "1":
    pytest.skip("Skipping integration tests (set RUN_INTEGRATION=1 to enable).", allow_module_level=True)

from src.core.pipeline import run_pipeline


ALLOWED_FILES = {
    "01_layout_lines.json",
    "02_noise_filter.json",
    "03_candidate_scoring.json",
    "04_gemini_heading_validation.json",
    "05_gemini_toc_classification.json",
    "06_toc_section_eval.json",
    "07_fragments.json",
    "08_hierarchy.json",
    "09_final_headings.json",
    "decision_trace.json",
}


def _latest_run_dir(logs_dir: Path) -> Path:
    run_dirs = sorted(
        [p for p in logs_dir.glob("run_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
    )
    assert run_dirs, f"No run_* folders found under {logs_dir}"
    return run_dirs[-1]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_stage_envelope(payload: Any) -> Dict[str, Any]:
    assert isinstance(payload, dict), "stage log must be a JSON object"
    for k in ("run_id", "stage", "pdf_file", "timestamp", "total_items", "items"):
        assert k in payload, f"missing top-level key: {k}"
    assert isinstance(payload["items"], list), "items must be a list"
    assert isinstance(payload["total_items"], int), "total_items must be int"
    assert payload["total_items"] == len(payload["items"]), "total_items must match len(items)"
    return payload


def _assert_items_have_keys(items: List[Dict[str, Any]], required_keys: List[str]) -> None:
    # Only spot-check a few items to keep tests fast on big PDFs
    for it in items[:5]:
        assert isinstance(it, dict)
        for k in required_keys:
            assert k in it, f"missing item key {k} in {it}"


@pytest.fixture(autouse=True)
def _run_in_tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Ensure tests don't pollute project ./logs by running in a temp cwd.
    This assumes the pipeline writes logs relative to cwd (it does today).
    """
    monkeypatch.chdir(tmp_path)
    # Create minimal repo-like structure for relative paths if needed
    os.makedirs("logs", exist_ok=True)
    yield


@pytest.mark.integration
def test_logging_contract_generates_only_expected_files():
    pdf = str(Path(__file__).resolve().parents[1] / "src" / "debug" / "pdf_files" / "law_of_tort.pdf")
    run_pipeline(pdf, enable_logs=True)

    logs_dir = Path("logs")
    run_dir = _latest_run_dir(logs_dir)

    files = {p.name for p in run_dir.iterdir() if p.is_file()}
    # This test will initially fail until refactor is completed.
    assert files == ALLOWED_FILES, f"Unexpected log files: {sorted(files - ALLOWED_FILES)} / missing: {sorted(ALLOWED_FILES - files)}"


import pytest


@pytest.mark.integration
def test_each_stage_log_has_envelope_schema():
    """
    This test exercises the full pipeline with enable_logs=True.
    It may call external LLM services (Gemini) depending on configuration,
    so keep it as an integration test to avoid flaky CI/unit runs.
    """
    pdf = str(Path(__file__).resolve().parents[1] / "src" / "debug" / "pdf_files" / "law_of_tort.pdf")
    run_pipeline(pdf, enable_logs=True)

    run_dir = _latest_run_dir(Path("logs"))

    for name in sorted(ALLOWED_FILES):
        if name == "decision_trace.json":
            continue
        payload = _read_json(run_dir / name)
        _assert_stage_envelope(payload)


@pytest.mark.integration
def test_stage_item_shapes_spot_check():
    pdf = str(Path(__file__).resolve().parents[1] / "src" / "debug" / "pdf_files" / "law_of_tort.pdf")
    run_pipeline(pdf, enable_logs=True)

    run_dir = _latest_run_dir(Path("logs"))

    layout = _assert_stage_envelope(_read_json(run_dir / "01_layout_lines.json"))
    _assert_items_have_keys(
        layout["items"],
        [
            "line_id",
            "text",
            "page_number",
            "bbox",
            "x0",
            "y0",
            "x1",
            "y1",
            "page_width",
            "page_height",
            "font_size",
            "font_name",
            "is_bold",
            "is_italic",
            "x_center",
            "centered",
            "vertical_gap_above",
            "large_gap",
            "large_font",
            "is_link",
            "is_table",
            "raw_line_index",
        ],
    )

    noise = _assert_stage_envelope(_read_json(run_dir / "02_noise_filter.json"))
    _assert_items_have_keys(
        noise["items"],
        [
            "line_id",
            "text",
            "page_number",
            "decision",
            "noise_type",
            "reason",
            "margin_position",
            "confidence",
        ],
    )

    scoring = _assert_stage_envelope(_read_json(run_dir / "03_candidate_scoring.json"))
    _assert_items_have_keys(
        scoring["items"],
        [
            "line_id",
            "text",
            "page_number",
            "score",
            "signals",
            "selected",
            "score_breakdown",
            "context_preview",
            "bbox",
            "font_size",
            "bold",
            "centered",
            "large_gap",
        ],
    )
