"""Acceptance criteria for heading-cleanup rules (export + hierarchy display)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from src.modules.quality.heuristics import classify_heading
from src.modules.structure.dropped_heading_registry import is_incomplete_pdf_heading
from src.modules.generation.rewrite_validation import strip_section_id_tags as _strip_sid

# Headings with these classes must not appear in exported notes (MD/DOCX).
_EXPORT_FORBIDDEN_CLASSES = frozenset(
    {
        "structural_partition",
        "incomplete_fragment",
        "noisy_fragment",
        "prose_not_topic",
        "weak_fragment",
        "syllabus_heading",
        "empty",
    }
)

# Raw hierarchy may still carry PDF fragments; display resolver must repair them.
_DISPLAY_FORBIDDEN_CLASSES = _EXPORT_FORBIDDEN_CLASSES - frozenset({"syllabus_heading"})


ACCEPTANCE_CRITERIA: Tuple[Dict[str, str], ...] = (
    {
        "id": "AC-01",
        "name": "no_structural_partition_export",
        "rule": "Exported # / ## titles must not be CHAPTER I:, PART II, MODULE N, or OF OFFENCES… partition lines.",
    },
    {
        "id": "AC-02",
        "name": "no_incomplete_pdf_export",
        "rule": "Exported titles must not be PDF fragments (Rs.10 lakh, BNS tails, truncated clause ends, page footers).",
    },
    {
        "id": "AC-03",
        "name": "no_noisy_fragment_export",
        "rule": "Exported titles must not be classification rows, bare markers, or other noisy PDF fragments.",
    },
    {
        "id": "AC-04",
        "name": "display_resolver_clean",
        "rule": "Every section/chapter display title (resolve_*_display_heading) must classify as looks_ok.",
    },
    {
        "id": "AC-05",
        "name": "section_coverage",
        "rule": "Rewrite bodies mapped to hierarchy sections must be >= 98% (completeness).",
    },
    {
        "id": "AC-07",
        "name": "no_short_bodies",
        "rule": "Very short note bodies (<120 chars) must be <= 3 sections.",
    },
)


@dataclass
class HeadingViolation:
    source: str  # export_md | export_docx | hierarchy_display | hierarchy_raw
    level: str  # chapter | section | subheading
    heading: str
    heading_class: str
    criterion_id: str


@dataclass
class HeadingAcceptanceResult:
    criteria: Dict[str, str] = field(default_factory=dict)
    violations: List[HeadingViolation] = field(default_factory=list)
    export_chapter_count: int = 0
    export_section_count: int = 0
    display_checked: int = 0
    raw_bad_unrepaired: int = 0

    @property
    def export_violation_count(self) -> int:
        return sum(1 for v in self.violations if v.source.startswith("export"))

    @property
    def failed_criteria(self) -> List[str]:
        return [cid for cid, status in self.criteria.items() if status == "FAIL"]

    def verdict(self) -> str:
        fails = len(self.failed_criteria)
        if fails == 0:
            return "PASS"
        if fails <= 2:
            return "OK"
        return "WARN"


def parse_markdown_headings(md_text: str) -> List[Tuple[str, str]]:
    """Return (level, heading) for # and ## lines after TOC block."""
    out: List[Tuple[str, str]] = []
    in_body = False
    for line in (md_text or "").splitlines():
        if line.startswith("# Table of Contents"):
            in_body = True
            continue
        if not in_body:
            continue
        if line.strip().startswith("```{=openxml}"):
            continue
        if line.startswith("# ") and not line.startswith("## "):
            out.append(("chapter", _strip_sid(line[2:]).strip()))
        elif line.startswith("## ") and not line.startswith("### "):
            h = _strip_sid(line[3:]).strip()
            if h and not re.match(r"^\d+\.\s+", h):
                out.append(("section", h))
    return out


def _check_export_headings(
    headings: Sequence[Tuple[str, str]],
    *,
    source: str,
) -> List[HeadingViolation]:
    violations: List[HeadingViolation] = []
    for level, heading in headings:
        cls = classify_heading(heading)
        if cls == "structural_partition":
            violations.append(
                HeadingViolation(source, level, heading, cls, "AC-01")
            )
        elif cls == "incomplete_fragment" or (cls == "weak_fragment" and is_incomplete_pdf_heading(heading)):
            violations.append(
                HeadingViolation(source, level, heading, cls, "AC-02")
            )
        elif cls == "noisy_fragment":
            violations.append(
                HeadingViolation(source, level, heading, cls, "AC-03")
            )
        elif cls in _EXPORT_FORBIDDEN_CLASSES:
            violations.append(
                HeadingViolation(source, level, heading, cls, "AC-03")
            )
    return violations


