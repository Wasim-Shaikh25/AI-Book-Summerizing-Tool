"""Notes quality analysis — deterministic audit + optional LLM insights."""

from src.modules.quality.analyzer import build_report, run_batch_audit
from src.modules.quality.heuristics import (
    chapter_mirrors_first_section,
    classify_heading,
    compute_verdict_scores,
    detect_syllabus_noise_in_body,
    find_parent_mirror_chapters,
)
from src.modules.quality.models import BookAuditResult, Report
from src.modules.quality.line_audit import audit_section_body, audit_all_sections, line_audit_enabled
from src.modules.quality.service import audit_enabled, run_quality_audit

__all__ = [
    "BookAuditResult",
    "Report",
    "audit_enabled",
    "build_report",
    "chapter_mirrors_first_section",
    "classify_heading",
    "compute_verdict_scores",
    "detect_syllabus_noise_in_body",
    "find_parent_mirror_chapters",
    "audit_all_sections",
    "audit_section_body",
    "line_audit_enabled",
    "run_batch_audit",
    "run_quality_audit",
]
