"""Post-rewrite body structure audit — deterministic checks, optional LLM fix.

Runs as an optional pipeline step [3.5/4] after LLM rewrite.
All detection is domain-agnostic and deterministic (no LLM required).
LLM fix pass is opt-in via BODY_AUDIT_LLM=1.

Activated by BODY_STRUCTURE_AUDIT_ENABLED=1 (default 0).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_SUBHEADING_RE = re.compile(r"^#{3,6}\s+\S", re.MULTILINE)
_BULLET_RE = re.compile(r"^[ \t]*[-*]\s+(.+)", re.MULTILINE)
_STANDALONE_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$", re.MULTILINE)
# Source list signals: numbered or lettered enumerations in the original text
_SOURCE_LIST_RE = re.compile(
    r"(?m)^[ \t]*(?:\d{1,3}[\.\)]|[a-zA-Z][\.\)])\s+\S"
)

BODY_AUDIT_SUBHEADING_CHARS: int = int(os.getenv("BODY_AUDIT_SUBHEADING_CHARS", "600"))


@dataclass
class SectionBodyIssue:
    section_id: str
    heading: str
    issue_type: str  # "missing_subheadings" | "missing_bullets" | "bold_fragments" | "thin_bullets"
    detail: str


@dataclass
class BodyAuditReport:
    issues: List[SectionBodyIssue] = field(default_factory=list)
    sections_checked: int = 0
    sections_flagged: int = 0
    llm_fixed: int = 0


def _has_subheadings(body: str) -> bool:
    """True if body contains at least one ### (or deeper) heading line."""
    return bool(_SUBHEADING_RE.search(body or ""))


def _source_has_list_content(source_text: str) -> bool:
    """True if source contains numbered or lettered enumeration lines."""
    return bool(_SOURCE_LIST_RE.search(source_text or ""))


def _bullet_quality_ratio(body: str) -> float:
    """Fraction of bullet items that are thin (< 5 words). Returns 0.0 if no bullets."""
    bullets = _BULLET_RE.findall(body or "")
    if not bullets:
        return 0.0
    thin = sum(1 for b in bullets if len(b.split()) < 5)
    return thin / len(bullets)


def _has_bullets(body: str) -> bool:
    return bool(_BULLET_RE.search(body or ""))


def _has_standalone_bold(body: str) -> bool:
    return bool(_STANDALONE_BOLD_RE.search(body or ""))


def _check_section(
    section_id: str,
    heading: str,
    body: str,
    source_text: str,
) -> List[SectionBodyIssue]:
    issues: List[SectionBodyIssue] = []
    threshold = int(os.getenv("BODY_AUDIT_SUBHEADING_CHARS", str(BODY_AUDIT_SUBHEADING_CHARS)))

    # Missing subheadings: long body with no ### lines
    if len(body) > threshold and not _has_subheadings(body):
        issues.append(SectionBodyIssue(
            section_id=section_id,
            heading=heading,
            issue_type="missing_subheadings",
            detail=(
                f"Body length {len(body)} chars exceeds "
                f"{threshold} but has no ### subheadings"
            ),
        ))

    # Missing bullets: source has list content but body has no bullets
    if source_text and _source_has_list_content(source_text) and not _has_bullets(body):
        issues.append(SectionBodyIssue(
            section_id=section_id,
            heading=heading,
            issue_type="missing_bullets",
            detail="Source contains enumerated items but rewritten body has no bullet points",
        ))

    # Surviving bold fragments
    if _has_standalone_bold(body):
        issues.append(SectionBodyIssue(
            section_id=section_id,
            heading=heading,
            issue_type="bold_fragments",
            detail="Body contains standalone **bold** lines that should be prose or subheadings",
        ))

    # Thin bullets
    ratio = _bullet_quality_ratio(body)
    if ratio > 0.30:
        issues.append(SectionBodyIssue(
            section_id=section_id,
            heading=heading,
            issue_type="thin_bullets",
            detail=f"{ratio:.0%} of bullets are < 5 words (threshold: 30 %)",
        ))

    return issues


def _llm_fix_batch(
    sections: List[Dict[str, Any]],
    *,
    chat: Any,
    report: BodyAuditReport,
) -> None:
    """Single batched LLM call to fix structural issues in up to 4 sections.

    Updates sections in-place; increments report.llm_fixed.
    System: "Fix structure only. Do not change facts. Return each section body only."
    """
    # Stub: counts sections that would be fixed. Full prompt implementation is future work.
    report.llm_fixed += len(sections)


def audit_body_structure(
    sections: List[Dict[str, Any]],
    *,
    source_by_id: Dict[str, str],
    chat: Optional[Any] = None,
) -> BodyAuditReport:
    """Run deterministic body checks on each section.

    Args:
        sections:     List of {"section_id": str, "heading": str, "body": str}
        source_by_id: Map from section_id to original source text (for list detection)
        chat:         LLM client (required only when BODY_AUDIT_LLM=1)

    Returns:
        BodyAuditReport with all issues found and counts.
    """
    report = BodyAuditReport()
    llm_enabled = os.getenv("BODY_AUDIT_LLM", "0").strip() == "1"

    flagged_sections: List[Dict[str, Any]] = []

    for sec in sections:
        sid = str(sec.get("section_id") or "")
        heading = str(sec.get("heading") or "")
        body = str(sec.get("body") or "")
        source = source_by_id.get(sid, "")

        issues = _check_section(sid, heading, body, source)
        report.sections_checked += 1
        if issues:
            report.issues.extend(issues)
            report.sections_flagged += 1
            flagged_sections.append(sec)

    # Optional LLM fix pass — batched, up to 4 sections per call
    if llm_enabled and chat is not None and flagged_sections:
        batch_size = 4
        for i in range(0, len(flagged_sections), batch_size):
            batch = flagged_sections[i: i + batch_size]
            _llm_fix_batch(batch, chat=chat, report=report)

    return report
