"""Load rewrite sections from 15e chapter hierarchy, 15d ultimate_sections, or legacy TOC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.modules.pipeline.stage_registry import (
    STAGE_15D,
    STAGE_15E,
    STAGE_15F,
    STAGE_15G,
    STAGE_15H,
    resolve_existing_artifact,
)
from src.shared.models import NormalizedLine
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.storage.toc_repository import TocRepository


def _logs_dir(logs_dir: str | Path | None = None) -> Path:
    if logs_dir is not None:
        return Path(logs_dir)
    from src import config

    return Path(getattr(config, "LOGS_FOLDER", "logs"))


def _pdf_matches_run(run_dir: Path, pdf_name: str) -> bool:
    meta = resolve_existing_artifact(run_dir, "book_metadata")
    if meta is None:
        return True
    try:
        meta_data = json.loads(meta.read_text(encoding="utf-8"))
        pdf_file = meta_data.get("pdf_file")
        if pdf_file and pdf_name not in str(pdf_file):
            return False
    except Exception:
        pass
    return True


def _line_text_map(lines: Sequence[NormalizedLine]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for ln in lines:
        lid = getattr(ln, "line_id", None)
        if isinstance(lid, int):
            out[lid] = getattr(ln, "text", "") or ""
    return out


def _span_text(line_text: Dict[int, str], start_line: Any, end_line: Any) -> str:
    if start_line is None or end_line is None:
        return ""
    try:
        start, end = int(start_line), int(end_line)
    except (TypeError, ValueError):
        return ""
    if end < start:
        end = start
    parts: List[str] = []
    for lid in range(start, end + 1):
        t = (line_text.get(lid) or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def _body_from_15d_row(row: Dict[str, Any], line_text: Dict[int, str]) -> str:
    frag = row.get("fragment") or {}
    body = _span_text(line_text, frag.get("start_line"), frag.get("end_line"))
    if body:
        return body
    preview = str(frag.get("preview") or "").strip()
    return preview


def _substantive_subheading_labels(subs: Sequence[Dict[str, Any]], *, min_chars: int = 40) -> List[str]:
    """Subheadings that carry enough source text to deserve a rewrite subtopic line."""
    labels: List[str] = []
    for sub in subs:
        h = str(sub.get("heading") or "").strip()
        if not h:
            continue
        frag = sub.get("fragment") or {}
        chars = int(frag.get("chars") or 0)
        preview = str(frag.get("preview") or "").strip()
        if chars >= min_chars or len(preview) >= min_chars:
            labels.append(h)
    return labels


def build_source_text_by_id(
    hierarchy: Dict[str, Any],
    line_text_by_id: Dict[int, str],
) -> Dict[str, str]:
    """Reconstruct the exact per-section source text the rewrite consumed.

    Keyed by section_id over the resolved chapter hierarchy, using the same span
    merge as the rewrite loader so audits compare notes against real source
    (not a truncated preview). Subject-agnostic.
    """
    out: Dict[str, str] = {}
    for chapter in hierarchy.get("chapters") or []:
        for sec in chapter.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            if not sid:
                continue
            out[sid] = _merge_section_body(sec, line_text_by_id)
    return out


def line_text_map_from_records(records: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    """Build a line_id -> text map from raw layout-line artifact records."""
    out: Dict[int, str] = {}
    for rec in records or []:
        lid = rec.get("line_id") if isinstance(rec, dict) else None
        if isinstance(lid, int):
            out[lid] = str(rec.get("text") or "")
    return out


def _merge_section_body(
    sec: Dict[str, Any],
    line_text: Dict[int, str],
    *,
    min_chars: int = 10,
) -> str:
    """Merge section + subheading text; fall back to preview/heading so rewrite units match hierarchy."""
    body = _body_from_15d_row(sec, line_text)
    subs = sec.get("subheadings") or []
    sub_blocks: List[str] = []
    for sub in subs:
        sub_heading = str(sub.get("heading") or "").strip()
        sub_body = _body_from_15d_row(sub, line_text)
        if sub_heading and sub_body:
            sub_blocks.append(f"### {sub_heading}\n{sub_body}")
    merged = body
    if sub_blocks:
        merged = (body + "\n\n" + "\n\n".join(sub_blocks)).strip() if body else "\n\n".join(sub_blocks)
    if len(merged) >= min_chars or subs:
        return merged
    heading = str(sec.get("heading") or "").strip()
    frag = sec.get("fragment") or {}
    preview = str(frag.get("preview") or "").strip()
    extra: List[str] = []
    if preview:
        extra.append(preview)
    for sub in subs:
        sub_frag = sub.get("fragment") or {}
        sub_preview = str(sub_frag.get("preview") or "").strip()
        if sub_preview:
            extra.append(sub_preview)
    if extra:
        return "\n\n".join(extra).strip()
    return heading


def load_ultimate_sections_json(path: str | Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, dict):
        raise ValueError(f"Invalid 15d payload in {path}")
    return items


def load_chapter_hierarchy_json(path: str | Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid chapter hierarchy payload in {path}")
    # Two equivalent on-disk schemas exist and both must load:
    #   * legacy stage artifacts wrap the hierarchy under "items"
    #     (e.g. s15f_heading_cleanup.json -> {"items": {"chapters": [...]}})
    #   * the cloud-hierarchy stage stores chapters at the top level
    #     (e.g. s15j_hierarchy_openai.json -> {"chapters": [...], "meta": {...}})
    inner = data.get("items")
    if isinstance(inner, dict) and inner.get("chapters") is not None:
        return inner
    if data.get("chapters") is not None:
        return data
    if isinstance(inner, dict):
        return inner
    raise ValueError(f"Invalid chapter hierarchy payload in {path}")


def find_latest_hierarchy_log(*, pdf_name: str, logs_dir: str | Path | None = None) -> Optional[Path]:
    """Prefer validated 15g artifact, then 15f, then raw 15e."""
    base = _logs_dir(logs_dir)
    if not base.is_dir():
        return None
    for run_dir in sorted(base.glob("run_*"), reverse=True):
        if not _pdf_matches_run(run_dir, pdf_name):
            continue
        for stage_key in (STAGE_15G, STAGE_15H, STAGE_15F, STAGE_15E):
            path = resolve_existing_artifact(run_dir, stage_key)
            if path is not None:
                return path
    return None


def find_latest_15e_log(*, pdf_name: str, logs_dir: str | Path | None = None) -> Optional[Path]:
    base = _logs_dir(logs_dir)
    if not base.is_dir():
        return None
    for run_dir in sorted(base.glob("run_*"), reverse=True):
        if not _pdf_matches_run(run_dir, pdf_name):
            continue
        path = resolve_existing_artifact(run_dir, STAGE_15E)
        if path is not None:
            return path
    return None


def load_rewrite_sections_from_15d(
    ultimate_sections: Dict[str, Any],
    *,
    lines: Sequence[NormalizedLine],
) -> List[Dict[str, Any]]:
    """Flatten 15d sections + subheadings into ordered rewrite units with full span text."""
    line_text = _line_text_map(lines)
    units: List[Dict[str, Any]] = []

    for sec in ultimate_sections.get("sections") or []:
        heading = str(sec.get("heading") or "").strip()
        if not heading:
            continue
        subs = sec.get("subheadings") or []
        merged = _merge_section_body(sec, line_text)
        if len(merged) < 3 and not subs:
            continue
        sub_labels = _substantive_subheading_labels(subs)
        units.append(
            {
                "section_id": sec.get("section_id"),
                "heading": heading,
                "page_number": sec.get("page_number"),
                "line_id": sec.get("line_id"),
                "text": merged,
                "subheading_count": len(subs),
                "subheadings": sub_labels,
            }
        )
    units.sort(
        key=lambda s: (
            s.get("page_number") is None,
            s.get("page_number") or 0,
            s.get("line_id") or 0,
        )
    )
    return units


def load_rewrite_sections_from_15e(
    chapter_hierarchy: Dict[str, Any],
    *,
    lines: Sequence[NormalizedLine],
) -> List[Dict[str, Any]]:
    """Flatten 15e chapters into rewrite units with chapter metadata attached."""
    import copy

    from src.modules.structure.final_structuring.heading_cleanup import (
        disambiguate_duplicate_section_headings,
    )

    hierarchy = copy.deepcopy(chapter_hierarchy)
    chapters = list(hierarchy.get("chapters") or [])
    disambiguate_duplicate_section_headings(chapters)

    line_text = _line_text_map(lines)
    units: List[Dict[str, Any]] = []

    for chapter in chapters:
        chapter_id = chapter.get("chapter_id")
        chapter_heading = str(chapter.get("heading") or "").strip()
        for sec in chapter.get("sections") or []:
            heading = str(sec.get("heading") or "").strip()
            if not heading:
                continue
            subs = sec.get("subheadings") or []
            merged = _merge_section_body(sec, line_text)
            if len(merged) < 3 and not subs:
                continue
            sub_labels = _substantive_subheading_labels(subs)
            units.append(
                {
                    "section_id": sec.get("section_id"),
                    "heading": heading,
                    "page_number": sec.get("page_number"),
                    "line_id": sec.get("line_id"),
                    "text": merged,
                    "subheading_count": len(subs),
                    "subheadings": sub_labels,
                    "chapter_id": chapter_id,
                    "chapter_heading": chapter_heading,
                    "chapter_page_start": chapter.get("page_start"),
                }
            )
    units.sort(
        key=lambda s: (
            s.get("page_number") is None,
            s.get("page_number") or 0,
            s.get("line_id") or 0,
        )
    )
    return units


def load_chapter_tree(chapter_hierarchy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return chapter tree for hierarchical markdown export."""
    tree: List[Dict[str, Any]] = []
    for chapter in chapter_hierarchy.get("chapters") or []:
        tree.append(
            {
                "chapter_id": chapter.get("chapter_id"),
                "heading": chapter.get("heading"),
                "page_start": chapter.get("page_start"),
                "page_end": chapter.get("page_end"),
                "section_ids": [s.get("section_id") for s in chapter.get("sections") or []],
            }
        )
    return tree


