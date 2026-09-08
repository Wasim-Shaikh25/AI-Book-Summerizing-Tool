"""Auto-retry rewrite for sections that failed or returned empty."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.modules.generation.rewrite_prompts import (
    build_section_user_prompt_with_context,
    resolve_rewrite_profile,
    rewrite_system_prompt,
)
from src.modules.generation.rewrite_validation import (
    RewriteValidationReport,
    missing_sections_from_report,
    validate_rewrite_coverage,
)
from src.modules.generation.parallel_rewrite import build_rewrite_jobs
from src.modules.generation.rewrite_validation import iter_hierarchy_sections
from src.modules.generation.toc_sections import _merge_section_body
from src.shared import config

GenerateFn = Callable[[str, str], str]
OnSectionFn = Callable[[str, str, int, int], None]


def _section_row_from_hierarchy(hierarchy: Dict[str, Any], section_id: str) -> Optional[Dict[str, Any]]:
    for row in iter_hierarchy_sections(hierarchy):
        if str(row.get("section_id") or "") == section_id:
            return row
    return None


def _work_row_for_section(
    sections: Sequence[Dict[str, Any]],
    hierarchy: Dict[str, Any],
    section_id: str,
) -> Optional[Dict[str, Any]]:
    for sec in sections:
        if str(sec.get("section_id") or "") == section_id:
            return dict(sec)
    row = _section_row_from_hierarchy(hierarchy, section_id)
    if row is None:
        return None
    for ch in hierarchy.get("chapters") or []:
        for sec in ch.get("sections") or []:
            if str(sec.get("section_id") or "") != section_id:
                continue
            merged = _merge_section_body(sec, {})
            return {
                "section_id": section_id,
                "heading": row.get("heading") or sec.get("heading") or "",
                "text": merged,
                "chapter_heading": row.get("chapter_heading") or ch.get("heading") or "",
                "subheadings": [
                    str(s.get("heading") or "").strip()
                    for s in sec.get("subheadings") or []
                    if str(s.get("heading") or "").strip()
                ],
            }
    return None


def auto_retry_missing_enabled() -> bool:
    explicit = os.environ.get("REWRITE_AUTO_RETRY_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() not in {"0", "false", "no", "n"}
    cfg_val = getattr(config, "REWRITE_AUTO_RETRY_ENABLED", "true")
    if str(cfg_val).strip().lower() in {"0", "false", "no", "n"}:
        return False
    if str(cfg_val).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return os.environ.get("REWRITE_AUTO_RETRY_MISSING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "n",
    }


def resolve_auto_retry_min_coverage(explicit: Optional[float] = None) -> float:
    if explicit is not None:
        return max(0.0, min(1.0, float(explicit)))
    raw = os.environ.get(
        "REWRITE_AUTO_RETRY_MIN_COVERAGE",
        str(getattr(config, "REWRITE_AUTO_RETRY_MIN_COVERAGE", 0.95)),
    )
    try:
        return max(0.0, min(1.0, float(raw or "0.95")))
    except ValueError:
        return 0.95


def resolve_auto_retry_max_passes(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 1:
        return explicit
    raw = os.environ.get(
        "REWRITE_AUTO_RETRY_MAX_PASSES",
        str(getattr(config, "REWRITE_AUTO_RETRY_MAX_PASSES", 1)),
    )
    try:
        return max(1, int(raw or "1"))
    except ValueError:
        return 1


def resolve_missing_max_rounds(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 1:
        return explicit
    raw = os.environ.get(
        "REWRITE_MISSING_MAX_ROUNDS",
        str(getattr(config, "REWRITE_MISSING_MAX_ROUNDS", 3)),
    )
    try:
        return max(1, int(raw or "3"))
    except ValueError:
        return 3


def retry_missing_sections(
    *,
    hierarchy: Dict[str, Any],
    rewritten: Dict[str, str],
    sections: Sequence[Dict[str, Any]],
    user_instruction: str,
    generate: GenerateFn,
    exam_oriented: Optional[bool] = None,
    max_source_chars: Optional[int] = None,
    overlap_chars: Optional[int] = None,
    max_rounds: Optional[int] = None,
    on_section: Optional[OnSectionFn] = None,
    intent: Optional[Any] = None,
) -> Tuple[Dict[str, str], RewriteValidationReport]:
    """
    Rewrite only missing/empty sections until coverage passes or rounds exhausted.
    Returns updated rewritten map and final validation report.
    """
    from src.modules.generation.parallel_rewrite import resolve_context_overlap_chars

    profile = resolve_rewrite_profile(user_instruction, intent=intent)
    exam = profile.exam_oriented if exam_oriented is None else exam_oriented
    system = rewrite_system_prompt(
        user_instruction=user_instruction,
        intent=intent,
    )
    cap = max_source_chars or int(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000)
    overlap = resolve_context_overlap_chars(overlap_chars)
    rounds = resolve_missing_max_rounds(max_rounds)

    out = dict(rewritten)
    sec_list = list(sections)
    jobs = build_rewrite_jobs(sec_list, max_source_chars=cap, overlap_chars=overlap)
    job_by_id = {j.section_id: j for j in jobs}

    report = validate_rewrite_coverage(hierarchy, out)
    for round_no in range(1, rounds + 1):
        missing = missing_sections_from_report(report)
        if not missing:
            break

        print(f"\n      Auto-retry missing sections (round {round_no}/{rounds}, count={len(missing)})...")
        for idx, (sid, heading) in enumerate(missing, start=1):
            job = job_by_id.get(sid)
            if job is None:
                fallback_sec = _work_row_for_section(sec_list, hierarchy, sid)
                if fallback_sec is None:
                    print(f"        [!] No job for {sid} — skip")
                    continue
                extra_jobs = build_rewrite_jobs([fallback_sec], max_source_chars=cap, overlap_chars=overlap)
                if not extra_jobs:
                    print(f"        [!] No job for {sid} — skip")
                    continue
                job = extra_jobs[0]
                job_by_id[sid] = job
            label = str(job.heading or heading)[:70]
            if on_section:
                on_section(sid, label, idx, len(missing))
            else:
                print(f"        {idx}/{len(missing)} {sid}: {label!r}")

            prompt = build_section_user_prompt_with_context(
                user_instruction=user_instruction,
                heading=job.heading,
                source_text=job.source_text,
                prev_heading=job.prev_heading,
                prev_overlap=job.prev_overlap,
                next_heading=job.next_heading,
                next_overlap=job.next_overlap,
                chapter_heading=job.chapter_heading,
                subheadings=list(job.subheadings),
            )
            text = (generate(system, prompt) or "").strip()
            if not text:
                print(f"        [!] Empty response for {sid}")
                continue
            out[sid] = text
            print(f"        [+] {sid} done ({len(text)} chars)")

        report = validate_rewrite_coverage(hierarchy, out)

    return out, report
