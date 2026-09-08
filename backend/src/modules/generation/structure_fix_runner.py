"""Pipeline integration for post-export notes structural cleanup.

Shared by ``scripts/fix_notes_structure.py`` and ``run_full_openai_pipeline.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from src.modules.generation.notes_structure_fix import FixReport, fix_notes_markdown


def structure_fix_enabled() -> bool:
    from src.shared import config

    return bool(getattr(config, "NOTES_STRUCTURE_FIX_ENABLED", True))


def resolve_structure_fix_engine(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip().lower()
    from src.shared import config

    raw = str(getattr(config, "NOTES_STRUCTURE_FIX_ENGINE", "hybrid") or "hybrid").strip().lower()
    if raw in {"hybrid", "minilm", "api"}:
        return raw
    return "hybrid"


def structure_fix_merge_duplicates() -> bool:
    from src.shared import config

    return bool(getattr(config, "NOTES_STRUCTURE_FIX_MERGE_DUPLICATES", False))


def structure_fix_drop_low_grounding() -> bool:
    from src.shared import config

    return bool(getattr(config, "NOTES_STRUCTURE_FIX_DROP_LOW_GROUNDING", False))


def _load_json(path: Path) -> Any:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return data


def build_source_by_id_from_log_dir(log_dir: Path) -> Dict[str, str]:
    """Reconstruct per-section source text from a pipeline log directory."""
    from src.modules.generation.toc_sections import (
        build_source_text_by_id,
        line_text_map_from_records,
    )
    from src.modules.pipeline.stage_registry import (
        require_artifact,
        resolve_chapter_hierarchy_artifact,
    )

    hierarchy_path = resolve_chapter_hierarchy_artifact(log_dir)
    if not hierarchy_path:
        return {}
    hierarchy_data = _load_json(hierarchy_path)
    layout_records = _load_json(require_artifact(log_dir, "layout_lines"))
    if isinstance(layout_records, dict):
        layout_records = layout_records.get("items") or layout_records.get("lines") or []
    line_text_by_id = line_text_map_from_records(layout_records or [])
    if not line_text_by_id:
        return {}
    return build_source_text_by_id(hierarchy_data, line_text_by_id)


def build_structure_fix_chat(
    engine: str,
) -> Tuple[Optional[Callable[[str, str, int], Optional[str]]], str]:
    """Return ``(chat_callable, model_label)``. ``chat`` is None when offline."""
    if engine == "minilm":
        return None, "offline"
    from src.modules.pipeline.llm_chat_client import LlmChatClient

    client = LlmChatClient.from_config()
    if not client.chat_enabled:
        return None, "offline"

    def chat(system: str, user: str, max_tokens: int) -> Optional[str]:
        return client.chat(system=system, user=user, max_tokens=max_tokens)

    return chat, client.last_model_label() or client.provider


def run_structure_fix(
    md_text: str,
    *,
    log_dir: Optional[Path] = None,
    engine: Optional[str] = None,
    merge_duplicates: Optional[bool] = None,
    drop_low_grounding: Optional[bool] = None,
) -> Tuple[str, FixReport]:
    """Apply structural fixes to assembled notes Markdown."""
    resolved_engine = resolve_structure_fix_engine(engine)
    merge = structure_fix_merge_duplicates() if merge_duplicates is None else merge_duplicates
    drop = structure_fix_drop_low_grounding() if drop_low_grounding is None else drop_low_grounding

    source_by_id: Dict[str, str] = {}
    if log_dir and log_dir.exists():
        try:
            source_by_id = build_source_by_id_from_log_dir(log_dir)
        except Exception:
            source_by_id = {}

    chat, model_label = build_structure_fix_chat(resolved_engine)
    return fix_notes_markdown(
        md_text,
        engine=resolved_engine,
        chat=chat,
        heading_model=model_label,
        source_by_id=source_by_id,
        merge_duplicates_apply=merge,
        drop_low_grounding=drop and bool(source_by_id),
    )


def write_structure_fix_report(report: FixReport, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_title_maps(
    fixed_md: str,
) -> Tuple[Dict[str, str], Dict[str, str], list[str]]:
    """Derive the authoritative titles from the final notes Markdown.

    Returns ``(section_title_by_sid, chapter_title_by_sid, chapter_titles_in_order)``.
    The Markdown is the single source of truth the user sees, so its (display-
    resolved + structurally repaired) titles are what DOCX and the audit must use.
    """
    from src.modules.generation.notes_structure_fix import parse_notes_md

    doc = parse_notes_md(fixed_md)
    section_title_by_sid: Dict[str, str] = {}
    chapter_title_by_sid: Dict[str, str] = {}
    chapter_titles_in_order: list[str] = []
    for ch in doc.chapters:
        chapter_titles_in_order.append(ch.title)
        for sec in ch.sections:
            if sec.dropped or not sec.sid:
                continue
            section_title_by_sid[sec.sid] = sec.title
            if ch.title:
                chapter_title_by_sid[sec.sid] = ch.title
    return section_title_by_sid, chapter_title_by_sid, chapter_titles_in_order


def _apply_titles_to_hierarchy(
    hierarchy: Dict[str, Any],
    section_title_by_sid: Dict[str, str],
    chapter_title_by_sid: Dict[str, str],
    chapter_titles_in_order: list[str],
) -> int:
    """Patch a hierarchy dict's section/chapter headings in place. Returns count.

    Sections match by ``section_id`` (stable). Chapters match by majority vote of
    their sections' Markdown chapter, falling back to positional order — this is
    robust to refine-stage reordering between the in-memory and on-disk hierarchies.
    """
    updated = 0
    chapters = hierarchy.get("chapters") or []
    for idx, ch in enumerate(chapters):
        ch_vote: Dict[str, int] = {}
        sid_seen = False
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            if sid:
                sid_seen = True
            new = section_title_by_sid.get(sid)
            if new and new != str(sec.get("heading") or "").strip():
                sec["heading"] = new
                updated += 1
            voted = chapter_title_by_sid.get(sid)
            if voted:
                ch_vote[voted] = ch_vote.get(voted, 0) + 1
        new_ch = None
        if ch_vote:
            new_ch = max(ch_vote, key=lambda k: ch_vote[k])
        elif not sid_seen and idx < len(chapter_titles_in_order):
            # No sid signal at all for this chapter — fall back to position.
            new_ch = chapter_titles_in_order[idx]
        if new_ch and new_ch != str(ch.get("heading") or "").strip():
            ch["heading"] = new_ch
            updated += 1
    return updated


def sync_hierarchy_from_markdown(
    md_path: "Path",
    hierarchy: Dict[str, Any],
    *,
    write_path: Optional["Path"] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Rebuild hierarchy headings and section order from the final Markdown file.

    This is a superset of ``propagate_titles_to_hierarchy``: it also reorders
    sections within each chapter to match the Markdown display sequence and does
    not require a FixReport — it reads the MD directly.

    Args:
        md_path:    Path to the ``.md`` notes file (the user-visible source of truth).
        hierarchy:  The loaded hierarchy dict (mutated in-place and returned).
        write_path: When provided, write the patched hierarchy as JSON here
                    (new ``s15k_synced_hierarchy.json`` artifact).

    Returns:
        ``(hierarchy, sync_report)`` where ``sync_report`` has keys:
            ``patched``  — number of section/chapter headings changed.
            ``skipped``  — number of sids in Markdown not found in hierarchy.
            ``warnings`` — list of human-readable warning strings.
    """
    from src.modules.generation.notes_structure_fix import parse_notes_md

    md_text = Path(md_path).read_text(encoding="utf-8")
    doc = parse_notes_md(md_text)

    # Build sid → (chapter_title, section_title, order_within_chapter) map.
    sid_to_info: Dict[str, Dict[str, Any]] = {}
    for ch in doc.chapters:
        for order, sec in enumerate(ch.sections):
            if getattr(sec, "dropped", False) or not getattr(sec, "sid", ""):
                continue
            sid_to_info[sec.sid] = {
                "section_heading": sec.title,
                "chapter_heading": ch.title,
                "order": order,
            }

    patched = 0
    skipped = 0
    warnings: list[str] = []

    chapters = hierarchy.get("chapters") or []
    for ch in chapters:
        sections = ch.get("sections") or []
        ch_vote: Dict[str, int] = {}

        for sec in sections:
            sid = str(sec.get("section_id") or "")
            if not sid:
                continue
            info = sid_to_info.get(sid)
            if info is None:
                skipped += 1
                warnings.append(
                    f"sid '{sid}' referenced in hierarchy not found in Markdown — skipped"
                )
                continue
            new_heading = info["section_heading"]
            if new_heading and new_heading != str(sec.get("heading") or "").strip():
                sec["heading"] = new_heading
                patched += 1
            ch_title = info.get("chapter_heading")
            if ch_title:
                ch_vote[ch_title] = ch_vote.get(ch_title, 0) + 1

        def _section_order(s: Dict[str, Any]) -> int:
            info = sid_to_info.get(str(s.get("section_id") or ""))
            return int(info["order"]) if info else 9999

        ch["sections"] = sorted(sections, key=_section_order)

        if ch_vote:
            new_ch = max(ch_vote, key=lambda k: ch_vote[k])
            if new_ch and new_ch != str(ch.get("heading") or "").strip():
                ch["heading"] = new_ch
                patched += 1

    if write_path is not None:
        write_path = Path(write_path)
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(
            json.dumps(hierarchy, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return hierarchy, {"patched": patched, "skipped": skipped, "warnings": warnings}


def propagate_titles_to_hierarchy(
    fixed_md: str,
    hierarchy: Optional[Dict[str, Any]],
    *,
    hierarchy_path: Optional[Path] = None,
) -> int:
    """Sync final Markdown titles into the hierarchy used by DOCX export and audit.

    Without this, DOCX renders raw ``hierarchy['...']['heading']`` and the audit's
    AC-04 reads the on-disk hierarchy artifact — both bypass the cleaned Markdown,
    so repaired/display-resolved titles never reach them. Updates the in-memory
    ``hierarchy`` (DOCX) and rewrites ``hierarchy_path`` (audit) when provided.
    """
    if not fixed_md:
        return 0
    section_map, chapter_map, chapter_order = _build_title_maps(fixed_md)
    if not section_map and not chapter_order:
        return 0

    mem_updated = 0
    if hierarchy and hierarchy.get("chapters"):
        mem_updated = _apply_titles_to_hierarchy(
            hierarchy, section_map, chapter_map, chapter_order
        )

    disk_updated = 0
    if hierarchy_path and hierarchy_path.exists():
        try:
            disk = json.loads(hierarchy_path.read_text(encoding="utf-8"))
            if isinstance(disk, dict) and disk.get("chapters"):
                disk_updated = _apply_titles_to_hierarchy(
                    disk, section_map, chapter_map, chapter_order
                )
                hierarchy_path.write_text(
                    json.dumps(disk, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    # In-memory (DOCX) and on-disk (audit) hierarchies can differ (refine stage),
    # so report whichever needed more syncing to keep the log meaningful.
    return max(mem_updated, disk_updated)
