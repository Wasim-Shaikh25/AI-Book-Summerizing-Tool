"""Track headings rejected by early pipeline stages — they must never reappear as titles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Sequence, Set

from src.modules.generation.rewrite_validation import normalize_heading
from src.shared.english_text import contains_english_letters, is_primarily_english

_BODY_STARTER_RE = re.compile(
    r"^(it will be|he must|she must|they must|we must|this will|there is|there are|"
    r"if the|when the|where the|in the case|it is|it was|such a|such an|"
    r"no person|every person|any person|a person|the person|"
    r"who can |who may |who shall |can a |may a |shall a |"
    r"since the|the power|the language|the president may|the prime minister|"
    r"his |her |their |its |this |these |those )",
    re.I,
)
_INCOMPLETE_TRAIL_RE = re.compile(
    r"(,\s*viz\.?\s*$|,\s*$|\bwith the\s*$|\bthe\s*$|\band\s*$|\bor\s*$|\bof\s*$|\bto\s*$|\bin\s*$)",
    re.I,
)
_CASE_HINT_RE = re.compile(
    r"^(?:case\s+no\.?\s*\d+\s+)?((?:in\s+re\.?|union\s+of\s+india|[A-Z][A-Za-z.&]+(?:\s+[A-Z][A-Za-z.&]+){1,8}))",
    re.I,
)


_SYLLABUS_RE = re.compile(
    r"^(course\s+objectives?|course\s+outcomes?|syllabus|reading\s+list|"
    r"recommended\s+readings?|bibliography|references?)\s*:?\s*$",
    re.I,
)
_ESSAY_STYLE_RE = re.compile(
    r"^(a study of|an analysis of|the analysis of|a history of|a chapter on|"
    r"here are some|the following|this chapter|this section|a marriage registrar)",
    re.I,
)
_CURRENCY_ONLY_RE = re.compile(
    r"^(?:Rs\.?|INR|₹|\$|USD|EUR)?\s*[\d,]+(?:\.\d+)?\s*(?:lakh|lac|crore|cr|million|thousand|k)?\.?\s*$",
    re.I,
)
_CURRENCY_STATUTE_RE = re.compile(
    r"^(?:Rs\.?|INR|₹)\s*[\d,]+(?:\.\d+)?\s*(?:lakh|lac|crore|cr)\b",
    re.I,
)
_BNS_TAIL_RE = re.compile(r"[—–-]\s*\d+\s+bns\.?", re.I)
_UNBALANCED_PAREN_START_RE = re.compile(r"^[a-z][^()]{0,80}\)\s", re.I)
_MULTI_STATUTE_MERGE_RE = re.compile(
    r"section\s+\d+[^.]{0,80}\.\s*[—–-]\s*section\s+\d+",
    re.I,
)
_PROSE_CLAUSE_FRAGMENT_RE = re.compile(
    r"^(?:apprehension|intention|illustration)\s+has been\b",
    re.I,
)
_CHAPTER_LINE_PAGE_RE = re.compile(r"^OF\s+[A-Z][A-Z\s,&'-]+(?:\(p\.\s*\d+\))?\s*$")
_CLAUSE_FRAGMENT_RE = re.compile(
    r"^(which would|whoever|whosoever|whereas|provided that|\(\d+\)\s+whoever)\b",
    re.I,
)
_EXAMPLE_FRAGMENT_RE = re.compile(r"^example\s+\d+\s*:?\s*\(", re.I)
_TRUNCATED_TAIL_WORDS = frozenset(
    {
        "a",
        "an",
        "any",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "and",
        "as",
        "at",
        "be",
        "is",
        "are",
        "dangerous",
        "genuine",
        "dishonestly",
        "fraudulently",
        "voluntarily",
        "uses",
        "use",
        "causing",
        "hurt",
        "grievous",
        "such",
        "means",
        "boiling",
        "descripti",
        "description",
        "competent",
        "armed",
        "instrument",
        "less",
        "whose",
    }
)
_OF_TWENTY_THOUSAND_RE = re.compile(r"^of twenty thousand\b", re.I)
_CLASSIFICATION_ROW_RE = re.compile(
    r"^(?:classification\s*[—–-]\s*)?(?:non-)?cognizable\.?\s+bailable\.?",
    re.I,
)
_PAGE_FOOTER_RE = re.compile(
    r"^E\s*I\s*L\s*P\s*a\s*g\s*e|^P\s*a\s*g\s*e\s*\|?\s*$",
    re.I,
)
_BARE_SECTION_PAREN_RE = re.compile(r"^section\s*\(\s*\d+\s*\)\.?\s*$", re.I)
_STATUTE_NUMBER_BNS_RE = re.compile(r"^\d+\s+bns\.?[\"']?\.*\s*$", re.I)
_PROSE_SINGLE_LETTER_RE = re.compile(r"^[A-Z]\s+intentionally\b", re.I)
_FOR_PURPOSES_FRAGMENT_RE = re.compile(r"^for the purposes of this\b", re.I)
_PRECEDING_SECTION_RE = re.compile(r"^preceding section\b", re.I)
_QUOTED_IPC_FRAGMENT_RE = re.compile(r'^["\'].*\(IPC\b', re.I)
_INCOMPLETE_TAIL_RE = re.compile(
    r"\b(renders such|either descripti|the boiling|weapons or means|may be a theft|"
    r"of twenty thousand|description of imprisonment|be of either description| or whose)\s*$",
    re.I,
)
_SEAL_PLATE_FRAGMENT_RE = re.compile(r"^seal,\s*plate or other instrument\b", re.I)
_STATUTE_EXPLANATION_RE = re.compile(r"^explanation\s*:\s*", re.I)
_STATUTE_SECTION_PROSE_RE = re.compile(
    r"^section\s+\d+[A-Za-z]?\s*:\s*.+[—–-]\s",
    re.I,
)
_STATUTE_GENERAL_EXCEPTIONS_RE = re.compile(r"^general exceptions\s*[—–-]", re.I)


def is_statute_prose_heading(text: str) -> bool:
    """Statute PDF lines (Explanation:, Section N: … — tail) — not study section titles."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return False
    if _STATUTE_EXPLANATION_RE.match(t):
        return True
    if _STATUTE_SECTION_PROSE_RE.match(t):
        return True
    if _STATUTE_GENERAL_EXCEPTIONS_RE.match(t):
        return True
    if re.match(r"^illustration\s*[\d.:]", t, re.I):
        return True
    return False


