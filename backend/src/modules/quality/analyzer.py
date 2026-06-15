"""Deterministic notes quality audit — PDF, hierarchy, MD/DOCX."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.modules.quality.heuristics import (
    classify_heading,
    compute_verdict_scores,
    detect_syllabus_noise_in_body,
    find_parent_mirror_chapters,
    norm as _norm,
)
from src.modules.quality.heading_acceptance import (
    evaluate_heading_acceptance,
    format_acceptance_report,
)
from src.modules.quality.models import BookAuditResult, Report

from src.modules.export.docx_notes_exporter import (  # noqa: E402
    parse_section_bodies_from_markdown,
    resolve_rewritten_map,
)
from src.modules.generation.rewrite_validation import strip_section_id_tags  # noqa: E402
from src.modules.generation.rewrite_validation import is_weak_section_heading  # noqa: E402
from src.modules.structure.dropped_heading_registry import (  # noqa: E402
    is_generic_study_title,
    is_noisy_fragment_heading,
    is_sentence_like_title,
    is_syllabus_heading,
)

def dynamic_sample_section_ids(section_ids: Sequence[str]) -> List[Tuple[str, str]]:
    """Pick first / 25% / 50% / 75% / last section IDs for fidelity sampling."""
    ids = [s for s in section_ids if s]
    if not ids:
        return []
    n = len(ids)
    indices = sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1})
    labels = ["first", "25%", "50%", "75%", "last"]
    out: List[Tuple[str, str]] = []
    for idx, label in zip(indices, labels[: len(indices)]):
        out.append((ids[idx], label))
    return out


def _pdf_match_source_grounding_enabled() -> bool:
    """When on, a clean (looks_ok) title not found verbatim in the PDF is accepted
    if its content words are covered by the section source — rewards intentionally
    cleaned/derived titles instead of penalizing them as PDF-match failures."""
    return os.environ.get("NOTES_QUALITY_PDF_MATCH_SOURCE_GROUNDING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


_TITLE_STOPWORDS = frozenset(
    {"the", "and", "for", "with", "section", "article", "under", "this", "that", "from", "into"}
)


def _title_grounded_in_source(title: str, source_preview: str, *, min_cover: float = 0.6) -> bool:
    """True when most content words of the title appear in the section source."""
    title_tokens = {
        w for w in re.findall(r"[a-zA-Z]{4,}", (title or "").lower()) if w not in _TITLE_STOPWORDS
    }
    if not title_tokens:
        return False
    source_tokens = set(re.findall(r"[a-zA-Z]{4,}", (source_preview or "").lower()))
    if not source_tokens:
        return False
    covered = len(title_tokens & source_tokens) / len(title_tokens)
    return covered >= min_cover


def pdf_match_heading(
    title: str,
    page_hint: Optional[int],
    page_text: Sequence[str],
    *,
    raw_title: str = "",
    source_preview: str = "",
) -> Tuple[str, Optional[int]]:
    """Check whether a heading appears in PDF page text."""
    from src.modules.structure.final_structuring.heading_cleanup import canonical_heading_for_match

    t = (title or "").strip()
    if not t:
        return "empty", None

    def _search_pages(needle: str) -> List[int]:
        needle = (needle or "").strip()
        if not needle or len(needle) < 4:
            return []
        low = needle.lower()
        pages: List[int] = []
        if isinstance(page_hint, int) and page_hint > 0:
            for pg in range(max(1, page_hint - 1), min(len(page_text), page_hint + 2) + 1):
                if low in page_text[pg - 1].lower():
                    pages.append(pg)
        if not pages:
            for pg, text in enumerate(page_text, start=1):
                if low in text.lower():
                    pages.append(pg)
        return pages

    candidates = [t]
    canon = canonical_heading_for_match(t)
    if canon and canon.lower() != t.lower():
        candidates.append(canon)
    raw = (raw_title or "").strip()
    if raw and raw.lower() not in {c.lower() for c in candidates}:
        candidates.append(raw)
        raw_canon = canonical_heading_for_match(raw)
        if raw_canon:
            candidates.append(raw_canon)

    pages: List[int] = []
    for candidate in candidates:
        pages = _search_pages(candidate)
        if pages:
            t = candidate
            break

    if not pages:
        for m in re.finditer(r"(?:section|art\.?|article)\s*\.?\s*(\d+[A-Za-z]?)", t, re.I):
            anchor = f"section {m.group(1)}"
            pages = _search_pages(anchor)
            if pages:
                break
        if not pages and raw:
            for m in re.finditer(r"(?:section|art\.?|article)\s*\.?\s*(\d+[A-Za-z]?)", raw, re.I):
                anchor = f"section {m.group(1)}"
                pages = _search_pages(anchor)
                if pages:
                    break
        if not pages:
            short = " ".join(t.split()[:6])
            if len(short) >= 12:
                pages = _search_pages(short)

    if not pages and source_preview.strip():
        preview_words = [w for w in re.findall(r"[a-zA-Z]{5,}", source_preview.lower())[:8]]
        if len(preview_words) >= 3:
            anchor = " ".join(preview_words[:4])
            if len(anchor) >= 12:
                pages = _search_pages(anchor)

    if not pages:
        if (
            _pdf_match_source_grounding_enabled()
            and classify_heading((title or "").strip()) == "looks_ok"
            and _title_grounded_in_source((title or "").strip(), source_preview)
        ):
            return "grounded_in_source", None
        return "not_in_pdf", None
    if t != (title or "").strip() and classify_heading(title) == "looks_ok":
        return "in_pdf_renamed", pages[0]
    if classify_heading(t) in {"prose_not_topic", "question_prose", "too_long"}:
        return "in_pdf_as_body", pages[0]
    return "in_pdf", pages[0]


def aggregate_batch_summary(results: Sequence[BookAuditResult]) -> Dict[str, Any]:
    """Build cross-book summary payload for JSON export."""
    return {
        "book_count": len(results),
        "books": [r.to_summary_dict() for r in results],
        "overall": {
            "pass": sum(1 for r in results if r.verdict_scores.get("overall") == "PASS"),
            "ok": sum(1 for r in results if r.verdict_scores.get("overall") == "OK"),
            "warn": sum(1 for r in results if r.verdict_scores.get("overall") == "WARN"),
        },
    }


def _load_json(path: Path) -> Any:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
        if isinstance(items, dict):
            return items
        return items
    return data


def _pdf_toc(pdf_path: Path) -> List[Tuple[int, str, int]]:
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        toc = doc.get_toc(simple=False) or []
        return [(int(lvl), str(title).strip(), int(page)) for lvl, title, page in toc]
    finally:
        doc.close()


def _pdf_stats(pdf_path: Path) -> Dict[str, Any]:
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        pages = doc.page_count
        toc = doc.get_toc(simple=False) or []
        return {"pages": pages, "outline_entries": len(toc)}
    finally:
        doc.close()


def _pdf_page_text(pdf_path: Path) -> List[str]:
    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        return [doc.load_page(i).get_text("text") for i in range(doc.page_count)]
    finally:
        doc.close()


def _parse_md_structure(md_text: str) -> Tuple[List[str], List[str], Dict[str, str]]:
    chapters: List[str] = []
    sections: List[str] = []
    bodies = parse_section_bodies_from_markdown(md_text)
    in_body = False
    for line in md_text.splitlines():
        if line.startswith("# Table of Contents"):
            in_body = True
            continue
        if not in_body:
            continue
        if line.strip().startswith("```{=openxml}"):
            continue
        if line.startswith("# ") and not line.startswith("## "):
            chapters.append(line[2:].strip())
        elif line.startswith("## ") and not line.startswith("### "):
            h = strip_section_id_tags(line[3:]).strip()
            if h and not re.match(r"^\d+\.\s+", h):
                sections.append(h)
    return chapters, sections, bodies


def _docx_structure(docx_path: Path) -> Tuple[List[str], List[str]]:
    from docx import Document

    doc = Document(str(docx_path))
    chapters: List[str] = []
    sections: List[str] = []
    for p in doc.paragraphs:
        style = (p.style.name or "").lower()
        text = (p.text or "").strip()
        if not text:
            continue
        if "heading 1" in style:
            chapters.append(text)
        elif "heading 2" in style:
            sections.append(text)
    return chapters, sections


def _keyword_overlap(source: str, notes: str) -> float:
    def tokens(s: str) -> set[str]:
        return {
            w
            for w in re.findall(r"[a-zA-Z]{4,}", s.lower())
            if w not in {"that", "this", "with", "from", "have", "been", "will", "shall", "article", "articles"}
        }

    a, b = tokens(source), tokens(notes)
    if not a:
        return 1.0 if notes.strip() else 0.0
    return len(a & b) / len(a)


def _heading_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _note_tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
        if w
        not in {
            "that",
            "this",
            "with",
            "from",
            "have",
            "been",
            "will",
            "shall",
            "article",
            "articles",
            "section",
            "points",
            "quick",
            "revision",
        }
    }


def _content_sim(a: str, b: str) -> float:
    ta, tb = _note_tokens(a), _note_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _find_repeated_topics(
    flat_sections: Sequence[Tuple[str, str, str]],
    *,
    heading_threshold: float = 0.82,
    content_threshold: float = 0.55,
    max_pairs: int = 20,
) -> List[Tuple[str, str, str, float, str]]:
    pairs: List[Tuple[str, str, str, float, str]] = []
    n = len(flat_sections)
    for i in range(n):
        sid_a, head_a, body_a = flat_sections[i]
        for j in range(i + 1, n):
            sid_b, head_b, body_b = flat_sections[j]
            hsim = _heading_sim(head_a, head_b)
            csim = _content_sim(body_a, body_b)
            if hsim >= heading_threshold:
                pairs.append((sid_a, sid_b, "similar headings", hsim, f"{head_a[:40]} ~ {head_b[:40]}"))
            elif csim >= content_threshold and len(body_a) > 80 and len(body_b) > 80:
                pairs.append((sid_a, sid_b, "similar note content", csim, f"{head_a[:35]} vs {head_b[:35]}"))
    pairs.sort(key=lambda x: -x[3])
    return pairs[:max_pairs]


def _weak_heading_flags(heading: str) -> List[str]:
    flags: List[str] = []
    h = (heading or "").strip()
    if not h:
        flags.append("empty")
    if len(h) < 4:
        flags.append("too_short")
    if re.match(r"^\(\s*(?:art|ii|iii|iv)\b", h, re.I):
        flags.append("bare_marker")
    if re.match(r"^\d+\.\s*$", h):
        flags.append("number_only")
    if re.match(r"^part\s+[IVXLC\d]+\s*$", h, re.I):
        flags.append("generic_part")
    if re.match(r"^chapter\s+\d+\s*$", h, re.I):
        flags.append("bare_chapter")
    return flags


def build_report(
    *,
    label: str = "",
    pdf_path: Path,
    log_dir: Path,
    md_path: Path,
    docx_path: Optional[Path],
) -> Tuple[Report, BookAuditResult]:
    r = Report()

    r.add("=" * 72)
    r.add(f"NOTES QUALITY REPORT — {label or pdf_path.stem}")
    r.add("=" * 72)
    r.add(f"PDF:   {pdf_path}")
    r.add(f"Notes: {md_path}")
    if docx_path:
        r.add(f"DOCX:  {docx_path}")
    r.add(f"Logs:  {log_dir}")
    r.add("")

    from src.modules.pipeline.stage_registry import (
        STAGE_PARTITION_SECTIONS,
        STAGE_PARTITION_TREE,
        require_artifact,
        resolve_chapter_hierarchy_artifact,
    )

    h15a = _load_json(require_artifact(log_dir, STAGE_PARTITION_TREE))
    h15d = _load_json(require_artifact(log_dir, STAGE_PARTITION_SECTIONS))
    hierarchy_path = resolve_chapter_hierarchy_artifact(log_dir)
    hierarchy_data = _load_json(hierarchy_path) if hierarchy_path else {}
    if hierarchy_path:
        from src.modules.pipeline.stage_registry import STAGE_LOG_FILES

        _file_to_key = {v: k for k, v in STAGE_LOG_FILES.items()}
        hierarchy_stage = _file_to_key.get(hierarchy_path.name, hierarchy_path.name)
    else:
        hierarchy_stage = "group_chapters"
    headings09 = _load_json(require_artifact(log_dir, "final_headings"))

    sections15d = h15d.get("sections") or []
    chapters15e = hierarchy_data.get("chapters") or []
    meta15d = h15d.get("meta") or {}
    meta15e = hierarchy_data.get("meta") or {}
    book_title = str(hierarchy_data.get("book_title") or meta15e.get("book_title") or "")

    r.add("1. INGESTION PIPELINE — what it produced")
    r.add("-" * 72)
    r.add(f"  Raw headings detected (stage 09):     {len(headings09)}")
    r.add(f"  Headings with hierarchy (15a):        {len(h15a)}")
    r.add(f"  Headings dropped in 15d consolidation: {meta15d.get('dropped_heading_count', '?')}")
    r.add(f"  Rewrite sections (15d):               {meta15d.get('total_sections', len(sections15d))}")
    r.add(f"  Subheadings preserved (15d):            {meta15d.get('total_subheadings', '?')}")
    r.add(f"  Chapters after {hierarchy_stage} grouping:          {meta15e.get('total_chapters', len(chapters15e))}")
    r.add(
        f"  {hierarchy_stage} assignment method:                "
        f"{meta15e.get('heading_cleanup_method') or meta15e.get('assignment_method', '?')}"
    )
    r.add(f"  Weak section headings after 15f:      {meta15e.get('weak_section_headings_after', '?')}")
    r.add(f"  Duplicate chapter names after 15f:    {meta15e.get('duplicate_chapter_names_after', '?')}")
    if meta15e.get("chapter_placement_method"):
        r.add(f"  15h placement method:                 {meta15e.get('chapter_placement_method')}")
        r.add(f"  15h chapter splits:                   {meta15e.get('chapter_placement_splits', 0)}")
        r.add(f"  15h section reassignments:            {meta15e.get('chapter_placement_reassignments', 0)}")
        r.add(f"  15h chapter renames:                  {meta15e.get('chapter_placement_chapter_renames', 0)}")
        r.add(f"  15h heading cleanups:                 {meta15e.get('chapter_placement_heading_cleanups', 0)}")
    if meta15e.get("hierarchy_openai_regrouped") is not None:
        r.add(f"  15j OpenAI regrouped:                 {meta15e.get('hierarchy_openai_regrouped')}")
        r.add(f"  15j coalesced chapter starts:         {meta15e.get('hierarchy_openai_coalesced_starts', 0)}")
        r.add(f"  15j merged chapters:                  {meta15e.get('hierarchy_openai_merged_chapters', 0)}")
    from src.modules.ingestion.document_profile import load_document_profile

    profile = load_document_profile(log_dir)
    if profile is not None:
        r.add("  Document profile (measured):")
        r.add(f"    heading_density:            {profile.heading_density}")
        r.add(f"    median_section_body_chars:    {profile.median_section_body_chars}")
        r.add(f"    short_section_ratio:          {profile.short_section_ratio}")
        r.add(f"    rewrite_overlap_chars:        {profile.rewrite_overlap_chars}")
        r.add(f"    min_section_body_chars:       {profile.min_section_body_chars}")
        r.add(f"    require_strict_heading_match: {profile.require_strict_heading_match}")
    rewrite_meta = meta15e.get("rewrite_auto_retry_summary") or {}
    fidelity_meta = meta15e.get("rewrite_fidelity_summary") or {}
    if rewrite_meta or fidelity_meta:
        r.add("  Rewrite quality summaries:")
        if rewrite_meta:
            r.add(f"    auto_retry missing_before/after: {rewrite_meta.get('missing_before', '—')} / {rewrite_meta.get('missing_after', '—')}")
            if "coverage_ratio" in rewrite_meta:
                r.add(f"    auto_retry coverage_ratio:       {rewrite_meta.get('coverage_ratio')}")
        if fidelity_meta:
            r.add(f"    fidelity drift_regenerated:      {fidelity_meta.get('drift_regenerated', 0)}")
            r.add(f"    low_grounding_sections:          {fidelity_meta.get('low_grounding_sections', 0)}")
    r.add("")

    pdf_info = _pdf_stats(pdf_path)
    pdf_toc = _pdf_toc(pdf_path)
    page_text = _pdf_page_text(pdf_path)

    r.add("2. ORIGINAL PDF")
    r.add("-" * 72)
    r.add(f"  Total pages:           {pdf_info['pages']}")
    r.add(f"  Embedded PDF outline:  {pdf_info['outline_entries']} entries")
    if pdf_toc:
        r.add("  First outline entries:")
        for lvl, title, page in pdf_toc[:12]:
            r.add(f"    {'  ' * (lvl - 1)}p.{page:3d}  {title[:70]}")
    else:
        r.add("  (No embedded PDF bookmark outline — comparison uses ingestion headings + page order.)")
    r.add("")

    md_text = md_path.read_text(encoding="utf-8")
    md_chapters, md_sections, md_bodies = _parse_md_structure(md_text)
    from src.modules.generation.rewrite_validation import (
        default_rewritten_map_path,
        load_rewritten_map,
    )

    sidecar_path = default_rewritten_map_path(md_path)
    if sidecar_path.exists():
        mapped = load_rewritten_map(sidecar_path)
    else:
        mapped = resolve_rewritten_map(hierarchy_data, md_text=md_text)

    # Reconstruct the exact source text the rewrite consumed (full span, not the
    # truncated preview) so fidelity numbers are honest and attributable.
    full_source_by_id: Dict[str, str] = {}
    try:
        from src.modules.generation.toc_sections import (
            build_source_text_by_id,
            line_text_map_from_records,
        )

        layout_records = _load_json(require_artifact(log_dir, "layout_lines"))
        if isinstance(layout_records, dict):
            layout_records = layout_records.get("items") or layout_records.get("lines") or []
        line_text_by_id = line_text_map_from_records(layout_records or [])
        if line_text_by_id:
            full_source_by_id = build_source_text_by_id(hierarchy_data, line_text_by_id)
    except Exception:
        full_source_by_id = {}

    def _section_source(sid: str, src: Dict[str, Any]) -> str:
        full = full_source_by_id.get(sid, "")
        if full and full.strip():
            return full
        return str((src.get("fragment") or {}).get("preview") or "")
    mermaid_count = len(re.findall(r"```mermaid", md_text, re.I))
    has_key_points = "### key points" in md_text.lower()
    has_quick_revision = "### quick revision" in md_text.lower()

    if docx_path and docx_path.exists():
        docx_chapters, docx_sections = _docx_structure(docx_path)
    else:
        docx_chapters, docx_sections = [], []

    docx_ch_delta = len(docx_chapters) - len(md_chapters) if docx_chapters else 0
    docx_sec_delta = len(docx_sections) - len(md_sections) if docx_sections else 0

    r.add("3. GENERATED NOTES")
    r.add("-" * 72)
    r.add(f"  Markdown chapters (#):     {len(md_chapters)}")
    r.add(f"  Markdown sections (##):    {len(md_sections)}")
    r.add(f"  Sections with body text:   {len(md_bodies)}")
    total_secs = int(meta15e.get("total_sections") or len(flat15e_from_chapters(chapters15e)))
    r.add(f"  Mapped to hierarchy IDs:   {len(mapped)} / {total_secs}")
    if docx_path:
        r.add(f"  DOCX H1 chapters:          {len(docx_chapters)}")
        r.add(f"  DOCX H2 sections:          {len(docx_sections)}")
    r.add(f"  Exam Key Points blocks:      {has_key_points}")
    r.add(f"  Quick Revision blocks:       {has_quick_revision}")
    r.add(f"  Mermaid diagrams:            {mermaid_count}")
    r.add("")

    r.add("4. DOCX EXPORT PARITY")
    r.add("-" * 72)
    if docx_path and docx_path.exists():
        r.add(f"  MD vs DOCX chapter delta:  {docx_ch_delta:+d}")
        r.add(f"  MD vs DOCX section delta:  {docx_sec_delta:+d}")
        if docx_ch_delta != 0 or abs(docx_sec_delta) > 2:
            r.add("  WARN: MD and DOCX heading counts diverge — check export.")
        else:
            r.add("  PASS: MD and DOCX heading counts align.")
    else:
        r.add("  (No DOCX provided — skipped)")
    r.add("")

    flat15e = flat15e_from_chapters(chapters15e)
    pages15e = [p for _, _, p in flat15e]
    inversions = sum(1 for i in range(1, len(pages15e)) if pages15e[i] < pages15e[i - 1])

    r.add("5. TOPIC SEQUENCE (page order vs notes order)")
    r.add("-" * 72)
    r.add(f"  Sections in flat order:    {len(flat15e)}")
    r.add(f"  Page-order inversions:     {inversions} (0 = strictly follows PDF page flow)")
    if inversions:
        r.add("  Sample out-of-order jumps:")
        shown = 0
        for i in range(1, len(flat15e)):
            prev_p = flat15e[i - 1][2]
            cur_p = flat15e[i][2]
            if cur_p < prev_p and shown < 8:
                r.add(f"    p.{prev_p} '{flat15e[i-1][1][:45]}' -> p.{cur_p} '{flat15e[i][1][:45]}'")
                shown += 1
    r.add("")

    ch_names = [str(c.get("heading") or "") for c in chapters15e]
    dup_ch = [n for n, c in Counter(ch_names).items() if c > 1]
    r.add("6. HIERARCHY QUALITY")
    r.add("-" * 72)
    r.add(f"  Unique chapter titles:     {len(set(ch_names))} / {len(ch_names)}")
    if dup_ch:
        r.add(f"  Duplicate chapter names:   {len(dup_ch)} — {dup_ch[:8]}")
    else:
        r.add("  Duplicate chapter names:   none (good)")
    r.add("")
    r.add("  Chapter flow:")
    for i, ch in enumerate(chapters15e[:15], 1):
        sec_count = len(ch.get("sections") or [])
        pg = ch.get("page_start", "?")
        r.add(f"    {i:2d}. p.{pg!s:>3}  {ch.get('heading', '')[:55]:55s}  ({sec_count} sections)")
    r.add("")

    missing_ids: List[str] = []
    for ch in chapters15e:
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            if sid and sid not in mapped:
                missing_ids.append(f"{sid}: {sec.get('heading', '')[:50]}")
    r.add("7. COVERAGE GAPS")
    r.add("-" * 72)
    r.add(f"  Unmapped sections (no rewrite body): {len(missing_ids)}")
    rewrite_meta = meta15e.get("rewrite_auto_retry_summary") or {}
    fidelity_meta = meta15e.get("rewrite_fidelity_summary") or {}
    if rewrite_meta:
        r.add(
            f"  Inline auto-retry: missing {rewrite_meta.get('missing_before', '—')} → "
            f"{rewrite_meta.get('missing_after', '—')} (coverage {rewrite_meta.get('coverage_ratio', '—')})"
        )
    if fidelity_meta:
        r.add(f"  Fidelity regenerations (drift):      {fidelity_meta.get('drift_regenerated', 0)}")
    for line in missing_ids[:15]:
        r.add(f"    - {line}")
    if len(missing_ids) > 15:
        r.add(f"    ... and {len(missing_ids) - 15} more")
    r.add("")

    sec_by_id: Dict[str, Dict[str, Any]] = {}
    for sec in sections15d:
        sec_by_id[str(sec.get("section_id"))] = sec

    section_ids_ordered = [sid for _, sid, _ in flat15e_from_chapters_with_ids(chapters15e)]
    samples = dynamic_sample_section_ids(section_ids_ordered)

    r.add("8. CONTENT FIDELITY (source fragment vs rewritten notes)")
    r.add("-" * 72)
    for sid, sample_label in samples:
        src = sec_by_id.get(sid)
        if not src:
            for ch in chapters15e:
                for sec in ch.get("sections") or []:
                    if str(sec.get("section_id")) == sid:
                        src = sec
                        break
        if not src:
            continue
        preview = str((src.get("fragment") or {}).get("preview") or "")
        heading = str(src.get("heading") or "")
        body = mapped.get(sid) or md_bodies.get(heading, "")
        if not body:
            for k, v in md_bodies.items():
                if _heading_sim(k, heading) > 0.85:
                    body = v
                    break
        source = _section_source(sid, src)
        ov = _keyword_overlap(source, body) if source else (1.0 if body else 0.0)
        r.add(f"  [{sid}] sample={sample_label}")
        r.add(f"    Heading:        {heading[:80]}")
        r.add(f"    Source preview: {(source or preview)[:120]!r}")
        r.add(f"    Notes length:   {len(body)} chars | keyword overlap: {ov:.0%}")
        if body:
            r.add(f"    Notes sample:   {body.splitlines()[0][:100]}")
        r.add("")

    from src.modules.generation.rewrite_fidelity import source_is_low_grounding

    all_ov: List[float] = []
    grounded_ov: List[float] = []
    short_notes = 0
    low_grounding = 0
    for ch in chapters15e:
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            body = mapped.get(sid, "")
            if not body:
                continue
            if len(body) < 120:
                short_notes += 1
            src = sec_by_id.get(sid) or sec
            source = _section_source(sid, src)
            if not source:
                continue
            is_low = source_is_low_grounding(source)
            if is_low:
                low_grounding += 1
            ov = _keyword_overlap(source, body)
            all_ov.append(ov)
            if not is_low:
                grounded_ov.append(ov)

    avg_ov = sum(all_ov) / len(all_ov) if all_ov else 0.0
    avg_grounded = sum(grounded_ov) / len(grounded_ov) if grounded_ov else 0.0
    # Verdict uses overlap on sections that actually have rewritable source;
    # index/contents-style sources carry no body text to ground on.
    avg_for_verdict = avg_grounded if grounded_ov else avg_ov
    r.add(f"  Avg keyword overlap (all mapped sections):          {avg_ov:.0%} across {len(all_ov)} sections")
    r.add(f"  Avg keyword overlap (sections with real source):    {avg_grounded:.0%} across {len(grounded_ov)} sections")
    r.add(f"  Low-grounding sources (index/contents-style/thin):  {low_grounding}")
    r.add(f"  Very short note bodies (<120 chars):                {short_notes}")
    r.add("")

    weak_sections: List[Tuple[str, str, List[str]]] = []
    title_noise: List[Tuple[str, str, str]] = []
    for ch in chapters15e:
        ch_heading = str(ch.get("heading") or "")
        ch_cls = classify_heading(ch_heading)
        if ch_cls not in {"looks_ok"} or is_generic_study_title(ch_heading, book_title=book_title):
            title_noise.append(("chapter", ch_heading, ch_cls))
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            heading = str(sec.get("heading") or "")
            flags = _weak_heading_flags(heading)
            if flags:
                weak_sections.append((sid, heading, flags))
            cls = classify_heading(heading)
            if cls not in {"looks_ok"}:
                title_noise.append((sid, heading, cls))
            elif is_generic_study_title(heading, book_title=book_title):
                title_noise.append((sid, heading, "generic_study"))

    r.add("9. TOPIC / CHAPTER NAMING QUALITY")
    r.add("-" * 72)
    r.add(f"  Sections with weak/generic headings: {len(weak_sections)}")
    for sid, heading, flags in weak_sections[:15]:
        r.add(f"    [{sid}] {heading[:55]:55s}  flags={','.join(flags)}")
    if len(weak_sections) > 15:
        r.add(f"    ... and {len(weak_sections) - 15} more")
    r.add(f"  Title noise (MODULE/syllabus/fragment): {len(title_noise)}")
    for kind, heading, cls in title_noise[:15]:
        r.add(f"    [{kind}] {heading[:60]:60s}  class={cls}")
    if len(title_noise) > 15:
        r.add(f"    ... and {len(title_noise) - 15} more")
    r.add("")

    if len(title_noise) > 15:
        r.add(f"    ... and {len(title_noise) - 15} more")
    r.add("")

    syllabus_hits: List[Tuple[str, str, List[str]]] = []
    for ch in chapters15e:
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            body = mapped.get(sid, "")
            if not body:
                continue
            flags = detect_syllabus_noise_in_body(body)
            if flags:
                syllabus_hits.append((sid, str(sec.get("heading") or ""), flags))

    r.add("10. SYLLABUS / ADMIN NOISE IN NOTE BODIES")
    r.add("-" * 72)
    r.add(f"  Sections with syllabus/admin noise: {len(syllabus_hits)}")
    for sid, heading, flags in syllabus_hits[:15]:
        r.add(f"    [{sid}] {heading[:50]:50s}  flags={','.join(flags)}")
    if len(syllabus_hits) > 15:
        r.add(f"    ... and {len(syllabus_hits) - 15} more")
    r.add("")

    pdf_rows: List[Dict[str, Any]] = []
    from src.modules.structure.final_structuring.heading_title_engine import resolve_section_display_heading

    for ch in chapters15e:
        ch_title = str(ch.get("heading") or "")
        for sec in ch.get("sections") or []:
            raw_heading = str(sec.get("heading") or "")
            display_heading = resolve_section_display_heading(
                sec,
                chapter_heading=ch_title,
                use_transformers=False,
            )
            src = sec_by_id.get(str(sec.get("section_id") or "")) or sec
            preview = str((src.get("fragment") or {}).get("preview") or "")
            pdf_rows.append(
                {
                    "section_id": str(sec.get("section_id") or ""),
                    "heading": display_heading or raw_heading,
                    "raw_heading": raw_heading,
                    "source_preview": preview,
                    "page": sec.get("page_number"),
                }
            )
    class_counts = Counter(classify_heading(row["heading"]) for row in pdf_rows)
    pdf_failures: List[str] = []
    strong_sections: List[str] = []
    grounded_titles = 0
    for row in pdf_rows:
        status, pg = pdf_match_heading(
            row["heading"],
            row.get("page"),
            page_text,
            raw_title=str(row.get("raw_heading") or ""),
            source_preview=str(row.get("source_preview") or ""),
        )
        if status in {"not_in_pdf", "in_pdf_as_body"}:
            pdf_failures.append(f"{row['section_id']}: {row['heading'][:50]} ({status})")
        if status == "grounded_in_source":
            grounded_titles += 1
        if classify_heading(row["heading"]) == "looks_ok" and status in {
            "in_pdf",
            "in_pdf_renamed",
            "grounded_in_source",
        }:
            strong_sections.append(f"{row['section_id']} p.{row.get('page')} | {row['heading'][:70]}")

    r.add("11. PDF HEADING VERIFICATION")
    r.add("-" * 72)
    r.add(f"  Heading class distribution: {dict(class_counts)}")
    if grounded_titles:
        r.add(f"  Clean titles grounded in source (not verbatim in PDF): {grounded_titles}")
    r.add(f"  Headings not verified in PDF: {len(pdf_failures)}")
    for line in pdf_failures[:12]:
        r.add(f"    - {line}")
    if len(pdf_failures) > 12:
        r.add(f"    ... and {len(pdf_failures) - 12} more")
    r.add("")

    flat_for_dup: List[Tuple[str, str, str]] = []
    for ch in chapters15e:
        for sec in ch.get("sections") or []:
            sid = str(sec.get("section_id") or "")
            heading = str(sec.get("heading") or "")
            body = mapped.get(sid, "")
            if body:
                flat_for_dup.append((sid, heading, body))
    repeated = _find_repeated_topics(flat_for_dup)

    r.add("12. REPEATED TOPIC COVERAGE")
    r.add("-" * 72)
    r.add(f"  Sections with rewritten notes: {len(flat_for_dup)}")
    r.add(f"  Likely duplicate/repeated pairs: {len(repeated)}")
    if repeated:
        r.add("  Top pairs (review if same topic taught twice):")
        for sid_a, sid_b, reason, score, pair_label in repeated[:12]:
            r.add(f"    {sid_a} vs {sid_b}  ({reason}, {score:.0%})  {pair_label}")
    else:
        r.add("  No strong heading/content duplicates detected.")
    r.add("")

    parent_mirrors = find_parent_mirror_chapters(chapters15e)
    r.add("13. PARENT TOPIC AS FIRST SUBTOPIC")
    r.add("-" * 72)
    r.add(f"  Chapters where title mirrors first section: {len(parent_mirrors)}")
    for sample in parent_mirrors[:12]:
        r.add(f"    - {sample}")
    if len(parent_mirrors) > 12:
        r.add(f"    ... and {len(parent_mirrors) - 12} more")
    r.add("")

    # Sentence length / prose density is intentionally NOT audited — it is not a
    # quality problem for these notes (removed per product decision).

    heading_acceptance = evaluate_heading_acceptance(
        chapters15e=chapters15e,
        md_text=md_text,
        docx_chapters=docx_chapters if docx_chapters else None,
        docx_sections=docx_sections if docx_sections else None,
        mapped_count=len(mapped),
        total_sections=total_secs,
        short_notes=short_notes,
    )
    r.add("15. HEADING ACCEPTANCE CRITERIA (pipeline heading rules)")
    r.add("-" * 72)
    for line in format_acceptance_report(heading_acceptance):
        r.add(line)
    r.add("")

    line_audit_fail = 0
    line_audit_warn = 0
    line_audit_book = None
    line_audit_samples: List[str] = []

    from src.modules.quality.line_audit import (
        audit_all_sections,
        format_line_audit_report,
        line_audit_enabled,
    )

    if line_audit_enabled():
        audit_rows: List[Dict[str, Any]] = []
        source_by_id: Dict[str, str] = {}
        for ch in chapters15e:
            for sec in ch.get("sections") or []:
                sid = str(sec.get("section_id") or "")
                audit_rows.append(
                    {
                        "section_id": sid,
                        "heading": str(sec.get("heading") or ""),
                    }
                )
                src = sec_by_id.get(sid) or sec
                source_by_id[sid] = _section_source(sid, src)

        line_audit_book = audit_all_sections(
            audit_rows,
            bodies_by_id=mapped,
            source_by_id=source_by_id,
        )
        line_audit_fail = line_audit_book.sections_fail
        line_audit_warn = line_audit_book.sections_warn

        r.add("16. LINE-BY-LINE CONTENT AUDIT")
        r.add("-" * 72)
        for line in format_line_audit_report(line_audit_book):
            r.add(line)
        r.add("")

        for sec in line_audit_book.worst_sections(6):
            line_audit_samples.append(
                f"[{sec.section_id}] {sec.verdict} {sec.issue_count} issues — {sec.heading[:50]}"
            )

    verdict_scores = compute_verdict_scores(
        mapped_count=len(mapped),
        total_sections=total_secs,
        inversions=inversions,
        dup_chapter_count=len(dup_ch),
        avg_overlap=avg_for_verdict,
        repeated_pairs=len(repeated),
        weak_heading_count=len(weak_sections),
        title_noise_count=len(title_noise),
        syllabus_body_hits=len(syllabus_hits),
        pdf_match_failures=len(pdf_failures),
        parent_mirror_count=len(parent_mirrors),
        line_audit_fail_sections=line_audit_fail,
        line_audit_warn_sections=line_audit_warn,
        heading_acceptance_failed=len(heading_acceptance.failed_criteria),
        heading_export_violations=heading_acceptance.export_violation_count,
        short_notes=short_notes,
    )

    r.add("17. OVERALL VERDICT")
    r.add("-" * 72)
    for dim, score in verdict_scores.items():
        if dim == "overall":
            continue
        r.add(f"  {score:4s}  {dim}")
    r.add(f"  ----")
    r.add(f"  {verdict_scores.get('overall', 'WARN'):4s}  OVERALL")
    r.add("")
    r.add("  Summary:")
    r.add(f"  - PDF has {pdf_info['pages']} pages; pipeline produced {total_secs} rewrite sections")
    r.add(f"    in {len(chapters15e)} chapters ({hierarchy_stage} hierarchy).")
    r.add(f"  - Notes cover {len(mapped)}/{total_secs} sections ({100*len(mapped)/max(total_secs,1):.0f}%);")
    r.add(f"    avg source keyword overlap {avg_grounded:.0%} on grounded sections "
          f"({low_grounding} low-grounding sources excluded).")
    r.add(f"  - Naming: {len(weak_sections)} weak headings; {len(title_noise)} title noise flags.")
    r.add(f"  - Syllabus in bodies: {len(syllabus_hits)} sections.")
    r.add(f"  - PDF match failures: {len(pdf_failures)}; repetition pairs: {len(repeated)}.")
    r.add(f"  - Parent-as-subtopic mirrors: {len(parent_mirrors)}.")
    r.add(
        f"  - Heading acceptance: {heading_acceptance.verdict()} "
        f"({heading_acceptance.export_violation_count} export violations; "
        f"{len(heading_acceptance.failed_criteria)} criteria failed)."
    )
    if line_audit_book is not None:
        r.add(
            f"  - Line audit: {line_audit_book.total_issues} issues across {line_audit_book.total_lines} lines "
            f"({line_audit_fail} FAIL / {line_audit_warn} WARN sections)."
        )
    r.add("")

    top_issues: List[str] = []
    for v in heading_acceptance.violations[:3]:
        top_issues.append(
            f"heading AC-{v.criterion_id}: [{v.source}] {v.heading[:50]} ({v.heading_class})"
        )
    for sid, heading, flags in syllabus_hits[:2]:
        top_issues.append(f"syllabus noise [{sid}] {heading[:40]} ({','.join(flags)})")
    for kind, heading, cls in title_noise[:3]:
        top_issues.append(f"title noise [{kind}] {heading[:40]} ({cls})")
    for line in pdf_failures[:2]:
        top_issues.append(f"pdf match: {line[:70]}")
    for sid_a, sid_b, reason, score, _ in repeated[:2]:
        top_issues.append(f"duplicate: {sid_a} vs {sid_b} ({reason} {score:.0%})")
    for sample in parent_mirrors[:2]:
        top_issues.append(f"parent mirror: {sample[:70]}")
    for sample in line_audit_samples[:3]:
        top_issues.append(f"line audit: {sample[:70]}")

    result = BookAuditResult(
        label=label or pdf_path.stem,
        pdf_path=str(pdf_path),
        md_path=str(md_path),
        log_dir=str(log_dir),
        docx_path=str(docx_path) if docx_path else "",
        pages=int(pdf_info["pages"]),
        total_sections=total_secs,
        chapters=len(chapters15e),
        mapped_count=len(mapped),
        coverage_ratio=len(mapped) / max(total_secs, 1),
        avg_overlap=avg_for_verdict,
        inversions=inversions,
        weak_heading_count=len(weak_sections),
        title_noise_count=len(title_noise),
        syllabus_body_hits=len(syllabus_hits),
        pdf_match_failures=len(pdf_failures),
        duplicate_chapter_count=len(dup_ch),
        repeated_pairs=len(repeated),
        short_notes=short_notes,
        docx_chapter_delta=docx_ch_delta,
        docx_section_delta=docx_sec_delta,
        parent_mirror_count=len(parent_mirrors),
        heading_acceptance_verdict=heading_acceptance.verdict(),
        heading_acceptance_failed=len(heading_acceptance.failed_criteria),
        heading_export_violations=heading_acceptance.export_violation_count,
        acceptance_criteria=dict(heading_acceptance.criteria),
        acceptance_violation_samples=[
            f"[{v.criterion_id}] {v.source}/{v.level}: {v.heading[:60]} ({v.heading_class})"
            for v in heading_acceptance.violations[:8]
        ],
        verdict_scores=verdict_scores,
        top_issues=top_issues[:8],
        strong_sections=strong_sections[:5],
        parent_mirror_samples=parent_mirrors[:8],
        line_audit_sections=len(line_audit_book.sections) if line_audit_book else 0,
        line_audit_lines=line_audit_book.total_lines if line_audit_book else 0,
        line_audit_issues=line_audit_book.total_issues if line_audit_book else 0,
        line_audit_fail_sections=line_audit_fail,
        line_audit_warn_sections=line_audit_warn,
        line_audit_summary=line_audit_book.to_dict() if line_audit_book else {},
        line_audit_samples=line_audit_samples[:8],
    )
    return r, result


def resolve_chapter_hierarchy_artifact_safe(log_dir: Path) -> Optional[Path]:
    from src.modules.pipeline.stage_registry import resolve_chapter_hierarchy_artifact

    try:
        return resolve_chapter_hierarchy_artifact(log_dir)
    except Exception:
        return None


def flat15e_from_chapters(chapters15e: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, int]]:
    flat: List[Tuple[str, str, int]] = []
    for ch in chapters15e:
        ch_name = str(ch.get("heading") or "")
        for sec in ch.get("sections") or []:
            flat.append((ch_name, str(sec.get("heading") or ""), int(sec.get("page_number") or 0)))
    return flat


def flat15e_from_chapters_with_ids(chapters15e: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, int]]:
    flat: List[Tuple[str, str, int]] = []
    for ch in chapters15e:
        for sec in ch.get("sections") or []:
            flat.append((str(ch.get("heading") or ""), str(sec.get("section_id") or ""), int(sec.get("page_number") or 0)))
    return flat


def build_combined_report(results: Sequence[BookAuditResult]) -> str:
    lines: List[str] = []
    lines.append("# Notes Quality Audit — Batch Summary")
    lines.append("")
    lines.append(f"Books audited: **{len(results)}**")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        "| Book | Pages | Sections | Coverage | Completeness | Line quality | Heading AC | Verdict |"
    )
    lines.append(
        "|------|-------|----------|----------|--------------|--------------|------------|---------|"
    )
    for r in results:
        lines.append(
            f"| {r.label} | {r.pages} | {r.total_sections} | "
            f"{r.coverage_ratio:.0%} | {r.verdict_scores.get('completeness', '—')} | "
            f"{r.verdict_scores.get('line_quality', '—')} | "
            f"{r.heading_acceptance_verdict or '—'} | "
            f"**{r.verdict_scores.get('overall', 'WARN')}** |"
        )
    lines.append("")
    lines.append("## Acceptance criteria (heading pipeline rules)")
    lines.append("")
    lines.append(
        "Each book is checked against AC-01…AC-05, AC-07: no CHAPTER I:/PART/MODULE/OF OFFENCES in export; "
        "no Rs.10 lakh/BNS/page-footer fragments; display resolver clean; "
        ">=98% section coverage; <=3 very short bodies."
    )
    lines.append("")
    lines.append("## Regression notes")
    lines.append("")
    lines.append("- Heading acceptance criteria enforce today's structural-partition and PDF-fragment fixes.")
    lines.append("- Completeness and simple-English dimensions are weighted in overall verdict.")
    lines.append("")
    for r in results:
        lines.append(f"## {r.label}")
        lines.append("")
        lines.append(f"**Overall verdict: {r.verdict_scores.get('overall', 'WARN')}**")
        lines.append("")
        lines.append("### Dimension scores")
        for dim, score in r.verdict_scores.items():
            if dim != "overall":
                lines.append(f"- {dim}: {score}")
        lines.append("")
        lines.append("### Acceptance criteria")
        if r.acceptance_criteria:
            for cid, status in sorted(r.acceptance_criteria.items()):
                lines.append(f"- {cid}: **{status}**")
        else:
            lines.append("- Not run")
        lines.append("")
        lines.append("### Top issues")
        if r.top_issues:
            for issue in r.top_issues:
                lines.append(f"- {issue}")
        else:
            lines.append("- None flagged")
        lines.append("")
        lines.append("### Strong sections (verified in PDF)")
        if r.strong_sections:
            for sec in r.strong_sections:
                lines.append(f"- {sec}")
        else:
            lines.append("- None sampled")
        lines.append("")
    return "\n".join(lines) + "\n"


def load_manifest(path: Path) -> List[Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "books" in data:
        return list(data["books"])
    if isinstance(data, list):
        return data
    raise ValueError(f"Invalid manifest format: {path}")


def run_batch_audit(
    manifest_path: Path,
    *,
    audit_dir: Path,
    combined_out: Optional[Path] = None,
    json_out: Optional[Path] = None,
) -> List[BookAuditResult]:
    books = load_manifest(manifest_path)
    results: List[BookAuditResult] = []
    audit_dir.mkdir(parents=True, exist_ok=True)

    for entry in books:
        label = entry.get("label") or "book"
        pdf_path = Path(entry["pdf"])
        log_dir = Path(entry["log_dir"])
        md_path = Path(entry["md"])
        docx_raw = entry.get("docx")
        docx_path = Path(docx_raw) if docx_raw else md_path.with_suffix(".docx")

        for name, p in [("PDF", pdf_path), ("log dir", log_dir), ("markdown", md_path)]:
            if not p.exists():
                raise FileNotFoundError(f"Missing {name} for {label}: {p}")

        report, result = build_report(
            label=label,
            pdf_path=pdf_path,
            log_dir=log_dir,
            md_path=md_path,
            docx_path=docx_path if docx_path.exists() else None,
        )
        out_path = audit_dir / f"{label}_quality_report.txt"
        report.save(out_path)
        print(f"[+] {label}: {result.verdict_scores.get('overall')} -> {out_path}")
        results.append(result)

    if combined_out:
        combined_out.parent.mkdir(parents=True, exist_ok=True)
        combined_out.write_text(build_combined_report(results), encoding="utf-8")
        print(f"[+] Combined report: {combined_out}")

    if json_out:
        payload = aggregate_batch_summary(results)
        payload["manifest"] = str(manifest_path)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[+] JSON summary: {json_out}")

    return results


