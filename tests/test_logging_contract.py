from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

import pytest

from src.core.pipeline import run_pipeline
from src.structure.logging.pipeline_logger import PipelineLogger

# Bundled PDF used for deterministic pipeline tests (repo root relative paths).
def _law_of_tort_pdf() -> str:
    return str(Path(__file__).resolve().parents[1] / "src" / "debug" / "pdf_files" / "law_of_tort.pdf")


# Stages always written for law_of_tort.pdf (continuity drops are non-empty → 08b exists).
EXPECTED_FILES_LAW_OF_TORT: Set[str] = {
    "01_layout_lines.json",
    "02_noise_filter.json",
    "03_candidate_scoring.json",
    "03b_heading_validity_gate.json",
    "08b_continuity_filter.json",
    "07_fragments.json",
    "09_final_headings.json",
    "10_deterministic_toc.json",
    "11_book_metadata.json",
    "12_final_headings_2.json",
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
    for it in items[:5]:
        assert isinstance(it, dict)
        for k in required_keys:
            assert k in it, f"missing item key {k} in {it}"


@pytest.fixture(autouse=True)
def _run_in_tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline writes logs relative to cwd; keep tests isolated."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    yield


@pytest.mark.integration
def test_logging_contract_generates_expected_stage_files() -> None:
    """Run folder contains exactly the expected deterministic stage JSON files."""
    run_pipeline(_law_of_tort_pdf(), enable_logs=True)

    run_dir = _latest_run_dir(Path("logs"))
    files = {p.name for p in run_dir.iterdir() if p.is_file()}

    allowed = PipelineLogger._ALLOWED_FILES  # type: ignore[attr-defined]
    assert files <= allowed, f"Unexpected files not in whitelist: {sorted(files - allowed)}"
    assert EXPECTED_FILES_LAW_OF_TORT <= files, f"Missing expected files: {sorted(EXPECTED_FILES_LAW_OF_TORT - files)}"


@pytest.mark.integration
def test_each_stage_log_has_envelope_schema() -> None:
    run_pipeline(_law_of_tort_pdf(), enable_logs=True)
    run_dir = _latest_run_dir(Path("logs"))

    for name in sorted(EXPECTED_FILES_LAW_OF_TORT):
        payload = _read_json(run_dir / name)
        _assert_stage_envelope(payload)


@pytest.mark.integration
def test_stage_item_shapes_spot_check() -> None:
    run_pipeline(_law_of_tort_pdf(), enable_logs=True)
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

    gate = _assert_stage_envelope(_read_json(run_dir / "03b_heading_validity_gate.json"))
    assert isinstance(gate["items"], list)