_LABELED_PROSE_PREFIX_RE = re.compile(
    r"^(?:section|sec\.?|art\.?|article|chapter|ch\.?|clause|rule|order|para(?:graph)?|"
    r"explanation|illustration|provision)\s*[\dIVXLC]*[A-Za-z]?\s*[:\.\-–—]\s*(.+)$",
    re.I,
)
_TOPIC_BOUNDARY_RE = re.compile(r"\.\s|\s[—–-]\s|\s*\(")


def topic_from_labeled_prose(text: str) -> str:
    """Extract a clean topic from a labeled-prose heading (subject-agnostic).

    Examples:
        'Section 309: Robbery. — Fund held and administered…' -> 'Robbery'
        'Chapter 3: Photosynthesis. — The process by which…'   -> 'Photosynthesis'
        'Section 4: Punishments (IPC – 53)'                     -> 'Punishments'
        'GENERAL EXCEPTIONS — Of the Right of Private Defence'  -> 'General Exceptions'

    Returns '' when no clean topic can be isolated (e.g. pure prose after the label).
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    m = _LABELED_PROSE_PREFIX_RE.match(t)
    if m:
        t = m.group(1).strip()
    # Cut at the first sentence end, dash-clause, or parenthetical.
    t = _TOPIC_BOUNDARY_RE.split(t, maxsplit=1)[0].strip(" .,;:—–-")
    if not t:
        return ""
    alpha = re.sub(r"[^A-Za-z]", "", t)
    if alpha and alpha.isupper():
        t = study_title_case(t)
    # A genuine topic label is short; longer output means we captured prose.
    if len(t.split()) > 7 or len(t) < 3:
        return ""
    return t[:120] if is_acceptable_study_title(t) else ""


def is_sentence_like_title(text: str) -> bool:
    """True when text looks like body prose, not a study topic title."""
    t = (text or "").strip()
    if not t:
        return True
    if _BODY_STARTER_RE.search(t):
        return True
    if _INCOMPLETE_TRAIL_RE.search(t):
        return True
    if t.endswith(".") and len(t.split()) >= 8:
        return True
    if len(t) > 95:
        return True
    if len(t.split()) > 16:
        return True
    return False


def is_syllabus_heading(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return False
    if _SYLLABUS_RE.match(t):
        return True
    low = t.lower()
    if low.startswith("course objectives") or low.startswith("course outcomes"):
        return True
    return False


def is_essay_style_title(text: str) -> bool:
    """Reject essay-style phrases as study headings (e.g. 'A study of …')."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if _ESSAY_STYLE_RE.match(t):
        return True
    if re.match(r"^(a|an|the)\s+\w+\s+of\s+", t, re.I) and len(t.split()) >= 5:
        return True
    return False


