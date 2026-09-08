"""Run stage 15g title validation on saved 15f pipeline logs."""
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

from src.modules.pipeline.stage_registry import STAGE_PARTITION_SECTIONS, STAGE_CLEAN_TITLES, STAGE_VALIDATE_TITLES, artifact_path, require_artifact
from src.modules.generation.toc_sections import load_chapter_hierarchy_json
from src.modules.structure.dropped_heading_registry import load_dropped_registry_from_log_dir
from src.modules.structure.heading_title_validation import is_citation_fragment_title
from src.modules.structure.final_structuring.title_validation import validate_chapter_hierarchy


def main() -> int:
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-06-07_17-00-37"))
    path_15f = require_artifact(log_dir, STAGE_CLEAN_TITLES)
    path_15g = artifact_path(log_dir, STAGE_VALIDATE_TITLES, for_write=True)
    ultimate = json.loads(require_artifact(log_dir, STAGE_PARTITION_SECTIONS).read_text(encoding="utf-8"))["items"]
    registry = load_dropped_registry_from_log_dir(log_dir)

    raw = load_chapter_hierarchy_json(path_15f)
    before_bad = sum(
        1
        for ch in raw.get("chapters") or []
        for sec in ch.get("sections") or []
        if is_citation_fragment_title(str(sec.get("heading") or ""))
    )
    print(f"15g title validation on {log_dir.name}")
    print(f"  citation-like titles before: {before_bad}")

    validated = validate_chapter_hierarchy(
        raw,
        ultimate_sections=ultimate.get("sections") or [],
        dropped_registry=registry,
    )
    meta = validated.get("meta") or {}
    after_bad = sum(
        1
        for ch in validated.get("chapters") or []
        for sec in ch.get("sections") or []
        if is_citation_fragment_title(str(sec.get("heading") or ""))
    )
    print(f"  rule_rejected={meta.get('title_validation_rule_rejected')}")
    print(f"  fixed={meta.get('title_validation_fixed')}")
    print(f"  kept={meta.get('title_validation_kept')}")
    print(f"  citation-like after: {after_bad}")

    payload = {
        "run_id": log_dir.name.replace("run_", ""),
        "stage": STAGE_VALIDATE_TITLES,
        "items": validated,
    }
    path_15g.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Wrote {path_15g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
