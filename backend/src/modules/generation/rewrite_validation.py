"""Post-rewrite validation — coverage, hierarchy naming, and structure checks."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class RewriteValidationReport:
    total_sections: int = 0
    rewritten_count: int = 0
    missing_section_ids: List[str] = field(default_factory=list)
    empty_section_ids: List[str] = field(default_factory=list)
    duplicate_chapter_names: List[str] = field(default_factory=list)
    weak_section_headings: List[str] = field(default_factory=list)
    subheading_gaps: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    ok: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_lines(self) -> List[str]:
        lines = [
            f"Sections expected: {self.total_sections}",
            f"Sections with rewrite: {self.rewritten_count} ({self.coverage_ratio:.0%})",
            f"Missing: {len(self.missing_section_ids)} | Empty: {len(self.empty_section_ids)}",
            f"Duplicate chapters: {len(self.duplicate_chapter_names)}",
            f"Weak section titles: {len(self.weak_section_headings)}",
            f"Status: {'PASS' if self.ok else 'FAIL'}",
        ]
        if self.missing_section_ids:
            lines.append("Missing section IDs (first 10):")
            for sid in self.missing_section_ids[:10]:
                lines.append(f"  - {sid}")
        for w in self.warnings[:8]:
            lines.append(f"  WARN: {w}")
        return lines


_SECTION_ID_TAG = re.compile(r"<!--\s*sid:([A-Za-z0-9_]+)\s*-->")
SECTION_ID_TAG = _SECTION_ID_TAG

_WEAK_HEADING = re.compile(
    r"^(\(\w+\)|\d+\.|$|\(Art\.\s*\d+\)|\d{4}\.\s*\(Art\.)",
    re.I,
)


def normalize_heading(text: str) -> str:
    """Normalize heading for fuzzy matching (OCR/punctuation/encoding tolerant)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def heading_similarity(a: str, b: str) -> float:
    na, nb = normalize_heading(a), normalize_heading(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def is_weak_section_heading(heading: str) -> bool:
    h = (heading or "").strip()
    if len(h) < 4:
        return True
    if _WEAK_HEADING.match(h):
        return True
    if h.startswith("(") and h.endswith(")") and len(h) < 20:
        return True
    return False


def iter_hierarchy_sections(hierarchy: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ch in hierarchy.get("chapters") or []:
        for sec in ch.get("sections") or []:
            rows.append(
                {
                    "section_id": str(sec.get("section_id") or ""),
                    "heading": str(sec.get("heading") or "").strip(),
                    "chapter_id": str(ch.get("chapter_id") or ""),
                    "chapter_heading": str(ch.get("heading") or "").strip(),
                    "page_number": sec.get("page_number"),
                    "subheadings": list(sec.get("subheadings") or []),
                }
            )
    return rows


def validate_rewrite_coverage(
    hierarchy: Dict[str, Any],
    rewritten: Dict[str, str],
    *,
    min_coverage: float = 0.98,
    check_subheadings: bool = True,
) -> RewriteValidationReport:
    """Verify every hierarchy section has non-empty rewritten content."""
    rows = iter_hierarchy_sections(hierarchy)
    report = RewriteValidationReport(total_sections=len(rows))

    chapter_names: List[str] = []
    for ch in hierarchy.get("chapters") or []:
        name = str(ch.get("heading") or "").strip()
        if name:
            chapter_names.append(name)

    from collections import Counter

    dupes = [n for n, c in Counter(chapter_names).items() if c > 1]
    report.duplicate_chapter_names = dupes
    if dupes:
        report.warnings.append(f"Duplicate chapter titles: {', '.join(dupes[:5])}")

    missing: List[str] = []
    empty: List[str] = []
    weak: List[str] = []
    sub_gaps: List[str] = []

    for row in rows:
        sid = row["section_id"]
        heading = row["heading"]
        if is_weak_section_heading(heading):
            weak.append(f"{sid}: {heading[:60]}")
        body = (rewritten.get(sid) or "").strip()
        if sid not in rewritten:
            missing.append(f"{sid}: {heading[:70]}")
        elif not body:
            empty.append(f"{sid}: {heading[:70]}")
        else:
            report.rewritten_count += 1
            if check_subheadings:
                for sub in row["subheadings"]:
                    sub_h = str(sub.get("heading") or "").strip()
                    if not sub_h or len(sub_h) < 4:
                        continue
                    if normalize_heading(sub_h) not in normalize_heading(body):
                        if heading_similarity(sub_h, body) < 0.15:
                            sub_gaps.append(f"{sid} missing subtopic mention: {sub_h[:50]}")

    report.missing_section_ids = missing
    report.empty_section_ids = empty
    report.weak_section_headings = weak[:40]
    report.subheading_gaps = sub_gaps[:30]
    report.coverage_ratio = report.rewritten_count / max(report.total_sections, 1)

    if report.coverage_ratio < min_coverage:
        report.warnings.append(
            f"Coverage {report.coverage_ratio:.0%} below minimum {min_coverage:.0%}"
        )
    if len(weak) > 20:
        report.warnings.append(
            f"{len(weak)} sections have weak/fragment headings from ingestion (may affect naming)"
        )

    report.ok = (
        report.coverage_ratio >= min_coverage
        and not empty
        and len(missing) == 0
    )
    return report


def save_rewritten_map(path: str | Path, rewritten: Dict[str, str], *, meta: Optional[Dict[str, Any]] = None) -> str:
    """Persist section_id -> rewrite body sidecar next to markdown output."""
    p = Path(path)
    payload = {"sections": rewritten, "meta": meta or {}}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def load_rewritten_map(path: str | Path) -> Dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sections = data.get("sections") if isinstance(data, dict) else data
    if not isinstance(sections, dict):
        raise ValueError(f"Invalid rewritten map: {path}")
    return {str(k): str(v) for k, v in sections.items()}


def default_rewritten_map_path(md_path: str | Path) -> Path:
    p = Path(md_path)
    return p.with_name(p.stem + ".rewritten_map.json")


def write_validation_report(path: str | Path, report: RewriteValidationReport) -> str:
    p = Path(path)
    p.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def missing_sections_from_report(report: RewriteValidationReport) -> List[Tuple[str, str]]:
    """Return [(section_id, heading), ...] from a validation report."""
    out: List[Tuple[str, str]] = []
    for line in report.missing_section_ids + report.empty_section_ids:
        if ":" in line:
            sid, _, heading = line.partition(":")
            out.append((sid.strip(), heading.strip()))
        elif line.strip():
            out.append((line.strip(), ""))
    return out
