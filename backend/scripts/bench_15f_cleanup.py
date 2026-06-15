#!/usr/bin/env python3
"""Benchmark stage 15f heading cleanup: rules vs MiniLM vs cloud LLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy


SAMPLE_WEAK = {
    "meta": {},
    "chapters": [
        {
            "chapter_id": "C1",
            "heading": "Fundamental Rights",
            "page_start": 42,
            "sections": [
                {
                    "section_id": "S1",
                    "heading": "(Art. 21)",
                    "page_number": 43,
                    "fragment": {"preview": "Protection of life and personal liberty"},
                    "subheadings": [{"heading": "(ii)", "line_id": 101, "fragment": {"preview": "Procedure established by law"}}],
                },
                {
                    "section_id": "S2",
                    "heading": "1.",
                    "page_number": 44,
                    "fragment": {"preview": "Equality before the law and equal protection of laws"},
                    "subheadings": [],
                },
            ],
        }
    ],
}


def _weak_count(hierarchy: dict) -> int:
    total = 0
    for ch in hierarchy.get("chapters") or []:
        for sec in ch.get("sections") or []:
            if is_weak_section_heading(str(sec.get("heading") or "")):
                total += 1
            for sub in sec.get("subheadings") or []:
                if is_weak_section_heading(str(sub.get("heading") or "")):
                    total += 1
    return total


def run_mode(mode: str) -> dict:
    if mode == "rules":
        os.environ["HEADING_CLEANUP_BACKEND"] = "rules_only"
        os.environ["HEADING_CLEANUP_USE_LLM"] = "false"
    elif mode == "minilm":
        os.environ["HEADING_CLEANUP_BACKEND"] = "minilm"
        os.environ["HEADING_CLEANUP_USE_LLM"] = "false"
    elif mode == "cloud":
        os.environ["HEADING_CLEANUP_BACKEND"] = "openai"
        os.environ["HEADING_CLEANUP_USE_LLM"] = "true"
    else:
        raise ValueError(mode)

    cleaned = clean_heading_hierarchy(SAMPLE_WEAK, use_llm=(mode == "cloud"))
    return {
        "mode": mode,
        "method": cleaned.get("meta", {}).get("heading_cleanup_method"),
        "weak_after": _weak_count(cleaned),
        "chapters": cleaned.get("chapters"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark 15f heading cleanup modes")
    parser.add_argument("--modes", default="rules,minilm", help="Comma-separated: rules,minilm,cloud")
    parser.add_argument("--json", action="store_true", help="Print JSON results")
    args = parser.parse_args()

    results = []
    for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
        results.append(run_mode(mode))

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for row in results:
            print(f"[{row['mode']}] method={row['method']} weak_after={row['weak_after']}")
            for ch in row.get("chapters") or []:
                for sec in ch.get("sections") or []:
                    print(f"  - {sec.get('heading')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
