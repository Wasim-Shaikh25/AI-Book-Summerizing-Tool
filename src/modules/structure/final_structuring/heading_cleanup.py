"""Stage 15f — normalize weak section/chapter headings via rules + optional LLM."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.shared import config
from src.modules.generation.rewrite_validation import is_weak_section_heading

logger = logging.getLogger(__name__)

_CLEANUP_SYSTEM = """You clean up law textbook section and chapter titles for study notes.
Rules:
1) Replace PDF fragments with clear study titles (e.g. "(Art. 21)" -> "Article 21 — Right to Life").
2) Remove bare list markers like "(ii)", "1.", "1950." when preview/context supports a proper topic name.
3) Disambiguate duplicate chapter titles using the topic focus from sample_sections (avoid generic "Part I/II").
4) Keep Article references when useful: prefer "Equality before the law (Art. 14)" over "(Art. 14)" alone.
5) Max 120 characters; do not invent legal facts beyond the preview/context given.
6) Return every item id you receive; do not skip or add ids.

Reply JSON only:
{"sections":[{"section_id":"S1","heading":"..."}],"subheadings":[{"section_id":"S1","line_id":42,"heading":"..."}],"chapters":[{"chapter_id":"C8","heading":"..."}]}"""

_ART_ONLY = re.compile(r"^\(\s*(?:arts?\.?|articles?\.?)\s*([^)]+)\)\s*$", re.I)
_NUM_PREFIX = re.compile(r"^\d+\.\s+")
_YEAR_ART = re.compile(r"^\d{4}\.\s*\(\s*(?:art|arts)", re.I)
_ROMAN_FRAGMENT = re.compile(r"^\([ivxlc]+\)$", re.I)
_PAREN_ONLY = re.compile(r"^\(\w+\)$", re.I)
_TRAILING_HYPHEN = re.compile(r"\s+in-\s*$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _preview_text(row: Dict[str, Any]) -> str:
    frag = row.get("fragment") or {}
    return _norm(str(frag.get("preview") or ""))[:240]


def _rule_clean_heading(
    heading: str,
    *,
    preview: str = "",
    subheadings: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Deterministic heading cleanup before/alongside LLM."""
    h = _norm(heading)
    if not h:
        return h

    m = _ART_ONLY.match(h)
    if m:
        arts = m.group(1).strip()
        arts = re.sub(r"^(?:arts?\.?|articles?\.?)\s*", "", arts, flags=re.I).strip()
        return f"Article {arts}"[:120]

    if _YEAR_ART.match(h):
        rest = h.split(".", 1)[-1].strip()
        if rest:
            return f"Citizenship {rest}"[:120]

    if _NUM_PREFIX.match(h):
        stripped = _NUM_PREFIX.sub("", h, count=1).strip()
        if stripped and not is_weak_section_heading(stripped):
            return stripped[:120]

    if _PAREN_ONLY.match(h) or _ROMAN_FRAGMENT.match(h):
        for sub in subheadings or []:
            sh = _norm(str(sub.get("heading") or ""))
            if sh and not is_weak_section_heading(sh):
                return sh[:120]
        if preview:
            first = re.split(r"[.\n]", preview)[0].strip()
            if 12 <= len(first) <= 100:
                return first[:120]

    if h.endswith("-") or _TRAILING_HYPHEN.search(h):
        if preview:
            extra = preview.split()[0] if preview.split() else ""
            if extra:
                combined = _norm(h.rstrip("- ") + " " + extra)
                if len(combined) > len(h):
                    return combined[:120]

    return h


def _duplicate_chapter_names(chapters: Sequence[Dict[str, Any]]) -> Set[str]:
    names = [_norm(str(c.get("heading") or "")) for c in chapters if _norm(str(c.get("heading") or ""))]
    return {n for n, count in Counter(names).items() if count > 1}


def _needs_chapter_cleanup(chapter: Dict[str, Any], *, duplicate_names: Set[str]) -> bool:
    name = _norm(str(chapter.get("heading") or ""))
    if not name:
        return False
    if name in duplicate_names:
        return True
    if name.lower().startswith("its "):
        return True
    if len(name) < 12 and not re.search(r"\(\s*art", name, re.I):
        return True
    return False


def _rule_dedupe_chapter_title(name: str, chapter: Dict[str, Any], occurrence: int) -> str:
    pg = chapter.get("page_start")
    if occurrence > 1 and pg is not None:
        return f"{name} (p. {pg})"[:120]
    return name


