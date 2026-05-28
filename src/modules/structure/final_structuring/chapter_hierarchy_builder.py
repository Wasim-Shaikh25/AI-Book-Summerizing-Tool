"""Stage 15e — build multi-level chapter → section → subheading hierarchy from 15d."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.shared import config

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"^\s*chapter\s+\d+", re.IGNORECASE)
_PART_RE = re.compile(r"^\s*part\s+[IVXLC\d]+", re.IGNORECASE)
_ROMAN_MAJOR_RE = re.compile(r"^\s*[IVXLC]+\.\s+[A-Z]")
_ARTICLES_RANGE_RE = re.compile(r"\(\s*(?:arts?\.?|articles?)\.?\s+\d+", re.IGNORECASE)
_MAJOR_CAPS_RE = re.compile(r"^[A-Z][A-Z\s\-–—,&()0-9]{12,}$")

_HIERARCHY_SYSTEM = """You organize law textbook sections into a clear chapter hierarchy.
Rules:
1) Group related consecutive sections under one chapter title.
2) Start a new chapter at major topic shifts (e.g. Preamble, Fundamental Rights, Directive Principles, Union, States).
3) Do NOT invent content; use concise chapter titles derived from section headings.
4) Every section_id must appear exactly once.
5) Preserve section order.

Reply JSON only:
{"assignments":[{"section_id":"S1","chapter_title":"Introductory","is_chapter_start":true}]}"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _looks_like_chapter_heading(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    if _CHAPTER_RE.match(t) or _PART_RE.match(t) or _ROMAN_MAJOR_RE.match(t):
        return True
    if _ARTICLES_RANGE_RE.search(t) and len(t) >= 20:
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters.isupper() and len(letters) >= 12 and len(t.split()) >= 2:
        return True
    if _MAJOR_CAPS_RE.match(t) and len(t.split()) >= 2:
        return True
    return False


