"""Audit section headings in a chapter hierarchy artifact."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.quality.heuristics import classify_heading
from src.modules.structure.dropped_heading_registry import is_acceptable_study_title


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "")
    if not path.exists():
        print(f"[!] Missing: {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") or data
    for ch in items.get("chapters") or []:
        for sec in ch.get("sections") or []:
            h = str(sec.get("heading") or "")
            cls = classify_heading(h)
            ok = is_acceptable_study_title(h)
            if cls != "looks_ok" or not ok:
                print(f"{sec.get('section_id'):4} [{cls:20}] ok={ok} {h[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