def _apply_rule_pass(chapters: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """Rule cleanup on all headings; returns (sections, subheadings, chapters) changed."""
    dupes = _duplicate_chapter_names(chapters)
    sec_changed = sub_changed = ch_changed = 0
    seen_chapter_name: Dict[str, int] = {}

    for ch in chapters:
        ch_name = _norm(str(ch.get("heading") or ""))
        if ch_name:
            seen_chapter_name[ch_name] = seen_chapter_name.get(ch_name, 0) + 1
        if ch_name in dupes:
            new_name = _rule_dedupe_chapter_title(ch_name, ch, seen_chapter_name.get(ch_name, 1))
            if new_name != ch_name:
                ch["heading"] = new_name
                ch_changed += 1

        for sec in ch.get("sections") or []:
            heading = _norm(str(sec.get("heading") or ""))
            preview = _preview_text(sec)
            subs = list(sec.get("subheadings") or [])
            cleaned = _rule_clean_heading(heading, preview=preview, subheadings=subs)
            if cleaned != heading:
                sec["heading"] = cleaned
                sec_changed += 1
                heading = cleaned

            for sub in subs:
                sub_h = _norm(str(sub.get("heading") or ""))
                sub_preview = _preview_text(sub)
                sub_clean = _rule_clean_heading(sub_h, preview=sub_preview)
                if sub_clean != sub_h:
                    sub["heading"] = sub_clean
                    sub_changed += 1

    return sec_changed, sub_changed, ch_changed


def _collect_llm_candidates(chapters: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    dupes = _duplicate_chapter_names(chapters)
    section_items: List[Dict[str, Any]] = []
    sub_items: List[Dict[str, Any]] = []
    chapter_items: List[Dict[str, Any]] = []
    chapter_seen: Dict[str, int] = {}

    for ch in chapters:
        cid = str(ch.get("chapter_id") or "")
        ch_name = _norm(str(ch.get("heading") or ""))
        if ch_name:
            chapter_seen[ch_name] = chapter_seen.get(ch_name, 0) + 1

        if _needs_chapter_cleanup(ch, duplicate_names=dupes):
            secs = ch.get("sections") or []
            samples = [
                _norm(str(s.get("heading") or ""))[:70]
                for s in secs[:6]
                if _norm(str(s.get("heading") or ""))
            ]
            chapter_items.append(
                {
                    "chapter_id": cid,
                    "heading": ch_name,
                    "page_start": ch.get("page_start"),
                    "occurrence": chapter_seen.get(ch_name, 1),
                    "sample_sections": samples,
                }
            )

        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            heading = _norm(str(sec.get("heading") or ""))
            if is_weak_section_heading(heading):
                section_items.append(
                    {
                        "section_id": sid,
                        "chapter_heading": ch_name,
                        "heading": heading,
                        "page": sec.get("page_number"),
                        "preview": _preview_text(sec)[:200],
                        "subheadings": [
                            _norm(str(s.get("heading") or ""))[:80]
                            for s in (sec.get("subheadings") or [])[:4]
                            if _norm(str(s.get("heading") or ""))
                        ],
                    }
                )

            for sub in sec.get("subheadings") or []:
                sub_h = _norm(str(sub.get("heading") or ""))
                if is_weak_section_heading(sub_h):
                    sub_items.append(
                        {
                            "section_id": sid,
                            "line_id": sub.get("line_id"),
                            "parent_heading": heading,
                            "heading": sub_h,
                            "preview": _preview_text(sub)[:160],
                        }
                    )

    return section_items, sub_items, chapter_items


def _parse_cleanup_json(raw: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not raw:
        return None
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\"sections\"[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key in ("sections", "subheadings", "chapters"):
        rows = data.get(key)
        if not isinstance(rows, list):
            out[key] = []
            continue
        cleaned: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            heading = _norm(str(row.get("heading") or ""))
            if not heading or is_weak_section_heading(heading):
                continue
            cleaned.append({**row, "heading": heading[:120]})
        out[key] = cleaned
    return out


def _llm_cleanup_batch(
    client: Any,
    *,
    sections: Sequence[Dict[str, Any]],
    subheadings: Sequence[Dict[str, Any]],
    chapters: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    if not sections and not subheadings and not chapters:
        return {"sections": [], "subheadings": [], "chapters": []}

    user = json.dumps(
        {"sections": list(sections), "subheadings": list(subheadings), "chapters": list(chapters)},
        ensure_ascii=False,
    )
    provider = normalize_chat_provider(config.HEADING_CLEANUP_LLM or config.LLM_PROVIDER or "openai")
    raw = client.chat_with_provider(provider, system=_CLEANUP_SYSTEM, user=user, max_tokens=4096)
    parsed = _parse_cleanup_json(raw or "")
    if not parsed:
        return None

    expected_sids = {str(s["section_id"]) for s in sections}
    got_sids = {str(r["section_id"]) for r in parsed.get("sections") or []}
    if expected_sids and expected_sids != got_sids:
        logger.warning("15f LLM section batch mismatch expected=%s got=%s", len(expected_sids), len(got_sids))
        return None

    expected_ch = {str(c["chapter_id"]) for c in chapters}
    got_ch = {str(r["chapter_id"]) for r in parsed.get("chapters") or []}
    if expected_ch and expected_ch != got_ch:
        logger.warning("15f LLM chapter batch mismatch expected=%s got=%s", len(expected_ch), len(got_ch))
        return None

    return parsed


def _apply_llm_results(chapters: List[Dict[str, Any]], parsed: Dict[str, List[Dict[str, Any]]]) -> Tuple[int, int, int]:
    sec_map = {str(r["section_id"]): r["heading"] for r in parsed.get("sections") or []}
    ch_map = {str(r["chapter_id"]): r["heading"] for r in parsed.get("chapters") or []}
    sub_map: Dict[Tuple[str, Any], str] = {}
    for row in parsed.get("subheadings") or []:
        key = (str(row.get("section_id") or ""), row.get("line_id"))
        sub_map[key] = str(row.get("heading") or "")

    sec_changed = sub_changed = ch_changed = 0
    for ch in chapters:
        cid = str(ch.get("chapter_id") or "")
        if cid in ch_map:
            ch["heading"] = ch_map[cid]
            ch_changed += 1
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            if sid in sec_map:
                sec["heading"] = sec_map[sid]
                sec_changed += 1
            for sub in sec.get("subheadings") or []:
                key = (sid, sub.get("line_id"))
                if key in sub_map:
                    sub["heading"] = sub_map[key]
                    sub_changed += 1
    return sec_changed, sub_changed, ch_changed


def _llm_cleanup(
    chapters: List[Dict[str, Any]],
    *,
    batch_size: int,
) -> Tuple[str, int, int, int]:
    from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider

    section_items, sub_items, chapter_items = _collect_llm_candidates(chapters)
    if not section_items and not sub_items and not chapter_items:
        return "rule_only", 0, 0, 0

    provider = normalize_chat_provider(config.HEADING_CLEANUP_LLM or config.LLM_PROVIDER or "openai")
    if provider not in {"openai", "gemini", "ollama", "llamacpp"}:
        return "rule_only", 0, 0, 0

    subs_by_sid: Dict[str, List[Dict[str, Any]]] = {}
    for row in sub_items:
        subs_by_sid.setdefault(str(row.get("section_id") or ""), []).append(row)

    batches: List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = []
    if section_items:
        for start in range(0, len(section_items), batch_size):
            sec_batch = section_items[start : start + batch_size]
            sub_batch: List[Dict[str, Any]] = []
            for sec in sec_batch:
                sub_batch.extend(subs_by_sid.get(str(sec.get("section_id") or ""), []))
            batches.append((sec_batch, sub_batch))
    elif sub_items or chapter_items:
        batches.append(([], sub_items[:batch_size]))

    client = LlmChatClient.from_config(temperature=0.1)
    total_sec = total_sub = total_ch = 0
    method = "llm"
    had_failure = False

    for i, (sec_batch, sub_batch) in enumerate(batches):
        parsed = _llm_cleanup_batch(
            client,
            sections=sec_batch,
            subheadings=sub_batch,
            chapters=chapter_items if i == 0 else [],
        )
        if not parsed:
            logger.info("15f LLM batch %s failed; keeping rule-cleaned titles", i)
            had_failure = True
            continue
        s, sh, c = _apply_llm_results(chapters, parsed)
        total_sec += s
        total_sub += sh
        total_ch += c

    if had_failure and (total_sec or total_sub or total_ch):
        method = "rule+llm_partial"
    elif had_failure:
        method = "rule"

    return method, total_sec, total_sub, total_ch


def clean_heading_hierarchy(
    chapter_hierarchy: Dict[str, Any],
    *,
    use_llm: Optional[bool] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Stage 15f — return a copy of hierarchy with cleaned section/chapter headings."""
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out

    if use_llm is None:
        use_llm = os.environ.get("HEADING_CLEANUP_USE_LLM", getattr(config, "HEADING_CLEANUP_USE_LLM", "1")).strip().lower() not in {
            "0",
            "false",
            "no",
            "n",
        }
    bs = int(batch_size or getattr(config, "HEADING_CLEANUP_BATCH_SIZE", 20) or 20)

    rule_sec, rule_sub, rule_ch = _apply_rule_pass(chapters)
    method = "rule"
    llm_sec = llm_sub = llm_ch = 0

    if use_llm:
        llm_method, llm_sec, llm_sub, llm_ch = _llm_cleanup(chapters, batch_size=bs)
        if llm_method != "rule_only":
            method = llm_method

    weak_after = sum(
        1
        for ch in chapters
        for sec in ch.get("sections") or []
        if is_weak_section_heading(str(sec.get("heading") or ""))
    )
    dup_after = list(_duplicate_chapter_names(chapters))

    meta = dict(out.get("meta") or {})
    meta.update(
        {
            "heading_cleanup_method": method,
            "heading_cleanup_rule_sections": rule_sec,
            "heading_cleanup_rule_subheadings": rule_sub,
            "heading_cleanup_rule_chapters": rule_ch,
            "heading_cleanup_llm_sections": llm_sec,
            "heading_cleanup_llm_subheadings": llm_sub,
            "heading_cleanup_llm_chapters": llm_ch,
            "weak_section_headings_after": weak_after,
            "duplicate_chapter_names_after": dup_after,
            "heading_cleanup_llm_provider": normalize_chat_provider(
                config.HEADING_CLEANUP_LLM or config.LLM_PROVIDER or ""
            ),
            "heading_cleanup_batch_size": bs,
        }
    )
    out["meta"] = meta
    out["chapters"] = chapters
    return out
