"""LLM-generated narrative and universal fix suggestions for quality audits."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from src.modules.quality.models import BookAuditResult

logger = logging.getLogger(__name__)

_SYSTEM = """You are a technical editor reviewing automated study-notes pipeline output.
You receive deterministic audit metrics only — not legal or subject-matter truth.

Write:
1) Executive summary (3-5 sentences) on coverage, naming, repetition, and line-level content quality.
2) Universal fix suggestions (numbered, max 8) for the **pipeline and configuration** only.
3) If line_audit data is present, call out recurring line-level problems (meta filler, thin bullets, heading echo, drift).

Rules for suggestions:
- MUST be universal (apply to any textbook PDF): heading cleanup, chapter grouping, rewrite prompts, batch sizes, validation gates.
- MUST NOT cite specific laws, articles, cases, or book topics.
- MUST NOT invent missing content from the PDF.
- Prefer actionable env/config/stage changes (e.g. enable 15j, tighten title validation, reduce parallel workers).

Return markdown with headings:
## Executive summary
## Universal fix suggestions
"""


def _provider() -> str:
    override = os.environ.get("NOTES_QUALITY_LLM_PROVIDER", "").strip().lower()
    if override:
        return override
    from src.shared.llm_provider import active_chat_provider

    return active_chat_provider()


def llm_insights_enabled() -> bool:
    return os.environ.get("NOTES_QUALITY_LLM", "1").strip().lower() not in {"0", "false", "no", "off"}


def generate_llm_insights(result: BookAuditResult, *, report_excerpt: str = "") -> Optional[str]:
    """Return markdown insights or None if LLM disabled/unavailable."""
    if not llm_insights_enabled():
        return None
    try:
        from src.modules.pipeline.llm_chat_client import LlmChatClient

        client = LlmChatClient(_provider(), temperature=0.2)
        if not client.chat_enabled:
            return None

        payload: Dict[str, Any] = {
            "audit_summary": result.to_summary_dict(),
            "top_issues": result.top_issues,
            "parent_mirror_samples": result.parent_mirror_samples,
            "line_audit": result.line_audit_summary,
            "line_audit_samples": result.line_audit_samples,
            "report_excerpt": (report_excerpt or "")[:3500],
        }
        user = (
            "Audit metrics JSON:\n"
            f"{json.dumps(payload, indent=2)}\n\n"
            "User rewrite instruction was for short, easy notes without extra detail."
        )
        text = client.chat(system=_SYSTEM, user=user, max_tokens=1200)
        if not text or not text.strip():
            return None
        return text.strip()
    except Exception as exc:
        logger.warning("LLM quality insights failed: %s", exc)
        return None