def find_latest_15d_log(*, pdf_name: str, logs_dir: str | Path | None = None) -> Optional[Path]:
    base = _logs_dir(logs_dir)
    if not base.is_dir():
        return None
    for run_dir in sorted(base.glob("run_*"), reverse=True):
        if not _pdf_matches_run(run_dir, pdf_name):
            continue
        path = resolve_existing_artifact(run_dir, STAGE_15D)
        if path is not None:
            return path
    return None


def load_rewrite_sections(
    store: KnowledgeStore,
    *,
    book_id: str,
    pdf_path: Optional[str] = None,
    ultimate_sections_path: Optional[str | Path] = None,
    chapter_hierarchy_path: Optional[str | Path] = None,
    lines: Optional[Sequence[NormalizedLine]] = None,
    prefer_15e: bool = True,
    prefer_15d: bool = True,
) -> List[Dict[str, Any]]:
    """Load rewrite units; prefer stage 15e, then 15d, then legacy TOC."""
    if lines is not None:
        path_15e = Path(chapter_hierarchy_path) if chapter_hierarchy_path else None
        if path_15e is None and prefer_15e and pdf_path:
            path_15e = find_latest_hierarchy_log(pdf_name=Path(pdf_path).name)
        if prefer_15e and path_15e and path_15e.exists():
            hierarchy = load_chapter_hierarchy_json(path_15e)
            sections = load_rewrite_sections_from_15e(hierarchy, lines=lines)
            if sections:
                return sections

        path = Path(ultimate_sections_path) if ultimate_sections_path else None
        if prefer_15d and path is None and pdf_path:
            path = find_latest_15d_log(pdf_name=Path(pdf_path).name)
        if prefer_15d and path and path.exists():
            ultimate = load_ultimate_sections_json(path)
            sections = load_rewrite_sections_from_15d(ultimate, lines=lines)
            if sections:
                return sections

    return _load_rewrite_sections_legacy(store, book_id=book_id)


def _load_rewrite_sections_legacy(store: KnowledgeStore, *, book_id: str) -> List[Dict[str, Any]]:
    snap = TocRepository(store).get_book_toc(book_id=book_id) or {}
    headings = list(snap.get("headings") or [])
    fragments = snap.get("fragments") or {}
    sections: List[Dict[str, Any]] = []
    for h in headings:
        heading = str(h.get("text") or "").strip()
        if not heading:
            continue
        texts: List[str] = []
        for fid in h.get("fragment_ids") or []:
            frag = fragments.get(fid) or {}
            t = str(frag.get("text") or "").strip()
            if t:
                texts.append(t)
        body = "\n\n".join(texts).strip()
        if len(body) < 40:
            continue
        sections.append(
            {
                "heading": heading,
                "page_number": h.get("page_number"),
                "text": body,
            }
        )
    sections.sort(key=lambda s: (s.get("page_number") is None, s.get("page_number") or 0, s["heading"]))
    return sections
