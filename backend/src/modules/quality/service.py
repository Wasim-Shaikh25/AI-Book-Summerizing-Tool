"""High-level API for post-pipeline notes quality audit."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.modules.quality.analyzer import build_report
from src.modules.quality.llm_insights import generate_llm_insights
from src.modules.quality.models import BookAuditResult, Report


def audit_enabled() -> bool:
    return os.environ.get("NOTES_QUALITY_AUDIT", "1").strip().lower() not in {"0", "false", "no", "off"}


def run_quality_audit(
    *,
    pdf_path: Path,
    log_dir: Path,
    md_path: Path,
    docx_path: Optional[Path] = None,
    label: str = "",
    out_dir: Optional[Path] = None,
) -> Tuple[Report, BookAuditResult, Dict[str, Path]]:
    """Run deterministic audit + optional LLM insights; write artifacts."""
    docx = docx_path if docx_path and docx_path.exists() else None
    report, result = build_report(
        label=label,
        pdf_path=pdf_path,
        log_dir=log_dir,
        md_path=md_path,
        docx_path=docx,
    )

    base = out_dir or md_path.parent
    stem = md_path.stem
    paths = {
        "txt": base / f"{stem}.quality_report.txt",
        "json": base / f"{stem}.quality_report.json",
        "insights": base / f"{stem}.quality_insights.md",
    }

    insights = generate_llm_insights(result, report_excerpt=report.text()[:4000])
    if insights:
        report.add("")
        report.add("18. LLM INSIGHTS (universal pipeline suggestions)")
        report.add("-" * 72)
        for line in insights.splitlines():
            report.add(line)

    report.save(paths["txt"])

    payload: Dict[str, Any] = {
        "summary": result.to_summary_dict(),
        "line_audit": result.line_audit_summary,
        "insights_markdown": insights or "",
    }
    paths["json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if insights:
        header = f"# Quality insights — {result.label}\n\n"
        paths["insights"].write_text(header + insights + "\n", encoding="utf-8")

    return report, result, paths
