"""Line-by-line notes body audit — aggressive content quality heuristics."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.modules.quality.heuristics import detect_syllabus_noise_in_body, norm

_STANDALONE_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)\d+\.\s+(.*)$")
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+")
_META_FILLER_RE = re.compile(
    r"^(this (chapter|section|topic)|in this (chapter|section)|"
    r"we (will |shall )?(discuss|cover|learn|explore)|"
    r"the (following|above) (section|chapter|points?)|"
    r"as (discussed|mentioned|noted) (above|earlier)|"
    r"it is important to note|this (note|section) (covers|explains|deals with))\b",
    re.I,
)
_TEMPLATE_RE = re.compile(
    r"^(key points|quick revision|also cover|exam tip|summary|definition)\s*:?\s*$",
    re.I,
)
_INCOMPLETE_TRAIL_RE = re.compile(r"(,\s*$|\band\s*$|\bor\s*$|\bthe\s*$|\bof\s*$|\bto\s*$)", re.I)
_STOPWORDS = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "will",
        "shall",
        "section",
        "article",
        "articles",
        "which",
        "their",
        "there",
        "these",
        "those",
        "when",
        "where",
        "what",
        "into",
        "about",
    }
)


def line_audit_enabled() -> bool:
    return os.environ.get("NOTES_QUALITY_LINE_AUDIT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def line_audit_strict() -> bool:
    return os.environ.get("NOTES_QUALITY_LINE_AUDIT_STRICT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def semantic_grounding_enabled() -> bool:
    """When on, a line failing literal source overlap is re-checked semantically.

    This keeps drift/hallucination detection (low semantic similarity is still
    flagged) while not penalizing legitimate paraphrase into simple English
    (high semantic similarity, low literal token overlap).
    """
    return os.environ.get("NOTES_QUALITY_SEMANTIC_GROUNDING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _semantic_min_sim() -> float:
    try:
        return float(os.environ.get("NOTES_QUALITY_SEMANTIC_MIN_SIM", "0.45"))
    except ValueError:
        return 0.45


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


class _SemanticGrounder:
    """Embedding-based grounding check using the shared MiniLM encoder.

    Precomputes source sentence embeddings once per section; `grounded(line)`
    returns True when the line is semantically close to some source sentence.
    Degrades to a no-op (always False) when the model/source is unavailable.
    """

    def __init__(self, source_text: str, *, enabled: bool) -> None:
        self.ready = False
        self._encoder = None
        self._corpus = None
        self.min_sim = _semantic_min_sim()
        if not enabled or not (source_text or "").strip():
            return
        sentences = [s.strip() for s in _SENT_SPLIT_RE.split(source_text) if len(s.split()) >= 3]
        if not sentences:
            return
        try:
            from src.modules.structure.final_structuring.models.mini_lm_encoder import (
                get_mini_lm_encoder,
            )

            encoder = get_mini_lm_encoder()
            corpus = encoder.encode(sentences)
        except Exception:
            corpus = None
            encoder = None
        if corpus is not None and len(corpus) > 0:
            self._encoder = encoder
            self._corpus = corpus
            self.ready = True

    def grounded(self, line: str) -> bool:
        if not self.ready:
            return False
        emb = self._encoder.encode([line])
        if emb is None or len(emb) == 0:
            return False
        return self._encoder.max_similarity(emb[0], self._corpus) >= self.min_sim


def _tokens(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
        if w not in _STOPWORDS
    }


def _heading_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


@dataclass
class LineIssue:
    line_no: int
    text: str
    code: str
    detail: str = ""


@dataclass
class SectionLineAudit:
    section_id: str
    heading: str
    line_count: int = 0
    prose_lines: int = 0
    bullet_lines: int = 0
    issues: List[LineIssue] = field(default_factory=list)
    source_overlap: float = 0.0
    verdict: str = "PASS"
    score: float = 100.0

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def issue_codes(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "heading": self.heading[:120],
            "line_count": self.line_count,
            "prose_lines": self.prose_lines,
            "bullet_lines": self.bullet_lines,
            "issue_count": self.issue_count,
            "source_overlap": round(self.source_overlap, 3),
            "verdict": self.verdict,
            "score": round(self.score, 1),
            "issues_by_code": self.issue_codes(),
            "sample_issues": [
                {"line": i.line_no, "code": i.code, "text": i.text[:100]}
                for i in self.issues[:6]
            ],
        }


@dataclass
class BookLineAudit:
    sections: List[SectionLineAudit] = field(default_factory=list)
    total_lines: int = 0
    total_issues: int = 0
    issue_by_code: Dict[str, int] = field(default_factory=dict)
    sections_pass: int = 0
    sections_ok: int = 0
    sections_warn: int = 0
    sections_fail: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_lines": self.total_lines,
            "total_issues": self.total_issues,
            "issue_by_code": self.issue_by_code,
            "sections_pass": self.sections_pass,
            "sections_ok": self.sections_ok,
            "sections_warn": self.sections_warn,
            "sections_fail": self.sections_fail,
            "worst_sections": [s.to_dict() for s in self.worst_sections(8)],
        }

    def worst_sections(self, n: int = 8) -> List[SectionLineAudit]:
        ranked = sorted(self.sections, key=lambda s: (s.score, -s.issue_count))
        return [s for s in ranked if s.verdict != "PASS"][:n]


def _keyword_overlap(source: str, notes: str) -> float:
    from src.modules.generation.rewrite_fidelity import section_overlap_score

    return section_overlap_score(source=source, generated=notes)


def _audit_single_line(
    line: str,
    *,
    line_no: int,
    heading: str,
    source_preview: str,
    strict: bool,
    grounder: Optional["_SemanticGrounder"] = None,
    skip_overlap: bool = False,
) -> List[LineIssue]:
    raw = line.rstrip()
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("```"):
        return []
    if _HEADING_LINE_RE.match(stripped):
        return [LineIssue(line_no, stripped[:100], "markdown_heading", "heading inside body")]

    issues: List[LineIssue] = []

    if _STANDALONE_BOLD_RE.match(stripped):
        issues.append(LineIssue(line_no, stripped[:100], "standalone_bold", "fake subheading line"))
    if _META_FILLER_RE.search(stripped):
        issues.append(LineIssue(line_no, stripped[:100], "meta_filler", "chapter/section meta text"))
    if _TEMPLATE_RE.match(stripped):
        issues.append(LineIssue(line_no, stripped[:100], "template_label", "study template artifact"))

    for flag in detect_syllabus_noise_in_body(stripped):
        issues.append(LineIssue(line_no, stripped[:100], flag, "syllabus/admin on line"))

    if heading and _heading_sim(heading, stripped) >= 0.88:
        issues.append(LineIssue(line_no, stripped[:100], "heading_echo", "repeats section title"))

    bullet = _BULLET_RE.match(raw)
    if bullet:
        body = (bullet.group(2) or "").strip()
        if len(body.split()) < 3:
            issues.append(LineIssue(line_no, stripped[:100], "thin_bullet", "bullet with too little content"))
        if _META_FILLER_RE.search(body):
            issues.append(LineIssue(line_no, stripped[:100], "meta_filler", "meta text in bullet"))
        return issues

    if _ORDERED_RE.match(raw):
        return issues

    # Prose line checks
    words = stripped.split()
    if len(words) < 4 and not stripped.endswith((".", "!", "?", ":")):
        issues.append(LineIssue(line_no, stripped[:100], "thin_line", "very short orphan line"))

    if len(words) >= 10 and not re.search(r"[.!?]\s*$", stripped):
        if _INCOMPLETE_TRAIL_RE.search(stripped):
            issues.append(LineIssue(line_no, stripped[:100], "incomplete_sentence", "trails off mid-thought"))
        elif strict:
            issues.append(LineIssue(line_no, stripped[:100], "no_terminal_punct", "long line without end punctuation"))

    if source_preview and len(words) >= 8 and not skip_overlap:
        line_ov = _keyword_overlap(source_preview, stripped)
        if line_ov < 0.04 and _keyword_overlap(source_preview, heading) < 0.15:
            # Literal overlap is near-zero. Before flagging as drift, give the line
            # a semantic second chance: paraphrase keeps meaning (high MiniLM sim)
            # even when it shares no surface tokens with the source.
            if not (grounder is not None and grounder.grounded(stripped)):
                issues.append(
                    LineIssue(line_no, stripped[:100], "low_source_overlap", f"line overlap {line_ov:.0%} with source")
                )

    return issues


def _score_section(
    *,
    line_count: int,
    issue_count: int,
    source_overlap: float,
    strict: bool,
) -> Tuple[str, float]:
    if line_count == 0:
        return "FAIL", 0.0
    rate = issue_count / max(line_count, 1)
    score = max(0.0, 100.0 - rate * 120.0 - max(0.0, 0.25 - source_overlap) * 40.0)
    if issue_count == 0 and source_overlap >= 0.15:
        return "PASS", score
    if rate <= 0.08 and issue_count <= 1 and source_overlap >= 0.1:
        return "PASS", score
    if rate <= 0.18 and issue_count <= 3:
        return "OK", score
    if rate <= 0.35 or (strict and rate <= 0.45):
        return "WARN", score
    return "FAIL", score


def audit_section_body(
    *,
    section_id: str,
    heading: str,
    body: str,
    source_preview: str = "",
    strict: Optional[bool] = None,
    semantic: Optional[bool] = None,
    source_low_grounding: bool = False,
) -> SectionLineAudit:
    """Audit every non-empty line in a section body.

    `source_low_grounding` marks sections whose source is an index/contents list
    (already reported separately as low-grounding). For those, source-overlap
    drift checks are skipped to avoid double-penalizing a known issue.
    """
    strict_mode = line_audit_strict() if strict is None else strict
    semantic_mode = semantic_grounding_enabled() if semantic is None else semantic
    audit = SectionLineAudit(section_id=section_id, heading=heading)
    if not (body or "").strip():
        audit.verdict = "FAIL"
        audit.score = 0.0
        audit.issues.append(LineIssue(0, "", "empty_body", "no rewritten content"))
        return audit

    audit.source_overlap = _keyword_overlap(source_preview, body)
    grounder = (
        _SemanticGrounder(source_preview, enabled=semantic_mode)
        if (semantic_mode and not source_low_grounding)
        else None
    )
    in_fence = False
    line_no = 0

    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            continue

        line_no += 1
        audit.line_count += 1
        if _BULLET_RE.match(raw) or _ORDERED_RE.match(raw):
            audit.bullet_lines += 1
        else:
            audit.prose_lines += 1

        for issue in _audit_single_line(
            raw,
            line_no=line_no,
            heading=heading,
            source_preview=source_preview,
            strict=strict_mode,
            grounder=grounder,
            skip_overlap=source_low_grounding,
        ):
            audit.issues.append(issue)

    if audit.line_count > 0 and audit.prose_lines == 0 and audit.bullet_lines >= 3:
        audit.issues.append(
            LineIssue(0, "", "bullet_only_section", f"{audit.bullet_lines} bullets, no prose paragraphs")
        )

    if (
        not source_low_grounding
        and audit.source_overlap < 0.08
        and source_preview.strip()
        and audit.line_count >= 2
        and not (grounder is not None and grounder.grounded(body))
    ):
        audit.issues.append(
            LineIssue(0, "", "section_drift", f"body overlap {audit.source_overlap:.0%} with source preview")
        )

    audit.verdict, audit.score = _score_section(
        line_count=audit.line_count,
        issue_count=len(audit.issues),
        source_overlap=audit.source_overlap,
        strict=strict_mode,
    )
    return audit


def audit_all_sections(
    sections: Sequence[Dict[str, Any]],
    *,
    bodies_by_id: Dict[str, str],
    source_by_id: Optional[Dict[str, str]] = None,
    strict: Optional[bool] = None,
    semantic: Optional[bool] = None,
) -> BookLineAudit:
    """Run line audit across every mapped section."""
    from src.shared.text_grounding import is_low_grounding

    book = BookLineAudit()
    source_by_id = source_by_id or {}

    for row in sections:
        sid = str(row.get("section_id") or "")
        heading = str(row.get("heading") or "")
        body = bodies_by_id.get(sid, "")
        if not body:
            continue
        section_source = source_by_id.get(sid, "")
        sec_audit = audit_section_body(
            section_id=sid,
            heading=heading,
            body=body,
            source_preview=section_source,
            strict=strict,
            semantic=semantic,
            source_low_grounding=is_low_grounding(section_source, min_chars=160),
        )
        book.sections.append(sec_audit)
        book.total_lines += sec_audit.line_count
        book.total_issues += sec_audit.issue_count
        for code, count in sec_audit.issue_codes().items():
            book.issue_by_code[code] = book.issue_by_code.get(code, 0) + count
        if sec_audit.verdict == "PASS":
            book.sections_pass += 1
        elif sec_audit.verdict == "OK":
            book.sections_ok += 1
        elif sec_audit.verdict == "WARN":
            book.sections_warn += 1
        else:
            book.sections_fail += 1

    return book


def format_line_audit_report(book: BookLineAudit) -> List[str]:
    """Human-readable report lines for insertion into quality report."""
    lines: List[str] = []
    lines.append(f"  Sections line-audited:       {len(book.sections)}")
    lines.append(f"  Total content lines scanned: {book.total_lines}")
    lines.append(f"  Total line issues flagged:   {book.total_issues}")
    lines.append(
        f"  Section verdicts:            PASS={book.sections_pass} OK={book.sections_ok} "
        f"WARN={book.sections_warn} FAIL={book.sections_fail}"
    )
    if book.issue_by_code:
        top_codes = sorted(book.issue_by_code.items(), key=lambda x: -x[1])[:10]
        lines.append(f"  Issue types (top):           {dict(top_codes)}")
    worst = book.worst_sections(10)
    if worst:
        lines.append("  Worst sections (line-level):")
        for sec in worst:
            codes = ", ".join(f"{k}×{v}" for k, v in sorted(sec.issue_codes().items(), key=lambda x: -x[1])[:4])
            lines.append(
                f"    [{sec.section_id}] {sec.verdict} score={sec.score:.0f} "
                f"issues={sec.issue_count}/{sec.line_count} — {sec.heading[:45]}"
            )
            if codes:
                lines.append(f"      types: {codes}")
            for issue in sec.issues[:3]:
                lines.append(f"      L{issue.line_no} {issue.code}: {issue.text[:70]}")
    else:
        lines.append("  All audited sections passed line-level checks.")
    return lines