def _rule_based_assignments(sections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic chapter boundaries from heading patterns."""
    assignments: List[Dict[str, Any]] = []
    current_title = "General"
    chapter_no = 0

    for sec in sections:
        sid = str(sec.get("section_id") or "")
        heading = _norm(str(sec.get("heading") or ""))
        is_start = False
        if _looks_like_chapter_heading(heading):
            chapter_no += 1
            current_title = heading[:120]
            is_start = True
        elif not assignments:
            chapter_no = 1
            current_title = heading[:120] or "Introduction"
            is_start = True
        assignments.append(
            {
                "section_id": sid,
                "chapter_title": current_title,
                "is_chapter_start": is_start,
                "method": "rule",
            }
        )
    return assignments


def _parse_assignments_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\"assignments\"[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    items = data.get("assignments")
    if not isinstance(items, list):
        return None
    out: List[Dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("section_id") or "").strip()
        title = _norm(str(row.get("chapter_title") or ""))
        if not sid or not title:
            continue
        out.append(
            {
                "section_id": sid,
                "chapter_title": title,
                "is_chapter_start": bool(row.get("is_chapter_start")),
                "method": "llm",
            }
        )
    return out or None


def _bigbird_refine_assignments(
    sections: Sequence[Dict[str, Any]],
    assignments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Use BigBird embeddings to split chapters when heading similarity drops."""
    try:
        from src.modules.structure.final_structuring.models.bigbird_encoder import get_bigbird_encoder

        enc = get_bigbird_encoder()
    except Exception:
        return assignments

    by_id = {str(a["section_id"]): a for a in assignments}
    anchor_emb = None
    anchor_title = ""
    refined: List[Dict[str, Any]] = []

    for sec in sections:
        sid = str(sec.get("section_id") or "")
        heading = _norm(str(sec.get("heading") or ""))
        row = dict(by_id.get(sid) or {"section_id": sid, "chapter_title": heading, "is_chapter_start": False, "method": "rule"})
        emb = enc.encode(heading)
        split = False
        if anchor_emb is not None and emb is not None:
            sim = float((anchor_emb * emb).sum())
            if sim < 0.52 and _looks_like_chapter_heading(heading):
                split = True
        if split or (anchor_emb is None and not refined):
            row["is_chapter_start"] = True
            row["chapter_title"] = heading[:120] or row.get("chapter_title") or "Section"
            row["method"] = "bigbird"
            anchor_emb = emb
            anchor_title = row["chapter_title"]
        else:
            row["is_chapter_start"] = False
            row["chapter_title"] = anchor_title or row.get("chapter_title") or heading[:120]
            if emb is not None and anchor_emb is None:
                anchor_emb = emb
                anchor_title = row["chapter_title"]
        refined.append(row)
    return refined


def _llm_assignments_for_batch(
    client: Any,
    batch: Sequence[Dict[str, Any]],
    *,
    prior_chapters: List[str],
) -> Optional[List[Dict[str, Any]]]:
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    compact = [
        {
            "section_id": s.get("section_id"),
            "heading": _norm(str(s.get("heading") or ""))[:140],
            "page": s.get("page_number"),
            "subheadings": len(s.get("subheadings") or []),
        }
        for s in batch
    ]
    user = json.dumps({"prior_chapters": prior_chapters[-8:], "sections": compact}, ensure_ascii=False)
    provider = normalize_chat_provider(config.CHAPTER_HIERARCHY_LLM or config.LLM_PROVIDER or "openai")
    raw = client.chat_with_provider(provider, system=_HIERARCHY_SYSTEM, user=user, max_tokens=2048)
    parsed = _parse_assignments_json(raw or "")
    if not parsed:
        return None
    expected = {str(s.get("section_id")) for s in batch}
    got = {str(r["section_id"]) for r in parsed}
    if expected != got:
        logger.warning("15e LLM batch mismatch expected=%s got=%s", len(expected), len(got))
        return None
    return parsed


def _llm_assignments(
    sections: Sequence[Dict[str, Any]],
    *,
    batch_size: int,
) -> Optional[List[Dict[str, Any]]]:
    from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider

    if not sections:
        return []
    client = LlmChatClient.from_config(temperature=0.1)
    provider = normalize_chat_provider(config.CHAPTER_HIERARCHY_LLM or config.LLM_PROVIDER or "openai")
    if provider not in {"openai", "gemini", "ollama", "llamacpp"}:
        return None

    merged: List[Dict[str, Any]] = []
    prior_titles: List[str] = []
    for start in range(0, len(sections), batch_size):
        batch = sections[start : start + batch_size]
        parsed = _llm_assignments_for_batch(client, batch, prior_chapters=prior_titles)
        if not parsed:
            rule_batch = _rule_based_assignments(batch)
            merged.extend(rule_batch)
            for row in rule_batch:
                if row.get("is_chapter_start"):
                    prior_titles.append(str(row["chapter_title"]))
            continue
        merged.extend(parsed)
        for row in parsed:
            if row.get("is_chapter_start"):
                prior_titles.append(str(row["chapter_title"]))
    return merged


def _assignments_to_chapters(
    sections: Sequence[Dict[str, Any]],
    assignments: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sec_by_id = {str(s.get("section_id")): s for s in sections}
    chapters: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    chap_no = 0

    for row in assignments:
        sid = str(row.get("section_id") or "")
        sec = sec_by_id.get(sid)
        if sec is None:
            continue
        title = _norm(str(row.get("chapter_title") or sec.get("heading") or "Section"))
        is_start = bool(row.get("is_chapter_start")) or current is None
        if is_start or current is None:
            chap_no += 1
            pages = [sec.get("page_number")] if sec.get("page_number") is not None else []
            current = {
                "chapter_id": f"C{chap_no}",
                "heading": title,
                "level": 1,
                "page_start": sec.get("page_number"),
                "page_end": sec.get("page_number"),
                "sections": [],
                "assignment_method": row.get("method") or "rule",
            }
            chapters.append(current)
        sec_copy = dict(sec)
        sec_copy["level"] = 2
        subs = []
        for j, sub in enumerate(sec.get("subheadings") or [], start=1):
            subs.append({**sub, "level": 3, "topic_id": f"{sid}_T{j}"})
        sec_copy["subheadings"] = subs
        sec_copy["topic_id"] = f"{sid}_main"
        current["sections"].append(sec_copy)
        if sec.get("page_number") is not None:
            pg = int(sec["page_number"])
            if current.get("page_start") is None:
                current["page_start"] = pg
            current["page_end"] = pg
    return chapters


def _consolidate_chapters(chapters: List[Dict[str, Any]], *, min_sections: int = 6) -> List[Dict[str, Any]]:
    """Merge tiny consecutive chapters so TOC/body are not fragmented."""
    if min_sections <= 1 or len(chapters) <= 1:
        return chapters
    merged: List[Dict[str, Any]] = []
    bucket: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        nonlocal bucket
        if bucket is not None:
            merged.append(bucket)
            bucket = None

    for ch in chapters:
        secs = list(ch.get("sections") or [])
        if bucket is None:
            bucket = {**ch, "sections": list(secs)}
            continue
        if len(bucket.get("sections") or []) >= min_sections:
            _flush()
            bucket = {**ch, "sections": list(secs)}
            continue
        bucket["sections"].extend(secs)
        if ch.get("page_end") is not None:
            bucket["page_end"] = ch.get("page_end")
    _flush()
    for i, ch in enumerate(merged, start=1):
        ch["chapter_id"] = f"C{i}"
    return merged


def build_chapter_hierarchy(
    *,
    ultimate_sections: Dict[str, Any],
    hierarchy: Optional[Sequence[Dict[str, Any]]] = None,
    max_sections: int = 0,
) -> Dict[str, Any]:
    """Stage 15e — chapters (L1) → sections (L2) → subheadings (L3)."""
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    sections = list(ultimate_sections.get("sections") or [])
    if max_sections > 0:
        sections = sections[:max_sections]

    use_llm = os.environ.get("CHAPTER_HIERARCHY_USE_LLM", getattr(config, "CHAPTER_HIERARCHY_USE_LLM", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "n",
    }
    use_bigbird = str(getattr(config, "CHAPTER_HIERARCHY_USE_BIGBIRD", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "n",
    }
    batch_size = int(getattr(config, "CHAPTER_HIERARCHY_BATCH_SIZE", 25) or 25)

    method = "rule"
    assignments = _rule_based_assignments(sections)

    if use_llm and sections:
        llm_rows = _llm_assignments(sections, batch_size=batch_size)
        if llm_rows:
            assignments = llm_rows
            method = "llm"
        else:
            logger.info("15e LLM assignment failed; using rule-based fallback")

    if use_bigbird and method != "llm":
        assignments = _bigbird_refine_assignments(sections, assignments)
        if any(a.get("method") == "bigbird" for a in assignments):
            method = "bigbird" if method == "rule" else f"{method}+bigbird"

    chapters = _assignments_to_chapters(sections, assignments)
    min_per = int(getattr(config, "CHAPTER_HIERARCHY_MIN_SECTIONS_PER_CHAPTER", 6) or 6)
    chapters = _consolidate_chapters(chapters, min_sections=min_per)
    topic_count = sum(
        1 + len(s.get("subheadings") or []) for ch in chapters for s in ch.get("sections") or []
    )

    return {
        "meta": {
            "strategy": "chapter_section_subheading",
            "assignment_method": method,
            "input_section_count": len(ultimate_sections.get("sections") or []),
            "processed_section_count": len(sections),
            "total_chapters": len(chapters),
            "total_sections": sum(len(c.get("sections") or []) for c in chapters),
            "total_topics": topic_count,
            "levels": 3,
            "llm_provider": normalize_chat_provider(config.CHAPTER_HIERARCHY_LLM or config.LLM_PROVIDER or ""),
            "batch_size": batch_size,
        },
        "chapters": chapters,
        "section_assignments": assignments,
    }