def is_flan_awkward_title(text: str) -> bool:
    """Deprecated alias — use :func:`is_essay_style_title`."""
    return is_essay_style_title(text)


def is_incomplete_pdf_heading(text: str) -> bool:
    """PDF line-break / table fragments — truncated statutes, amounts, clause starts."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if _CURRENCY_ONLY_RE.match(t):
        return True
    if _CURRENCY_STATUTE_RE.search(t):
        return True
    if _BNS_TAIL_RE.search(t):
        return True
    if _UNBALANCED_PAREN_START_RE.match(t):
        return True
    if _MULTI_STATUTE_MERGE_RE.search(t):
        return True
    if _PROSE_CLAUSE_FRAGMENT_RE.match(t):
        return True
    if _CHAPTER_LINE_PAGE_RE.match(t):
        return True
    if re.search(r"\band\s+bns\.?\s*$", t, re.I):
        return True
    if _CLAUSE_FRAGMENT_RE.match(t):
        return True
    if _EXAMPLE_FRAGMENT_RE.match(t):
        return True
    if _CLASSIFICATION_ROW_RE.match(t):
        return True
    if _PAGE_FOOTER_RE.search(t):
        return True
    if _BARE_SECTION_PAREN_RE.match(t):
        return True
    if _STATUTE_NUMBER_BNS_RE.match(t):
        return True
    if _PROSE_SINGLE_LETTER_RE.match(t):
        return True
    if _FOR_PURPOSES_FRAGMENT_RE.match(t):
        return True
    if _PRECEDING_SECTION_RE.match(t):
        return True
    if _QUOTED_IPC_FRAGMENT_RE.match(t):
        return True
    if _INCOMPLETE_TAIL_RE.search(t):
        return True
    if _SEAL_PLATE_FRAGMENT_RE.match(t):
        return True
    if _OF_TWENTY_THOUSAND_RE.match(t):
        return True
    if t.lower().startswith("section topic (p."):
        return True
    if is_sentence_like_title(t) and not t.endswith("."):
        words = t.split()
        if len(words) >= 5 and words[-1].lower().rstrip(",") in _TRUNCATED_TAIL_WORDS:
            return True
    if not re.search(r"[.):]\s*$", t):
        words = t.split()
        if len(words) >= 4 and words[-1].lower().rstrip(",") in _TRUNCATED_TAIL_WORDS:
            return True
        if re.match(r"^(?:section|art\.?|article)\s+\d+", t, re.I) and len(words) >= 6:
            if words[-1].lower().rstrip(",") in _TRUNCATED_TAIL_WORDS:
                return True
    if len(t.split()) > 12 and not re.search(r"\(\s*(?:Art|Section|S)\.?\s*\d", t, re.I):
        return True
    return False


_OVERVIEW_PREFIX_RE = re.compile(r"^overview of\b", re.I)
_MODULE_UNIT_RE = re.compile(r"^\s*(module|unit)\s+\d+", re.I)
_GENERIC_SUFFIX_RE = re.compile(r"\boverview\s*$", re.I)


_NOISE_FRAGMENT_RE = re.compile(
    r"^\(IPC\b|^\(IPC\s|^\d{1,2}\s*years?\s*$|^[A-Z]\)\s*$|^\([A-Za-z]\s*$|^[A-Z]\.\s*Z\.\s*$",
    re.I,
)
_SUBJECT_CAPS_RE = re.compile(r"^[A-Z][A-Z\s\-]{6,}\s*:?\s*$")
_MODULE_UNIT_PART_RE = re.compile(r"^\s*(module|unit|part)\s+[\dIVXLC]+", re.I)
_CHAPTER_PART_PREFIX_RE = re.compile(
    r"^\s*(?:chapter|part)\s+[\dIVXLC]+\s*(?:[:\-–—\.]\s*|\s+)",
    re.I,
)
_MAJOR_OF_CAPS_RE = re.compile(r"^OF\s+[A-Z]", re.I)
_STUDY_TITLE_SMALL_WORDS = frozenset(
    {"a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "by", "with", "at", "from", "as"}
)
_STUDY_TITLE_ACRONYMS = frozenset({"BNS", "IPC", "DPSP", "PIL", "NGT", "CPC", "CRPC", "SC", "HC"})


def is_structural_partition_heading(text: str) -> bool:
    """Book partition labels (CHAPTER I:, OF OFFENCES…) — chapter breaks only, not section/subtopic titles."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or is_syllabus_heading(t):
        return False
    if _MODULE_UNIT_PART_RE.match(t):
        return True
    if _CHAPTER_PART_PREFIX_RE.match(t):
        return True
    if re.match(r"^\s*(?:chapter|part)\s+[\dIVXLC]+\s*$", t, re.I):
        return True
    if _MAJOR_OF_CAPS_RE.match(t) and len(t.split()) >= 3:
        return True
    letters = re.sub(r"[^A-Za-z]", "", t)
    if letters.isupper() and len(letters) >= 14 and len(t.split()) >= 3:
        if re.match(r"^(?:CHAPTER|PART|OF)\b", t, re.I):
            return True
    return False


