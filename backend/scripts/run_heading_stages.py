"""Re-run heading stages 15f–15j on saved pipeline logs (no PDF re-ingest)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.generation.toc_sections import load_chapter_hierarchy_json
from src.modules.pipeline.stage_registry import (
    STAGE_15D,
    STAGE_15E,
    STAGE_15F,
    STAGE_15G,
    STAGE_15H,
    STAGE_15I,
    STAGE_15J,
    artifact_path,
    require_artifact,
    resolve_existing_artifact,
)
from src.modules.structure.dropped_heading_registry import load_dropped_registry_from_log_dir
from src.modules.structure.final_structuring.chapter_placement import run_chapter_placement
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy
from src.modules.structure.final_structuring.hierarchy_openai_refinement import run_hierarchy_openai_refinement
from src.modules.structure.final_structuring.subheading_refinement import run_heading_refinement


def _weak_count(hierarchy: dict) -> int:
    return sum(
        1
        for ch in hierarchy.get("chapters") or []
        for sec in ch.get("sections") or []
        if is_weak_section_heading(str(sec.get("heading") or ""))
    )


def _write_stage(log_dir: Path, stage_key: str, items: dict) -> Path:
    path = artifact_path(log_dir, stage_key, for_write=True)
    payload = {
        "run_id": log_dir.name.replace("run_", ""),
        "stage": stage_key,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", ""))
    if not log_dir.is_dir():
        print("[!] Set PIPELINE_LOG_DIR to an existing run log folder.")
        return 1

    try:
        path_15e = require_artifact(log_dir, STAGE_15E)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1

    raw = load_chapter_hierarchy_json(path_15e)
    ultimate_sections: list = []
    path_15d = resolve_existing_artifact(log_dir, STAGE_15D)
    if path_15d is not None:
        ultimate_sections = json.loads(path_15d.read_text(encoding="utf-8")).get("items", {}).get("sections") or []
    registry = load_dropped_registry_from_log_dir(log_dir)

    print(f"Heading stages on {log_dir.name}")
    print(f"  weak before: {_weak_count(raw)}")

    cleaned = clean_heading_hierarchy(
        raw,
        ultimate_sections=ultimate_sections,
        dropped_registry=registry,
    )
    p15f = _write_stage(log_dir, STAGE_15F, cleaned)
    print(f"  15f -> {p15f.name} weak={_weak_count(cleaned)} method={(cleaned.get('meta') or {}).get('heading_cleanup_method')}")

    placed = run_chapter_placement(cleaned)
    p15h = _write_stage(log_dir, STAGE_15H, placed)
    print(f"  15h -> {p15h.name} weak={_weak_count(placed)}")

    refined = run_heading_refinement(placed)
    p15i = _write_stage(log_dir, STAGE_15I, refined)
    meta_i = refined.get("meta") or {}
    print(
        f"  15i -> {p15i.name} weak={_weak_count(refined)} "
        f"section_fixes={meta_i.get('heading_refinement_section_titles')}"
    )

    openai_refined = run_hierarchy_openai_refinement(refined)
    p15j = _write_stage(log_dir, STAGE_15J, openai_refined)
    p15g = _write_stage(log_dir, STAGE_15G, openai_refined)
    print(f"  15j -> {p15j.name} weak={_weak_count(openai_refined)}")
    print(f"  15g -> {p15g.name} (synced with 15j)")
    print("[+] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
