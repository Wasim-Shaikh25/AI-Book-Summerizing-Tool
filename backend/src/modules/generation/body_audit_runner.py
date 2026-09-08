"""Pipeline wrapper for body_structure_audit — called as optional step [3.5/4].

Mirrors the pattern of structure_fix_runner.py: thin integration module that
bridges pipeline plumbing from the audit logic.

Activated by BODY_STRUCTURE_AUDIT_ENABLED=1 (default 0).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def body_audit_enabled() -> bool:
    return os.getenv("BODY_STRUCTURE_AUDIT_ENABLED", "0").strip() == "1"


def run_body_audit(
    sections: List[Dict[str, Any]],
    *,
    source_by_id: Dict[str, str],
    chat: Optional[Any] = None,
    log_dir: Optional[Path] = None,
) -> "BodyAuditReport":
    """Run body structure audit on a list of rewritten sections.

    Writes a JSON audit report to log_dir if provided.
    Can be called standalone (not only via full pipeline).

    Args:
        sections:     List of {"section_id": str, "heading": str, "body": str}.
        source_by_id: Map from section_id to original source text.
        chat:         LLM client for optional fix pass (BODY_AUDIT_LLM=1).
        log_dir:      When provided, writes ``body_audit_report.json`` there.

    Returns:
        BodyAuditReport with issue list and counts.
    """
    from src.modules.generation.body_structure_audit import BodyAuditReport, audit_body_structure

    report = audit_body_structure(sections, source_by_id=source_by_id, chat=chat)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        out = {
            "sections_checked": report.sections_checked,
            "sections_flagged": report.sections_flagged,
            "llm_fixed": report.llm_fixed,
            "issues": [
                {
                    "section_id": i.section_id,
                    "heading": i.heading,
                    "issue_type": i.issue_type,
                    "detail": i.detail,
                }
                for i in report.issues
            ],
        }
        (log_dir / "body_audit_report.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "Body audit: checked=%d flagged=%d llm_fixed=%d",
            report.sections_checked,
            report.sections_flagged,
            report.llm_fixed,
        )

    return report
