"""Unit tests for chapter-hierarchy artifact loading."""
from __future__ import annotations

import json

import pytest

from src.modules.generation.toc_sections import load_chapter_hierarchy_json


def _write(tmp_path, payload) -> str:
    p = tmp_path / "hierarchy.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_loads_wrapped_items_schema(tmp_path) -> None:
    # Legacy stage artifacts (e.g. s15f) wrap the hierarchy under "items".
    payload = {"stage": "15f", "items": {"chapters": [{"heading": "A"}], "meta": {}}}
    h = load_chapter_hierarchy_json(_write(tmp_path, payload))
    assert [c["heading"] for c in h["chapters"]] == ["A"]


def test_loads_top_level_chapters_schema(tmp_path) -> None:
    # Cloud-hierarchy stage (s15j) stores chapters at the top level, no wrapper.
    payload = {"meta": {}, "chapters": [{"heading": "A"}, {"heading": "B"}], "book_title": "x"}
    h = load_chapter_hierarchy_json(_write(tmp_path, payload))
    assert [c["heading"] for c in h["chapters"]] == ["A", "B"]


def test_prefers_items_when_both_present(tmp_path) -> None:
    payload = {"items": {"chapters": [{"heading": "inner"}]}, "chapters": [{"heading": "outer"}]}
    h = load_chapter_hierarchy_json(_write(tmp_path, payload))
    assert h["chapters"][0]["heading"] == "inner"


def test_rejects_non_hierarchy_payload(tmp_path) -> None:
    with pytest.raises(ValueError):
        load_chapter_hierarchy_json(_write(tmp_path, [1, 2, 3]))
