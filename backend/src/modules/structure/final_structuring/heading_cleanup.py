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
from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.dropped_heading_registry import (
    DroppedHeadingRegistry,
    case_hint_from_preview,
    is_sentence_like_title,
    title_from_subheadings,
)

logger = logging.getLogger(__name__)

_CLEANUP_SYSTEM = """You clean up academic textbook section and chapter titles for study notes.
Rules:
1) Replace PDF fragments with clear study titles using subheadings and chapter context — never copy body preview prose.
2) Remove bare list markers like "(ii)", "1.", "1950." by picking a valid subheading title when provided.
3) Disambiguate duplicate chapter titles using sample_sections (avoid generic "Part I/II").
4) Keep numbered references (articles, sections, chapters) when useful and supported by context.
5) Max 120 characters; do not invent facts beyond the subheadings/context given.
6) Return every item id you receive; do not skip or add ids.
7) Never use sentence-like body text as a title.

Reply JSON only:
{"sections":[{"section_id":"S1","heading":"..."}],"subheadings":[{"section_id":"S1","line_id":42,"heading":"..."}],"chapters":[{"chapter_id":"C8","heading":"..."}]}"""

_ART_ONLY = re.compile(r"^\(\s*(?:arts?\.?|articles?\.?)\s*([^)]+)\)\s*$", re.I)
_NUM_PREFIX = re.compile(r"^\d+\.\s+")
_YEAR_ART = re.compile(r"^\d{4}\.\s*\(\s*(?:art|arts)", re.I)
_ROMAN_FRAGMENT = re.compile(r"^\([ivxlc]+\)$", re.I)
_PAREN_ONLY = re.compile(r"^\(\w+\)$", re.I)
_TRAILING_HYPHEN = re.compile(r"\s+in-\s*$", re.I)
_GENERIC_DISAMBIG_BASES = frozenset(
    {
        "illustration",
        "illustrations",
        "explanation",
        "classification",
        "section",
        "note",
        "notes",
        "definition",
        "definitions",
        "example",
        "examples",
    }
)
_ILLUSTRATION_HEADING_RE = re.compile(r"^illustrations?$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _preview_text(row: Dict[str, Any]) -> str:
    frag = row.get("fragment") or {}
    return _norm(str(frag.get("preview") or ""))[:240]


def _strip_page_disambiguation_suffixes(heading: str) -> str:
    """Remove PDF merge tails like ' — Book (p. 12) — Book (p. 12)' from any heading."""
    h = _norm(heading)
    if not h:
        return h
    h = re.sub(r"\s*\(p\.\s*\d+\)\s*$", "", h, flags=re.I).strip()
    if not h or not _MERGE_SUFFIX.search(h):
        return h[:120]
    changed = True
    while changed and _MERGE_SUFFIX.search(h):
        changed = False
        base, suffix = re.split(r"\s+[—–-]\s+", h, maxsplit=1)
        base = base.strip().rstrip(":").strip()
        suffix = (suffix or "").strip()
        if not base or not suffix:
            break
        if _PAGE_REF_IN_TEXT.search(suffix):
            h = base
            changed = True
            continue
        suffix_parts = re.split(r"\s+[—–-]\s+", suffix)
        if len(suffix_parts) >= 2:
            norms = [_norm(p) for p in suffix_parts if _norm(p)]
            if len(norms) >= 2 and (
                len(set(norms)) == 1 or norms[0][:24] == norms[-1][:24]
            ):
                h = base
                changed = True
                continue
        break
    return h[:120]


def canonical_heading_for_match(heading: str) -> str:
    """Normalize a heading for fuzzy matching (rules only, no book-specific aliases)."""
    cleaned = _rule_clean_heading(heading)
    return normalize_heading(cleaned or heading)


def sanitize_hierarchy_headings(hierarchy: Dict[str, Any]) -> int:
    """Apply rule-based page-hint / merge-tail cleanup to all chapter and section headings."""
    changed = 0
    for ch in hierarchy.get("chapters") or []:
        old_ch = _norm(str(ch.get("heading") or ""))
        if old_ch:
            new_ch = _rule_clean_heading(old_ch)
            if new_ch and new_ch != old_ch:
                ch["heading"] = new_ch[:120]
                changed += 1
        for sec in ch.get("sections") or []:
            old = _norm(str(sec.get("heading") or ""))
            if not old:
                continue
            new = _rule_clean_heading(
                old,
                preview=_preview_text(sec),
                subheadings=sec.get("subheadings"),
            )
            if new and new != old:
                sec["heading"] = new[:120]
                changed += 1
    return changed


def _rule_clean_heading(
    heading: str,
    *,
    preview: str = "",
    subheadings: Optional[Sequence[Dict[str, Any]]] = None,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> str:
    """Deterministic heading cleanup — never promote body preview text to a title."""
    h = _norm(heading)
    if not h:
        return h

    h = _strip_page_disambiguation_suffixes(h)

    m = _ART_ONLY.match(h)
    if m:
        arts = m.group(1).strip()
        arts = re.sub(r"^(?:arts?\.?|articles?\.?)\s*", "", arts, flags=re.I).strip()
        return f"Article {arts}"[:120]

    if _YEAR_ART.match(h):
        rest = h.split(".", 1)[-1].strip()
        if rest and not is_weak_section_heading(rest):
            return rest[:120]
        from_sub = title_from_subheadings(subheadings, registry=registry)
        if from_sub:
            return from_sub

    if _NUM_PREFIX.match(h):
        stripped = _NUM_PREFIX.sub("", h, count=1).strip()
        stripped = _strip_page_disambiguation_suffixes(stripped)
        if stripped and not is_weak_section_heading(stripped):
            return stripped[:120]

    if _PAREN_ONLY.match(h) or _ROMAN_FRAGMENT.match(h):
        from_sub = title_from_subheadings(subheadings, registry=registry)
        if from_sub:
            return from_sub
        case_hint = case_hint_from_preview(preview)
        if case_hint:
            return case_hint[:120]

    if h.endswith("-") or _TRAILING_HYPHEN.search(h):
        from_sub = title_from_subheadings(subheadings, registry=registry)
        if from_sub:
            return from_sub[:120]

    cleaned = _strip_page_disambiguation_suffixes(h)
    if cleaned != h:
        return cleaned[:120]
    return h


def _duplicate_chapter_names(chapters: Sequence[Dict[str, Any]]) -> Set[str]:
    names = [_norm(str(c.get("heading") or "")) for c in chapters if _norm(str(c.get("heading") or ""))]
    return {n for n, count in Counter(names).items() if count > 1}


def _section_page_sort_key(sec: Dict[str, Any]) -> tuple:
    return (
        sec.get("page_number") is None,
        int(sec.get("page_number") or 0),
        int(sec.get("line_id") or 0),
    )


def merge_duplicate_named_chapters(
    chapters: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Merge chapters that share the same title — append sections in page order."""
    if not chapters:
        return chapters, 0
    out: List[Dict[str, Any]] = []
    index_by_name: Dict[str, int] = {}
    merged = 0
    for ch in chapters:
        name = normalize_heading(str(ch.get("heading") or ""))
        if not name:
            out.append(ch)
            continue
        if name in index_by_name:
            target = out[index_by_name[name]]
            combined = list(target.get("sections") or []) + list(ch.get("sections") or [])
            combined.sort(key=_section_page_sort_key)
            target["sections"] = combined
            for key in ("page_end",):
                a = target.get(key)
                b = ch.get(key)
                if a is not None and b is not None:
                    target[key] = max(int(a), int(b))
            merged += 1
            continue
        out.append(ch)
        index_by_name[name] = len(out) - 1
    return out, merged


def disambiguate_duplicate_chapter_titles(chapters: List[Dict[str, Any]]) -> int:
    """Suffix duplicate chapter titles with page when merge is not used."""
    dupes = _duplicate_chapter_names(chapters)
    if not dupes:
        return 0
    changed = 0
    seen: Dict[str, int] = {}
    for ch in chapters:
        name = _norm(str(ch.get("heading") or ""))
        if name not in dupes:
            continue
        seen[name] = seen.get(name, 0) + 1
        new_name = _rule_dedupe_chapter_title(name, ch, seen[name])
        if new_name != name:
            ch["heading"] = new_name
            changed += 1
    return changed


def _heading_dedupe_key(heading: str) -> str:
    """Normalize near-duplicate labels (Illustration ≈ Illustrations)."""
    n = normalize_heading(heading)
    if _ILLUSTRATION_HEADING_RE.match(n):
        return "illustration"
    return n


def _collapse_generic_disambiguation(heading: str, preview: str = "") -> str:
    """Prefer substantive suffix over 'Illustrations — …' style labels not in the PDF."""
    h = _norm(heading)
    if not re.search(r"\s+[—–-]\s+", h):
        return h
    base, suffix = re.split(r"\s+[—–-]\s+", h, maxsplit=1)
    base_key = base.lower().rstrip(".:-")
    suffix = (suffix or "").strip()
    if base_key in _GENERIC_DISAMBIG_BASES and len(suffix) >= 8:
        from src.modules.structure.dropped_heading_registry import is_acceptable_study_title

        # The generic prefix (Illustrations/Notes/Example —) is the noise; prefer
        # any substantive multi-word, non-prose suffix even if it is a caps
        # partition line (downstream display resolvers normalize casing).
        if (
            is_acceptable_study_title(suffix)
            or (len(suffix.split()) >= 2 and not is_sentence_like_title(suffix))
        ):
            return suffix[:120]
    if len(h) >= 115:
        from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

        frag = title_from_fragment_preview({"fragment": {"preview": preview}})
        if frag:
            return frag[:120]
    return h


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


_GENERIC_DUPLICATE_HEADINGS = frozenset(
    {
        "brief historical background",
        "introduction",
        "concluding note",
    }
)
_ART_ONLY_HEADING = re.compile(r"^\[?\s*(?:art(?:icle)?\.?\s*\d+[a-z]?)\s*\]?\)?$", re.I)
_NUMBERED_SUBCLAUSE = re.compile(r"^\(\d+\)\s+\S")
_ROMAN_SECTION_HEADING = re.compile(
    r"^(?:[IVXLC]{1,4}\.|\(?[IVXLC]{1,4}\))\s+[A-Za-z]",
    re.I,
)
_MERGE_SUFFIX = re.compile(r"\s+[—–-]\s+")
_PAGE_REF_IN_TEXT = re.compile(r"\(p\.\s*\d+\)", re.I)


def _is_specific_numbered_clause(heading: str) -> bool:
    """(3) Protection against self-incrimination … — specific sub-clause, not a bare marker."""
    h = _norm(heading)
    match = re.match(r"^\(\d+\)\s+(.+)$", h)
    if not match:
        return False
    return len(match.group(1).strip()) >= 12


def _is_broader_parent_title(parent: str, child: str) -> bool:
    """True when parent is a Roman-numeral section encompassing a numbered sub-clause."""
    p = _norm(parent)
    c = _norm(child)
    if not p or not c:
        return False
    if _ROMAN_SECTION_HEADING.match(p) and _NUMBERED_SUBCLAUSE.match(c):
        return True
    if p.lower() in c.lower() and len(p) >= 20:
        return True
    return False


def _strip_redundant_merge_suffix(heading: str, sibling_headings: Sequence[str]) -> str:
    """Remove truncated or redundant ' — parent section' suffixes from disambiguation."""
    h = _norm(heading)
    if not _MERGE_SUFFIX.search(h):
        return h
    base, suffix = re.split(r"\s+[—–-]\s+", h, maxsplit=1)
    base = base.strip()
    suffix = (suffix or "").strip()
    if not base or not suffix:
        return h
    # Truncated at 120-char cap (garbled tail)
    if len(h) >= 115 and len(suffix) > 20 and not suffix[-1].isalnum() and suffix[-1] not in ")]":
        return base[:120]
    for sib in sibling_headings:
        sib_n = _norm(sib)
        if not sib_n:
            continue
        if sib_n.lower().startswith(suffix.lower()[: min(24, len(suffix))]):
            return base[:120]
        if suffix.lower().startswith(sib_n.lower()[: min(24, len(sib_n))]):
            return base[:120]
    if _is_broader_parent_title(suffix, base):
        return base[:120]
    return h


def sanitize_merged_section_titles(chapters: List[Dict[str, Any]]) -> int:
    """Clean up bad merged titles across all sections in a hierarchy."""
    all_headings = [
        _norm(str(sec.get("heading") or ""))
        for ch in chapters
        for sec in ch.get("sections") or []
    ]
    changed = 0
    for ch in chapters:
        siblings = [
            _norm(str(s.get("heading") or ""))
            for s in ch.get("sections") or []
        ]
        for sec in ch.get("sections") or []:
            heading = _norm(str(sec.get("heading") or ""))
            if not heading:
                continue
            cleaned = _rule_clean_heading(
                heading,
                subheadings=sec.get("subheadings"),
            )
            cleaned = _strip_redundant_merge_suffix(cleaned, siblings)
            cleaned = _collapse_generic_disambiguation(cleaned, _preview_text(sec))
            if cleaned != heading:
                sec["heading"] = cleaned
                changed += 1
    return changed


def _topic_phrase_from_preview(preview: str, *, max_words: int = 7) -> str:
    """Disambiguation hint from preview — case names only, never prose sentences."""
    return case_hint_from_preview(preview)


def _disambiguate_section_heading(
    heading: str,
    *,
    chapter_heading: str,
    preview: str,
    page_number: Optional[int],
    occurrence: int,
    subheadings: Optional[Sequence[Dict[str, Any]]] = None,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> str:
    base = _norm(heading)
    if not base:
        return base
    if _is_specific_numbered_clause(base):
        return base[:120]
    from src.modules.structure.dropped_heading_registry import is_noisy_fragment_heading
    from src.modules.structure.final_structuring.heading_title_engine import title_from_fragment_preview

    if is_noisy_fragment_heading(base):
        frag_title = title_from_fragment_preview(
            {"fragment": {"preview": preview}, "subheadings": list(subheadings or [])}
        )
        if frag_title and frag_title.lower() != base.lower():
            return frag_title[:120]

    from_sub = title_from_subheadings(subheadings, registry=registry)
    if from_sub and from_sub.lower() != base.lower():
        if _is_broader_parent_title(from_sub, base):
            return base[:120]
        if is_weak_section_heading(base) and not is_weak_section_heading(from_sub):
            return from_sub[:120]
        return f"{base} — {from_sub}"[:120]
    topic = _topic_phrase_from_preview(preview)
    if topic and topic.lower() != base.lower():
        return _collapse_generic_disambiguation(f"{base} — {topic}", preview)[:120]
    if chapter_heading:
        short_ch = _norm(chapter_heading)[:45]
        if page_number:
            return f"{base} — {short_ch} (p. {page_number})"[:120]
        return f"{base} — {short_ch}"[:120]
    if page_number:
        return f"{base} (p. {page_number})"[:120]
    if occurrence > 1:
        return f"{base} ({occurrence})"[:120]
    return base


def _should_disambiguate_section_heading(heading: str, *, duplicate: bool) -> bool:
    from src.modules.structure.dropped_heading_registry import is_noisy_fragment_heading

    h = _norm(heading)
    if not h:
        return False
    if duplicate:
        return True
    if is_noisy_fragment_heading(h):
        return True
    if h.lower() in _GENERIC_DUPLICATE_HEADINGS:
        return True
    if _ART_ONLY_HEADING.match(h):
        return True
    if is_weak_section_heading(h):
        return True
    return False


def disambiguate_duplicate_section_headings(
    chapters: List[Dict[str, Any]],
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> int:
    """Suffix duplicate or generic section titles using chapter context and preview text."""
    counts: Counter[str] = Counter()
    for ch in chapters:
        for sec in ch.get("sections") or []:
            h = _heading_dedupe_key(str(sec.get("heading") or ""))
            if h:
                counts[h] += 1

    changed = 0
    seen: Dict[str, int] = {}
    for ch in chapters:
        chapter_heading = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            heading = _norm(str(sec.get("heading") or ""))
            if not heading:
                continue
            duplicate = counts[_heading_dedupe_key(heading)] > 1
            if not _should_disambiguate_section_heading(heading, duplicate=duplicate):
                continue
            seen[heading] = seen.get(heading, 0) + 1
            new_heading = _disambiguate_section_heading(
                heading,
                chapter_heading=chapter_heading,
                preview=_preview_text(sec),
                page_number=sec.get("page_number"),
                occurrence=seen[heading],
                subheadings=sec.get("subheadings"),
                registry=registry,
            )
            new_heading = _collapse_generic_disambiguation(new_heading, _preview_text(sec))
            if new_heading != heading:
                sec["heading"] = new_heading
                changed += 1
    return changed


def _apply_rule_pass(
    chapters: List[Dict[str, Any]],
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Tuple[int, int, int]:
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
            cleaned = _rule_clean_heading(
                heading,
                preview=_preview_text(sec),
                subheadings=subs,
                registry=registry,
            )
            if cleaned != heading:
                sec["heading"] = cleaned
                sec_changed += 1
                heading = cleaned

            for sub in subs:
                sub_h = _norm(str(sub.get("heading") or ""))
                sub_preview = _preview_text(sub)
                sub_clean = _rule_clean_heading(
                    sub_h,
                    preview=sub_preview,
                    registry=registry,
                )
                if sub_clean != sub_h:
                    sub["heading"] = sub_clean
                    sub_changed += 1

    sec_changed += disambiguate_duplicate_section_headings(chapters, registry=registry)
    return sec_changed, sub_changed, ch_changed


def _ultimate_heading_map(ultimate_sections: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    return {
        str(sec.get("section_id") or ""): _norm(str(sec.get("heading") or ""))
        for sec in ultimate_sections
        if sec.get("section_id")
    }


def _is_allowed_title_change(
    original: str,
    candidate: str,
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> bool:
    if not candidate or not original:
        return False
    if registry and not registry.is_allowed_title(candidate):
        return False
    if is_sentence_like_title(candidate) and normalize_heading(candidate) != normalize_heading(original):
        return False
    if normalize_heading(candidate) == normalize_heading(original):
        return True
    if _rule_clean_heading(original, registry=registry) == candidate:
        return True
    if candidate.startswith(original) and " — " in candidate:
        suffix = candidate.split(" — ", 1)[1]
        return not is_sentence_like_title(suffix)
    return not is_sentence_like_title(candidate)


def _restore_title_from_ultimate(
    sec: Dict[str, Any],
    *,
    ultimate_heading: str,
    chapter_heading: str,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> str:
    subs = list(sec.get("subheadings") or [])
    cleaned = _rule_clean_heading(
        ultimate_heading,
        preview=_preview_text(sec),
        subheadings=subs,
        registry=registry,
    )
    if not is_weak_section_heading(cleaned) and (registry is None or registry.is_allowed_title(cleaned)):
        return cleaned
    from_sub = title_from_subheadings(subs, registry=registry)
    if from_sub:
        return from_sub
    if is_weak_section_heading(cleaned) or is_sentence_like_title(cleaned):
        return _disambiguate_section_heading(
            ultimate_heading or cleaned,
            chapter_heading=chapter_heading,
            preview="",
            page_number=sec.get("page_number"),
            occurrence=1,
            subheadings=subs,
            registry=registry,
        )
    return cleaned or ultimate_heading


def _enforce_ultimate_section_headings(
    chapters: List[Dict[str, Any]],
    *,
    ultimate_by_sid: Dict[str, str],
    registry: Optional[DroppedHeadingRegistry] = None,
) -> int:
    """Section titles must derive from 15d ultimate headings — never banned body text."""
    restored = 0
    for ch in chapters:
        chapter_heading = _norm(str(ch.get("heading") or ""))
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            ultimate = ultimate_by_sid.get(sid, "")
            if not ultimate:
                continue
            current = _norm(str(sec.get("heading") or ""))
            if _is_allowed_title_change(ultimate, current, registry=registry):
                continue
            sec["heading"] = _restore_title_from_ultimate(
                sec,
                ultimate_heading=ultimate,
                chapter_heading=chapter_heading,
                registry=registry,
            )
            restored += 1
    return restored


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


def _parse_cleanup_json(
    raw: str,
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
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
            if registry and not registry.is_allowed_title(heading):
                continue
            if is_sentence_like_title(heading):
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
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    if not sections and not subheadings and not chapters:
        return {"sections": [], "subheadings": [], "chapters": []}

    user = json.dumps(
        {"sections": list(sections), "subheadings": list(subheadings), "chapters": list(chapters)},
        ensure_ascii=False,
    )
    from src.shared.llm_provider import resolve_stage_provider

    provider = resolve_stage_provider(config.HEADING_CLEANUP_LLM or "")
    raw = client.chat_with_provider(provider, system=_CLEANUP_SYSTEM, user=user, max_tokens=4096)
    parsed = _parse_cleanup_json(raw or "", registry=registry)
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


def _apply_llm_results(
    chapters: List[Dict[str, Any]],
    parsed: Dict[str, List[Dict[str, Any]]],
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Tuple[int, int, int]:
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
                candidate = _norm(sec_map[sid])
                if candidate and (not registry or registry.is_allowed_title(candidate)):
                    sec["heading"] = candidate
                    sec_changed += 1
            for sub in sec.get("subheadings") or []:
                key = (sid, sub.get("line_id"))
                if key in sub_map:
                    candidate = _norm(sub_map[key])
                    if candidate and (not registry or registry.is_allowed_title(candidate)):
                        sub["heading"] = candidate
                        sub_changed += 1
    return sec_changed, sub_changed, ch_changed


def _minilm_cleanup(
    chapters: List[Dict[str, Any]],
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Tuple[str, int, int, int]:
    """Rules → subheading pick → MiniLM for weak titles."""
    from src.modules.structure.final_structuring.models.mini_lm_title_pick import mini_lm_pick_title

    threshold = float(getattr(config, "HEADING_CLEANUP_MINILM_PICK_THRESHOLD", 0.82) or 0.82)
    sec_changed = sub_changed = ch_changed = 0

    for ch in chapters:
        for sec in ch.get("sections") or []:
            heading = _norm(str(sec.get("heading") or ""))
            if is_weak_section_heading(heading):
                subs = list(sec.get("subheadings") or [])
                sub_titles = [_norm(str(s.get("heading") or "")) for s in subs]
                from_sub = title_from_subheadings(subs, registry=registry)
                if from_sub:
                    sec["heading"] = from_sub
                    sec_changed += 1
                    continue
                preview = _norm(str((sec.get("fragment") or {}).get("preview") or ""))
                picked = mini_lm_pick_title(
                    heading,
                    preview=preview,
                    subheadings=sub_titles,
                    threshold=threshold,
                    registry=registry,
                )
                if picked:
                    sec["heading"] = picked
                    sec_changed += 1

            for sub in sec.get("subheadings") or []:
                sub_h = _norm(str(sub.get("heading") or ""))
                if not is_weak_section_heading(sub_h):
                    continue
                picked = mini_lm_pick_title(sub_h, threshold=threshold, registry=registry)
                if picked:
                    sub["heading"] = picked
                    sub_changed += 1

    method = "rule+minilm" if (sec_changed or sub_changed) else "rule"
    return method, sec_changed, sub_changed, ch_changed


def _llm_cleanup(
    chapters: List[Dict[str, Any]],
    *,
    batch_size: int,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> Tuple[str, int, int, int]:
    from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider

    section_items, sub_items, chapter_items = _collect_llm_candidates(chapters)
    if not section_items and not sub_items and not chapter_items:
        return "rule_only", 0, 0, 0

    from src.shared.llm_provider import resolve_stage_provider

    provider = resolve_stage_provider(config.HEADING_CLEANUP_LLM or "")
    from src.shared.llm_provider import is_chat_provider

    if not is_chat_provider(provider):
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
            registry=registry,
        )
        if not parsed:
            logger.info("15f LLM batch %s failed; keeping rule-cleaned titles", i)
            had_failure = True
            continue
        s, sh, c = _apply_llm_results(chapters, parsed, registry=registry)
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
    ultimate_sections: Optional[Sequence[Dict[str, Any]]] = None,
    dropped_registry: Optional[DroppedHeadingRegistry] = None,
    use_llm: Optional[bool] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Stage 15f — return a copy of hierarchy with cleaned section/chapter headings."""
    from src.modules.pipeline.llm_chat_client import normalize_chat_provider

    out = copy.deepcopy(chapter_hierarchy)
    chapters = list(out.get("chapters") or [])
    if not chapters:
        return out

    registry = dropped_registry or DroppedHeadingRegistry()
    ultimate_by_sid = _ultimate_heading_map(ultimate_sections or [])

    if use_llm is None:
        use_llm = os.environ.get("HEADING_CLEANUP_USE_LLM", getattr(config, "HEADING_CLEANUP_USE_LLM", "1")).strip().lower() not in {
            "0",
            "false",
            "no",
            "n",
        }
    bs = int(batch_size or getattr(config, "HEADING_CLEANUP_BATCH_SIZE", 20) or 20)

    rule_sec, rule_sub, rule_ch = _apply_rule_pass(chapters, registry=registry)
    method = "rule"
    llm_sec = llm_sub = llm_ch = 0
    restored = 0

    backend = os.environ.get(
        "HEADING_CLEANUP_BACKEND",
        getattr(config, "HEADING_CLEANUP_BACKEND", ""),
    ).strip().lower()

    hierarchy_openai = getattr(config, "HIERARCHY_OPENAI_ENABLED", True)
    skip_15f_llm = hierarchy_openai and backend in {"rules_only", "off", "rules", ""}

    if backend in {"rules_only", "off", "rules", "minilm"}:
        minilm_method, mm_sec, mm_sub, mm_ch = _minilm_cleanup(chapters, registry=registry)
        method = minilm_method
        llm_sec += mm_sec
        llm_sub += mm_sub
        llm_ch += mm_ch
    elif use_llm and not skip_15f_llm and backend in {"openai", "openrouter"}:
        llm_method, llm_sec, llm_sub, llm_ch = _llm_cleanup(chapters, batch_size=bs, registry=registry)
        if llm_method != "rule_only":
            method = llm_method
    elif backend in {"flan", "bigbird"}:
        logger.warning("HEADING_CLEANUP_BACKEND=%s removed; using rules+minilm", backend)
        minilm_method, mm_sec, mm_sub, mm_ch = _minilm_cleanup(chapters, registry=registry)
        method = minilm_method
        llm_sec += mm_sec
        llm_sub += mm_sub
        llm_ch += mm_ch

    if ultimate_by_sid:
        restored = _enforce_ultimate_section_headings(
            chapters,
            ultimate_by_sid=ultimate_by_sid,
            registry=registry,
        )

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
            "heading_cleanup_backend": backend,
            "heading_cleanup_batch_size": bs,
            "heading_cleanup_restored_from_ultimate": restored,
        }
    )
    out["meta"] = meta
    out["chapters"] = chapters
    return out