def study_title_case(text: str) -> str:
    """Normalize ALL-CAPS partition lines to readable title case."""
    words = re.sub(r"\s+", " ", (text or "").strip()).split()
    if not words:
        return ""
    out: list[str] = []
    for i, word in enumerate(words):
        bare = re.sub(r"[^\w]", "", word)
        upper = bare.upper()
        if upper in _STUDY_TITLE_ACRONYMS:
            out.append(upper + word[len(bare) :] if len(word) > len(bare) else "")
            continue
        if i > 0 and word.lower() in _STUDY_TITLE_SMALL_WORDS:
            out.append(word.lower())
        elif word.isupper() and len(bare) > 1:
            out.append(word.capitalize())
        else:
            out.append(word)
    return " ".join(out)


def partition_heading_to_study_title(text: str) -> str:
    """CHAPTER I: PRELIMINARY → Preliminary; OF OFFENCES AGAINST THE STATE → Offences Against the State."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    m = re.match(
        r"^(?:chapter|part)\s+[\dIVXLC]+\s*[:\-–—\.]\s*(.+)$",
        t,
        re.I,
    )
    if m:
        t = m.group(1).strip()
    elif re.match(r"^(?:chapter|part)\s+[\dIVXLC]+\s*$", t, re.I):
        return ""
    if re.match(r"^OF\s+", t, re.I):
        t = re.sub(r"^OF\s+", "", t, flags=re.I).strip()
    alpha = re.sub(r"[^A-Za-z]", "", t)
    if alpha and alpha.isupper():
        t = study_title_case(t)
    return t[:120]


def is_noisy_fragment_heading(text: str) -> bool:
    """PDF fragment garbage — partial IPC refs, lone letters, incomplete clauses."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if is_incomplete_pdf_heading(t):
        return True
    if _NOISE_FRAGMENT_RE.match(t):
        return True
    if t.lower().startswith("section topic (p."):
        return True
    if t.startswith("(") and not t.endswith(")") and len(t) < 50:
        return True
    if len(t) <= 3 and not re.match(r"^section\s+\d", t, re.I):
        return True
    if len(t) > 95:
        return True
    words = t.split()
    if len(words) >= 12 and t.endswith((".", ",")):
        return True
    return False


