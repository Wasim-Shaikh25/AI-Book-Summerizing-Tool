"""Run stage 15f heading cleanup on saved 15e pipeline logs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.generation.toc_sections import load_chapter_hierarchy_json
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy


def main() -> int:
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46"))
    path_15e = log_dir / "15e_chapter_hierarchy.json"
    path_15f = log_dir / "15f_heading_cleanup.json"

    if not path_15e.exists():
        print(f"[!] Missing {path_15e}")
        return 1

    raw = load_chapter_hierarchy_json(path_15e)
    weak_before = sum(
        1
        for ch in raw.get("chapters") or []
        for sec in ch.get("sections") or []
        if is_weak_section_heading(str(sec.get("heading") or ""))
    )
    print(f"15f heading cleanup on {log_dir.name}")
    print(f"  weak section titles before: {weak_before}")

    cleaned = clean_heading_hierarchy(raw)
    meta = cleaned.get("meta") or {}
    print(f"  method={meta.get('heading_cleanup_method')}")
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
        "stage": "15f_heading_cleanup",
        "items": cleaned,
    }
    path_15f.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Wrote {path_15f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
