"""Build rewritten_map sidecar from existing markdown + hierarchy (retroactive fix)."""
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

from src.modules.export.docx_notes_exporter import resolve_rewritten_map
from src.modules.generation.rewrite_validation import (
    default_rewritten_map_path,
    save_rewritten_map,
    validate_rewrite_coverage,
    write_validation_report,
)
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy


def main() -> int:
    md_path = Path(
        os.environ.get(
            "NOTES_MD",
            str(PROJECT_ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-28_14-30-12.md"),
        )
    )
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46"))
    if not md_path.exists():
        print(f"[!] Missing {md_path}")
        return 1

    from src.modules.pipeline.stage_registry import STAGE_PARTITION_SECTIONS, STAGE_PARTITION_TREE, require_artifact

    ultimate = json.loads(require_artifact(log_dir, STAGE_PARTITION_SECTIONS).read_text(encoding="utf-8"))["items"]
    hierarchy_rows = json.loads(require_artifact(log_dir, STAGE_PARTITION_TREE).read_text(encoding="utf-8")).get("items") or []
    hierarchy = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=0,
    )

    md_text = md_path.read_text(encoding="utf-8")
    rewritten = resolve_rewritten_map(hierarchy, md_text=md_text)
    validation = validate_rewrite_coverage(hierarchy, rewritten)

    sidecar = default_rewritten_map_path(md_path)
    save_rewritten_map(sidecar, rewritten, meta={"built_from_md": str(md_path)})
    write_validation_report(md_path.with_name(md_path.stem + ".rewrite_validation.json"), validation)

    print(f"[+] Sidecar: {sidecar} ({len(rewritten)} sections)")
    for line in validation.summary_lines():
        print(f"    {line}")
    return 0 if validation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