def evaluate_heading_acceptance(
    *,
    chapters15e: Sequence[Dict[str, Any]],
    md_text: str,
    docx_chapters: Sequence[str] | None = None,
    docx_sections: Sequence[str] | None = None,
    mapped_count: int,
    total_sections: int,
    short_notes: int,
) -> HeadingAcceptanceResult:
    """Run acceptance criteria against hierarchy display titles and exported files."""
    from src.modules.structure.final_structuring.heading_title_engine import (
        resolve_chapter_display_heading,
        resolve_section_display_heading,
    )

    result = HeadingAcceptanceResult()
    md_headings = parse_markdown_headings(md_text)
    result.export_chapter_count = sum(1 for lvl, _ in md_headings if lvl == "chapter")
    result.export_section_count = sum(1 for lvl, _ in md_headings if lvl == "section")

    result.violations.extend(_check_export_headings(md_headings, source="export_md"))

    if docx_chapters is not None:
        docx_h = [("chapter", h) for h in docx_chapters if h]
        docx_h += [("section", h) for h in (docx_sections or []) if h]
        result.violations.extend(_check_export_headings(docx_h, source="export_docx"))

    raw_bad_unrepaired = 0
    for ch in chapters15e:
        ch_title = str(ch.get("heading") or "")
        display_ch = resolve_chapter_display_heading(ch, use_transformers=False)
        result.display_checked += 1
        ch_cls = classify_heading(display_ch)
        if ch_cls in _DISPLAY_FORBIDDEN_CLASSES:
            result.violations.append(
                HeadingViolation("hierarchy_display", "chapter", display_ch, ch_cls, "AC-04")
            )
        raw_ch_cls = classify_heading(ch_title)
        if raw_ch_cls in _DISPLAY_FORBIDDEN_CLASSES and ch_cls in _DISPLAY_FORBIDDEN_CLASSES:
            raw_bad_unrepaired += 1

        for sec in ch.get("sections") or []:
            raw = str(sec.get("heading") or "")
            display = resolve_section_display_heading(
                sec,
                chapter_heading=ch_title,
                use_transformers=False,
            )
            result.display_checked += 1
            disp_cls = classify_heading(display)
            if disp_cls in _DISPLAY_FORBIDDEN_CLASSES:
                result.violations.append(
                    HeadingViolation(
                        "hierarchy_display",
                        "section",
                        display or raw,
                        disp_cls,
                        "AC-04",
                    )
                )
            raw_cls = classify_heading(raw)
            if raw_cls in _DISPLAY_FORBIDDEN_CLASSES and disp_cls in _DISPLAY_FORBIDDEN_CLASSES:
                raw_bad_unrepaired += 1
                result.violations.append(
                    HeadingViolation("hierarchy_raw", "section", raw, raw_cls, "AC-04")
                )

    result.raw_bad_unrepaired = raw_bad_unrepaired

    ratio = mapped_count / max(total_sections, 1)

    ac01_fail = any(v.criterion_id == "AC-01" for v in result.violations)
    ac02_fail = any(v.criterion_id == "AC-02" for v in result.violations)
    ac03_fail = any(v.criterion_id == "AC-03" for v in result.violations)
    ac04_fail = any(v.criterion_id == "AC-04" for v in result.violations)

    result.criteria = {
        "AC-01": "FAIL" if ac01_fail else "PASS",
        "AC-02": "FAIL" if ac02_fail else "PASS",
        "AC-03": "FAIL" if ac03_fail else "PASS",
        "AC-04": "FAIL" if ac04_fail else "PASS",
        "AC-05": "FAIL" if ratio < 0.98 else "PASS",
        "AC-07": "FAIL" if short_notes > 3 else "PASS",
    }
    return result


def format_acceptance_report(result: HeadingAcceptanceResult) -> List[str]:
    lines: List[str] = []
    lines.append(f"  Acceptance verdict: {result.verdict()}")
    lines.append(f"  Export violations: {result.export_violation_count}")
    lines.append(f"  Display titles checked: {result.display_checked}")
    lines.append(f"  Raw bad headings unrepaired: {result.raw_bad_unrepaired}")
    lines.append("")
    lines.append("  Criteria:")
    for spec in ACCEPTANCE_CRITERIA:
        cid = spec["id"]
        status = result.criteria.get(cid, "—")
        lines.append(f"    [{status:4s}] {cid}  {spec['rule']}")
    if result.violations:
        lines.append("")
        lines.append("  Sample violations (first 15):")
        for v in result.violations[:15]:
            lines.append(
                f"    [{v.criterion_id}] {v.source}/{v.level} class={v.heading_class}  {v.heading[:65]}"
            )
        if len(result.violations) > 15:
            lines.append(f"    ... and {len(result.violations) - 15} more")
    return lines
