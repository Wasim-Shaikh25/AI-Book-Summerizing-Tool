from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _load_heading_run(source_path: str | Path) -> Dict[str, Any]:
    path = Path(source_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_items(run_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = run_data.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _build_occurrence_index(items: Iterable[Dict[str, Any]]) -> Dict[str, List[int]]:
    occurrences: Dict[str, List[int]] = {}
    for idx, item in enumerate(items):
        text = _normalize_text(str(item.get("text", "")))
        if not text:
            continue
        occurrences.setdefault(text, []).append(idx)
    return occurrences


def split_toc_forward_only(
    run_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Split heading records into:
    - toc_json: first occurrence of every repeated heading text
    - final_headings_json: all non-TOC headings in original order

    Rule:
    - scan forward only
    - for repeated normalized text, only the first occurrence is TOC
    - later repeated occurrences remain normal headings/fragments
    """
    items = _iter_items(run_data)
    occurrences = _build_occurrence_index(items)

    toc_items: List[Dict[str, Any]] = []
    final_items: List[Dict[str, Any]] = []

    for idx, item in enumerate(items):
        text = _normalize_text(str(item.get("text", "")))
        repeated = len(occurrences.get(text, [])) > 1 if text else False

        updated_item = dict(item)
        if repeated and occurrences[text][0] == idx:
            updated_item["is_toc"] = True
            updated_item["toc_reason"] = "forward_first_occurrence_of_repeated_heading"
            toc_items.append(updated_item)
        else:
            updated_item["is_toc"] = False
            updated_item["toc_reason"] = ""
            final_items.append(updated_item)

    base_meta = {k: v for k, v in run_data.items() if k != "items"}

    toc_data = dict(base_meta)
    toc_data["stage"] = "toc_headings"
    toc_data["total_items"] = len(toc_items)
    toc_data["items"] = toc_items

    final_data = dict(base_meta)
    final_data["stage"] = "final_headings_only"
    final_data["total_items"] = len(final_items)
    final_data["items"] = final_items

    return toc_data, final_data


def write_toc_split_outputs(
    source_path: str | Path,
    toc_output_path: str | Path,
    final_output_path: str | Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    run_data = _load_heading_run(source_path)
    toc_data, final_data = split_toc_forward_only(run_data)

    Path(toc_output_path).write_text(
        json.dumps(toc_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(final_output_path).write_text(
        json.dumps(final_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return toc_data, final_data
