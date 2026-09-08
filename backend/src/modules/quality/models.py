"""Data models for notes quality audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Report:
    lines: List[str] = field(default_factory=list)

    def add(self, text: str = "") -> None:
        self.lines.append(text)

    def save(self, path) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


@dataclass
class BookAuditResult:
    label: str
    pdf_path: str
    md_path: str
    log_dir: str
    docx_path: str = ""
    pages: int = 0
    total_sections: int = 0
    chapters: int = 0
    mapped_count: int = 0
    coverage_ratio: float = 0.0
    avg_overlap: float = 0.0
    inversions: int = 0
    weak_heading_count: int = 0
    title_noise_count: int = 0
    syllabus_body_hits: int = 0
    pdf_match_failures: int = 0
    duplicate_chapter_count: int = 0
    repeated_pairs: int = 0
    short_notes: int = 0
    docx_chapter_delta: int = 0
    docx_section_delta: int = 0
    parent_mirror_count: int = 0
    heading_acceptance_verdict: str = ""
    heading_acceptance_failed: int = 0
    heading_export_violations: int = 0
    acceptance_criteria: Dict[str, str] = field(default_factory=dict)
    acceptance_violation_samples: List[str] = field(default_factory=list)
    line_audit_sections: int = 0
    line_audit_lines: int = 0
    line_audit_issues: int = 0
    line_audit_fail_sections: int = 0
    line_audit_warn_sections: int = 0
    line_audit_summary: Dict[str, Any] = field(default_factory=dict)
    line_audit_samples: List[str] = field(default_factory=list)
    verdict_scores: Dict[str, str] = field(default_factory=dict)
    top_issues: List[str] = field(default_factory=list)
    strong_sections: List[str] = field(default_factory=list)
    parent_mirror_samples: List[str] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "pdf": self.pdf_path,
            "md": self.md_path,
            "docx": self.docx_path,
            "log_dir": self.log_dir,
            "pages": self.pages,
            "sections": self.total_sections,
            "chapters": self.chapters,
            "coverage_pct": round(100 * self.coverage_ratio, 1),
            "avg_overlap_pct": round(100 * self.avg_overlap, 1),
            "weak_headings": self.weak_heading_count,
            "title_noise": self.title_noise_count,
            "syllabus_in_body": self.syllabus_body_hits,
            "pdf_match_failures": self.pdf_match_failures,
            "parent_mirror": self.parent_mirror_count,
            "heading_acceptance": self.heading_acceptance_verdict,
            "heading_export_violations": self.heading_export_violations,
            "acceptance_failed": self.heading_acceptance_failed,
            "acceptance_criteria": self.acceptance_criteria,
            "line_audit_issues": self.line_audit_issues,
            "line_audit_fail_sections": self.line_audit_fail_sections,
            "line_audit_warn_sections": self.line_audit_warn_sections,
            "duplicate_chapters": self.duplicate_chapter_count,
            "repeated_pairs": self.repeated_pairs,
            "verdict": self.verdict_scores.get("overall", "WARN"),
            "scores": self.verdict_scores,
            "top_issues": self.top_issues[:8],
            "strong_sections": self.strong_sections[:5],
        }
