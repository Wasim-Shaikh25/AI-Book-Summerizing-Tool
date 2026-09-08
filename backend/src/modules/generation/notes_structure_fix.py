"""Post-rewrite structural cleanup for generated notes Markdown.

This module runs *after* the rewrite/export stage. It never edits section body
prose — it only fixes structural defects that survive rewriting:

1. Heading repair   — replace noisy / fragment / prose section titles with a
                      clean topic title derived from the (already clean) body.
                      Hybrid engine: one batched LLM call when chat is enabled,
                      MiniLM-from-body otherwise, with `ensure_study_safe_heading`
                      as a deterministic floor.
2. Duplicate merge  — detect near-identical adjacent sections in the same chapter
                      and (opt-in) merge their bodies.
3. Low-grounding    — flag (opt-in drop) sections whose *source* was an index /
                      contents list, so the body is ungrounded. Requires the
                      pipeline log dir to reconstruct source text.

Detection is fully subject-agnostic: it uses the structural heading classifier,
embedding similarity, and measured grounding signals only — no domain words.
The Table of Contents is regenerated from the repaired headings so notes stay
internally consistent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.modules.generation.rewrite_validation import SECTION_ID_TAG
from src.modules.generation.markdown_format_normalizer import renumber_ordered_list_blocks
from src.modules.quality.heuristics import classify_heading
from src.modules.structure.final_structuring.heading_title_engine import (
    ensure_study_safe_heading,
)

_MINILM_MODEL = "all-MiniLM-L6-v2"

_TOC_HEADING = "# Table of Contents"
_OPENXML_FENCE = "```{=openxml}"

# Tokens ignored when scoring note-body similarity for duplicate detection.
_DUP_STOPWORDS = frozenset(
    {
        "that", "this", "with", "from", "have", "been", "will", "shall",
        "section", "article", "articles", "which", "their", "there", "these",
        "those", "when", "where", "what", "into", "about", "under", "such",
        "also", "person", "whoever", "any", "the", "and", "for",
    }
)


# --------------------------------------------------------------------------- #
# Document model
# --------------------------------------------------------------------------- #
@dataclass
class Section:
    level: int  # 2 (##) or 3 (###)
    sid: str
    title: str
    body_lines: List[str] = field(default_factory=list)
    dropped: bool = False
    low_grounding: bool = False
    merged_from: List[str] = field(default_factory=list)

    def body_text(self) -> str:
        return "\n".join(self.body_lines).strip()


@dataclass
class Chapter:
    title: str
    pre_lines: List[str] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)


@dataclass
class NotesDoc:
    preamble: List[str]
    toc_present: bool
    toc_tail: List[str]
    chapters: List[Chapter]

    def iter_sections(self):
        for ch in self.chapters:
            for sec in ch.sections:
                yield ch, sec


@dataclass
class FixChange:
    kind: str  # "heading" | "merge" | "low_grounding"
    sid: str
    before: str
    after: str
    detail: str = ""


@dataclass
class FixReport:
    engine: str
    heading_model: str
    embedding_model: str
    generated_at: str
    sections_total: int = 0
    headings_noisy: int = 0
    headings_repaired: int = 0
    duplicate_pairs: int = 0
    duplicates_merged: int = 0
    low_grounding_flagged: int = 0
    low_grounding_dropped: int = 0
    changes: List[FixChange] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "heading_model": self.heading_model,
            "embedding_model": self.embedding_model,
            "generated_at": self.generated_at,
            "sections_total": self.sections_total,
            "headings_noisy": self.headings_noisy,
            "headings_repaired": self.headings_repaired,
            "duplicate_pairs": self.duplicate_pairs,
            "duplicates_merged": self.duplicates_merged,
            "low_grounding_flagged": self.low_grounding_flagged,
            "low_grounding_dropped": self.low_grounding_dropped,
            "changes": [
                {
                    "kind": c.kind,
                    "sid": c.sid,
                    "before": c.before,
                    "after": c.after,
                    "detail": c.detail,
                }
                for c in self.changes
            ],
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------- #
# Parsing / rendering
# --------------------------------------------------------------------------- #
def parse_notes_md(md_text: str) -> NotesDoc:
    """Split notes Markdown into preamble, TOC tail, and chapter/section blocks."""
    lines = md_text.splitlines()
    n = len(lines)

    toc_idx: Optional[int] = None
    for i, ln in enumerate(lines):
        if ln.strip() == _TOC_HEADING:
            toc_idx = i
            break

    search_from = (toc_idx + 1) if toc_idx is not None else 0
    body_idx: Optional[int] = None
    for i in range(search_from, n):
        ln = lines[i]
        if ln.startswith("# ") and not ln.startswith("## "):
            body_idx = i
            break

    if body_idx is None:
        return NotesDoc(preamble=lines, toc_present=False, toc_tail=[], chapters=[])

    if toc_idx is not None:
        preamble = lines[:toc_idx]
        toc_region = lines[toc_idx:body_idx]
        toc_tail = _extract_toc_tail(toc_region)
        toc_present = True
    else:
        preamble = lines[:body_idx]
        toc_tail = []
        toc_present = False

    chapters = _parse_body(lines[body_idx:])
    return NotesDoc(preamble=preamble, toc_present=toc_present, toc_tail=toc_tail, chapters=chapters)


def _extract_toc_tail(toc_region: List[str]) -> List[str]:
    """Keep the trailing page-break openxml block of the TOC region verbatim."""
    last_fence = -1
    for i, ln in enumerate(toc_region):
        if ln.strip().startswith(_OPENXML_FENCE):
            last_fence = i
    if last_fence < 0:
        return [""]
    return toc_region[last_fence:]


def _parse_body(body: List[str]) -> List[Chapter]:
    chapters: List[Chapter] = []
    cur_ch: Optional[Chapter] = None
    cur_sec: Optional[Section] = None

    for ln in body:
        if ln.startswith("# ") and not ln.startswith("## "):
            # The heading line itself is rendered from `title`; pre_lines holds
            # only what follows it (blank lines, intro text, page-break blocks).
            cur_ch = Chapter(title=ln[2:].strip(), pre_lines=[])
            chapters.append(cur_ch)
            cur_sec = None
            continue
        is_h2 = ln.startswith("## ") and not ln.startswith("### ")
        is_h3 = ln.startswith("### ") and not ln.startswith("#### ")
        if is_h2 or is_h3:
            level = 2 if is_h2 else 3
            raw = ln[level + 1:].strip()
            sid_m = SECTION_ID_TAG.search(raw)
            sid = sid_m.group(1) if sid_m else ""
            title = SECTION_ID_TAG.sub("", raw).strip()
            cur_sec = Section(level=level, sid=sid, title=title)
            if cur_ch is None:
                cur_ch = Chapter(title="")
                chapters.append(cur_ch)
            cur_ch.sections.append(cur_sec)
            continue
        if cur_sec is not None:
            cur_sec.body_lines.append(ln)
        elif cur_ch is not None:
            cur_ch.pre_lines.append(ln)

    return chapters


def render_notes_md(doc: NotesDoc) -> str:
    out: List[str] = list(doc.preamble)

    if doc.toc_present:
        out.append(_TOC_HEADING)
        out.append("")
        for ci, ch in enumerate(doc.chapters, 1):
            out.append(f"## {ci}. {ch.title}")
            for sec in ch.sections:
                if sec.dropped or sec.level != 2:
                    continue
                out.append(f"- {sec.title}")
            out.append("")
        out.extend(doc.toc_tail)

    for ch in doc.chapters:
        if ch.title:
            out.append(f"# {ch.title}")
        out.extend(ch.pre_lines)
        for sec in ch.sections:
            if sec.dropped:
                continue
            tag = f" <!-- sid:{sec.sid} -->" if sec.sid else ""
            prefix = "#" * sec.level
            out.append(f"{prefix} {sec.title}{tag}")
            out.extend(renumber_ordered_list_blocks(sec.body_lines))

    return "\n".join(out).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- #
# Heading repair
# --------------------------------------------------------------------------- #
def _is_noisy(title: str) -> bool:
    return classify_heading(title) != "looks_ok"


def _first_sentence(body: str, max_words: int = 9) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", body or "")
    text = re.sub(r"[#`>*_]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    sent = re.split(r"(?<=[.!?])\s+", text)[0]
    words = sent.split()
    return " ".join(words[:max_words]).strip(" ,.;:-")


def _body_candidates(body: str) -> List[str]:
    cands: List[str] = []
    for m in re.findall(r"\*\*([^*]+)\*\*", body or ""):
        c = m.strip(" .,:;-")
        if c:
            cands.append(c)
    fs = _first_sentence(body)
    if fs:
        cands.append(fs)
    seen: set[str] = set()
    out: List[str] = []
    for c in cands:
        k = c.lower()
        if k in seen or not c:
            continue
        seen.add(k)
        out.append(c)
    return out


def _offline_title_from_body(
    *, current: str, body: str, chapter_title: str
) -> str:
    """Deterministic heading repair: pick a clean candidate from the body, then floor."""
    candidates = [c for c in _body_candidates(body) if classify_heading(c) == "looks_ok"]

    if candidates:
        best = _minilm_best(query=body[:400] or current, candidates=candidates)
        if best:
            return ensure_study_safe_heading(best, chapter_heading=chapter_title)
        return ensure_study_safe_heading(candidates[0], chapter_heading=chapter_title)

    return ensure_study_safe_heading(current, chapter_heading=chapter_title)


def _minilm_best(*, query: str, candidates: List[str]) -> Optional[str]:
    if not candidates:
        return None
    try:
        from src.modules.structure.final_structuring.models.mini_lm_encoder import (
            get_mini_lm_encoder,
        )

        encoder = get_mini_lm_encoder()
        q = encoder.encode([query])
        corpus = encoder.encode(candidates)
        if q is None or corpus is None:
            return None
        sims = corpus @ q[0]
        return candidates[int(sims.argmax())]
    except Exception:
        return None


def _llm_titles(
    noisy: List[Tuple[str, str]],
    *,
    chat: Callable[[str, str, int], Optional[str]],
) -> Dict[str, str]:
    """One batched call: map sid -> clean title from body. Returns {} on failure."""
    if not noisy:
        return {}
    payload = [
        {"id": sid, "body": (body or "")[:500]}
        for sid, body in noisy
    ]
    system = (
        "You title study-note sections. For each item you receive an id and the "
        "section body text. Return ONLY a JSON object mapping each id to a concise "
        "topic title (3-8 words, Title Case) that summarizes that body. The title "
        "must contain no section numbers, no statutory clause fragments, and no "
        "trailing punctuation. Do not invent facts; title only what the body says."
    )
    user = (
        "Return JSON like {\"S1\": \"Title One\", \"S2\": \"Title Two\"}.\n\n"
        f"Sections:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    raw = chat(system, user, 900)
    if not raw:
        return {}
    return _parse_title_json(raw)


def _parse_title_json(raw: str) -> Dict[str, str]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if m:
            text = m.group(1)
    if not text.lstrip().startswith("{"):
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    out: Dict[str, str] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.strip():
                out[str(k)] = v.strip()
    return out


@dataclass
class _Target:
    obj: Any  # Chapter | Section
    kind: str  # "chapter" | "section"
    key: str  # stable id for the batched LLM map
    context: str  # body text (section) or section-title list (chapter)
    parent: str  # parent chapter title for the heading floor


def _collect_noisy_targets(doc: NotesDoc) -> List[_Target]:
    targets: List[_Target] = []
    for ci, ch in enumerate(doc.chapters):
        if ch.title and _is_noisy(ch.title):
            ctx = "\n".join(s.title for s in ch.sections if not s.dropped)[:600]
            targets.append(_Target(obj=ch, kind="chapter", key=f"C{ci}", context=ctx, parent=""))
        for si, sec in enumerate(ch.sections):
            if sec.dropped or not _is_noisy(sec.title):
                continue
            key = sec.sid or f"C{ci}S{si}"
            targets.append(
                _Target(obj=sec, kind="section", key=key, context=sec.body_text(), parent=ch.title)
            )
    return targets


def repair_headings(
    doc: NotesDoc,
    report: FixReport,
    *,
    chat: Optional[Callable[[str, str, int], Optional[str]]] = None,
) -> None:
    targets = _collect_noisy_targets(doc)
    report.headings_noisy = len(targets)
    if not targets:
        return

    llm_titles: Dict[str, str] = {}
    if chat is not None:
        llm_titles = _llm_titles([(t.key, t.context) for t in targets if t.key], chat=chat)

    for t in targets:
        before = t.obj.title
        candidate = llm_titles.get(t.key, "")
        if candidate:
            new_title = ensure_study_safe_heading(candidate, chapter_heading=t.parent)
        else:
            new_title = _offline_title_from_body(
                current=t.obj.title, body=t.context, chapter_title=t.parent
            )
        new_title = (new_title or "").strip()
        if new_title and new_title != before and classify_heading(new_title) == "looks_ok":
            t.obj.title = new_title
            report.headings_repaired += 1
            report.changes.append(
                FixChange(
                    kind="heading",
                    sid=getattr(t.obj, "sid", "") or t.key,
                    before=before,
                    after=new_title,
                    detail=f"{t.kind}/{'llm' if candidate else 'offline'}",
                )
            )


# --------------------------------------------------------------------------- #
# Duplicate detection / merge
# --------------------------------------------------------------------------- #
def _dup_tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
        if w not in _DUP_STOPWORDS
    }


def _content_sim(a: str, b: str) -> float:
    ta, tb = _dup_tokens(a), _dup_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def merge_duplicates(
    doc: NotesDoc,
    report: FixReport,
    *,
    apply_merge: bool = False,
    sim_threshold: float = 0.9,
) -> None:
    """Flag (and optionally merge) near-identical adjacent sections in a chapter."""
    pairs = 0
    for ch in doc.chapters:
        secs = [s for s in ch.sections if not s.dropped and s.level == 2]
        for i in range(1, len(secs)):
            prev, cur = secs[i - 1], secs[i]
            if prev.dropped or cur.dropped:
                continue
            csim = _content_sim(prev.body_text(), cur.body_text())
            if csim < sim_threshold:
                continue
            pairs += 1
            detail = f"content_sim={csim:.2f}"
            if apply_merge:
                prev.body_lines.append("")
                prev.body_lines.extend(cur.body_lines)
                prev.merged_from.append(cur.sid)
                cur.dropped = True
                report.duplicates_merged += 1
                report.changes.append(
                    FixChange(
                        kind="merge",
                        sid=cur.sid,
                        before=cur.title,
                        after=prev.title,
                        detail=detail,
                    )
                )
            else:
                report.changes.append(
                    FixChange(
                        kind="merge",
                        sid=cur.sid,
                        before=cur.title,
                        after=prev.title,
                        detail=f"flagged ({detail})",
                    )
                )
    report.duplicate_pairs = pairs


# --------------------------------------------------------------------------- #
# Low-grounding detection
# --------------------------------------------------------------------------- #
def flag_low_grounding(
    doc: NotesDoc,
    report: FixReport,
    source_by_id: Dict[str, str],
    *,
    drop: bool = False,
) -> None:
    """Flag (opt-in drop) sections whose source was an index/contents-style list."""
    if not source_by_id:
        report.notes.append(
            "Low-grounding check skipped: no source text available (pass --log-dir)."
        )
        return
    from src.modules.generation.rewrite_fidelity import source_is_low_grounding

    for ch, sec in doc.iter_sections():
        if sec.dropped or not sec.sid:
            continue
        src = source_by_id.get(sec.sid, "")
        if not src:
            continue
        if source_is_low_grounding(src):
            sec.low_grounding = True
            report.low_grounding_flagged += 1
            if drop:
                sec.dropped = True
                report.low_grounding_dropped += 1
            report.changes.append(
                FixChange(
                    kind="low_grounding",
                    sid=sec.sid,
                    before=sec.title,
                    after="(dropped)" if drop else "(flagged)",
                    detail="index/contents-style source",
                )
            )


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def fix_notes_markdown(
    md_text: str,
    *,
    engine: str = "hybrid",
    chat: Optional[Callable[[str, str, int], Optional[str]]] = None,
    heading_model: str = "",
    source_by_id: Optional[Dict[str, str]] = None,
    merge_duplicates_apply: bool = False,
    drop_low_grounding: bool = False,
) -> Tuple[str, FixReport]:
    """Apply structural fixes to notes Markdown. Returns (new_md, report).

    `chat` is a `(system, user, max_tokens) -> Optional[str]` callable. When None
    (offline / engine="minilm"), heading repair uses the MiniLM-from-body floor.
    """
    doc = parse_notes_md(md_text)
    report = FixReport(
        engine=engine,
        heading_model=heading_model or ("offline" if chat is None else "llm"),
        embedding_model=_MINILM_MODEL,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    report.sections_total = sum(len(ch.sections) for ch in doc.chapters)

    flag_low_grounding(doc, report, source_by_id or {}, drop=drop_low_grounding)
    repair_headings(doc, report, chat=chat)
    merge_duplicates(doc, report, apply_merge=merge_duplicates_apply)

    return render_notes_md(doc), report
