"""Run stage 15f heading cleanup on saved 15e pipeline logs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get('PROJECT_ROOT', str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.modules.pipeline.stage_registry import STAGE_CLEAN_TITLES, STAGE_PARTITION_SECTIONS, STAGE_GROUP_CHAPTERS, artifact_path, require_artifact, resolve_existing_artifact
from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.generation.toc_sections import load_chapter_hierarchy_json
from src.modules.structure.dropped_heading_registry import load_dropped_registry_from_log_dir
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy


def main() -> int:
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46"))
    try:
        path_15e = require_artifact(log_dir, STAGE_GROUP_CHAPTERS)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1
    path_15f = artifact_path(log_dir, STAGE_CLEAN_TITLES, for_write=True)

    raw = load_chapter_hierarchy_json(path_15e)
    ultimate_sections: list = []
    path_15d = resolve_existing_artifact(log_dir, STAGE_PARTITION_SECTIONS)
    if path_15d is not None:
        ultimate_sections = json.loads(path_15d.read_text(encoding="utf-8")).get("items", {}).get("sections") or []
    registry = load_dropped_registry_from_log_dir(log_dir)

    weak_before = sum(
        1
        for ch in raw.get("chapters") or []
        for sec in ch.get("sections") or []
        if is_weak_section_heading(str(sec.get("heading") or ""))
    )
    print(f"15f heading cleanup on {log_dir.name}")
    print(f"  weak section titles before: {weak_before}")

    cleaned = clean_heading_hierarchy(
        raw,
        ultimate_sections=ultimate_sections,
        dropped_registry=registry,
    )
    meta = cleaned.get("meta") or {}
    print(f"  method={meta.get('heading_cleanup_method')}")
    print(f"  restored from ultimate={meta.get('heading_cleanup_restored_from_ultimate')}")
    print(f"  rule changed: sections={meta.get('heading_cleanup_rule_sections')} "
          f"subheadings={meta.get('heading_cleanup_rule_subheadings')} "
          f"chapters={meta.get('heading_cleanup_rule_chapters')}")
    print(f"  llm changed: sections={meta.get('heading_cleanup_llm_sections')} "
          f"subheadings={meta.get('heading_cleanup_llm_subheadings')} "
          f"chapters={meta.get('heading_cleanup_llm_chapters')}")
    print(f"  weak after={meta.get('weak_section_headings_after')} "
          f"dup chapters={meta.get('duplicate_chapter_names_after')}")

    payload = {
        "run_id": log_dir.name.replace("run_", ""),
        "stage": STAGE_CLEAN_TITLES,
        "items": cleaned,
    }
    path_15f.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Wrote {path_15f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