def is_generic_study_title(text: str, *, book_title: str = "") -> bool:
    """True when a title is too vague for study notes (module label, overview echo, book slug)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if _OVERVIEW_PREFIX_RE.match(t):
        return True
    if _MODULE_UNIT_RE.match(t):
        return True
    if _SUBJECT_CAPS_RE.match(t) and len(t.split()) <= 4:
        return True
    if _GENERIC_SUFFIX_RE.search(t) and len(t.split()) <= 5:
        return True
    # Structurally vague labels only — no subject-specific vocabulary.
    low = t.lower()
    if low in {
        "introduction",
        "intro",
        "general",
        "miscellaneous",
    }:
        return True
    if book_title:
        bt = normalize_heading(book_title.replace("-", " ").replace("_", " "))
        if bt and normalize_heading(t) == bt:
            return True
    return False


def is_acceptable_study_title(text: str, *, book_title: str = "") -> bool:
    from src.modules.generation.rewrite_validation import is_weak_section_heading

    t = (text or "").strip()
    if not t or is_weak_section_heading(t):
        return False
    if is_sentence_like_title(t) or is_essay_style_title(t) or is_syllabus_heading(t):
        return False
    if is_statute_prose_heading(t):
        return False
    if is_generic_study_title(t, book_title=book_title):
        return False
    if is_noisy_fragment_heading(t):
        return False
    if is_structural_partition_heading(t):
        return False
    if len(t.split()) > 12 and not re.search(r"\(\s*(?:Art|Section|S)[.\s-]*\d", t, re.I):
        return False
    if not contains_english_letters(t) or not is_primarily_english(t):
        return False
    return True


@dataclass
class DroppedHeadingRegistry:
    line_ids: Set[int] = field(default_factory=set)
    normalized_texts: Set[str] = field(default_factory=set)

    def register(self, *, line_id: Optional[int] = None, text: str = "") -> None:
        if isinstance(line_id, int):
            self.line_ids.add(line_id)
        norm = normalize_heading(text)
        if norm:
            self.normalized_texts.add(norm)

    def is_banned_text(self, text: str) -> bool:
        norm = normalize_heading(text)
        return bool(norm and norm in self.normalized_texts)

    def is_allowed_title(self, text: str) -> bool:
        if not (text or "").strip():
            return False
        if self.is_banned_text(text):
            return False
        if is_sentence_like_title(text):
            return False
        if not contains_english_letters(text) or not is_primarily_english(text):
            return False
        return True

    def extend_from_gate_log(self, rows: Iterable[Dict[str, Any]]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action") or row.get("decision") or "").lower()
            if action not in {"drop_heading_validity_gate", "dropped", "drop"}:
                continue
            text = str(row.get("text") or "")
            lid = row.get("line_id")
            if not isinstance(lid, int):
                start = row.get("start_line") or row.get("id")
                if isinstance(start, str) and start.startswith("L"):
                    try:
                        lid = int(start[1:].split(":", 1)[0])
                    except ValueError:
                        lid = None
                elif isinstance(start, int):
                    lid = start
            self.register(line_id=lid if isinstance(lid, int) else None, text=text)

    def extend_from_continuity_log(self, rows: Iterable[Dict[str, Any]]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            reason = str(row.get("reason") or row.get("action") or "")
            if "drop" not in reason.lower():
                continue
            self.register(
                line_id=row.get("line_id") if isinstance(row.get("line_id"), int) else None,
                text=str(row.get("text") or ""),
            )

    def extend_from_title_validation_log(self, rows: Iterable[Dict[str, Any]]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("action") or "") != "drop_title_validation":
                continue
            self.register(
                line_id=row.get("line_id") if isinstance(row.get("line_id"), int) else None,
                text=str(row.get("text") or ""),
            )


def case_hint_from_preview(preview: str) -> str:
    """Extract a case-name hint only — never return a prose sentence."""
    text = re.sub(r"\s+", " ", (preview or "").strip())
    if not text or is_sentence_like_title(text):
        return ""
    match = _CASE_HINT_RE.match(text)
    if not match:
        return ""
    phrase = re.sub(r"\s+", " ", (match.group(1) or "").strip())
    if len(phrase) < 10 or is_sentence_like_title(phrase):
        return ""
    return phrase[:80]


def title_from_subheadings(
    subheadings: Optional[Sequence[Dict[str, Any]]],
    *,
    registry: Optional[DroppedHeadingRegistry] = None,
) -> str:
    """Pick the first valid ultimate subheading (from 15d), not body preview."""
    for sub in subheadings or []:
        heading = re.sub(r"\s+", " ", str(sub.get("heading") or "").strip())
        if not heading:
            continue
        if registry and not registry.is_allowed_title(heading):
            continue
        if is_sentence_like_title(heading) or is_syllabus_heading(heading) or is_essay_style_title(heading):
            continue
        return heading[:120]
    return ""


def load_dropped_registry_from_log_dir(log_dir) -> DroppedHeadingRegistry:
    """Rebuild dropped-heading registry from saved pipeline stage logs."""
    import json
    from pathlib import Path

    from src.modules.pipeline.stage_registry import resolve_existing_artifact

    registry = DroppedHeadingRegistry()
    log_path = Path(log_dir)

    gate_path = resolve_existing_artifact(log_path, "heading_validity_gate")
    if gate_path is not None:
        payload = json.loads(gate_path.read_text(encoding="utf-8"))
        registry.extend_from_gate_log(payload.get("items") or payload if isinstance(payload, list) else [])

    cont_path = resolve_existing_artifact(log_path, "continuity_filter")
    if cont_path is not None:
        payload = json.loads(cont_path.read_text(encoding="utf-8"))
        registry.extend_from_continuity_log(payload.get("items") or payload if isinstance(payload, list) else [])

    val_path = resolve_existing_artifact(log_path, "heading_title_validation")
    if val_path is not None:
        payload = json.loads(val_path.read_text(encoding="utf-8"))
        registry.extend_from_title_validation_log(payload.get("items") or payload if isinstance(payload, list) else [])

    return registry
