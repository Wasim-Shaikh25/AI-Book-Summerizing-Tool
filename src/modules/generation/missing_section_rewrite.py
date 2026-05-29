"""Auto-retry rewrite for sections that failed or returned empty."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.modules.generation.rewrite_prompts import (
    build_section_user_prompt_with_context,
    is_exam_oriented_mode,
    rewrite_system_prompt,
)
from src.modules.generation.rewrite_validation import (
    RewriteValidationReport,
    missing_sections_from_report,
    validate_rewrite_coverage,
)
from src.modules.generation.parallel_rewrite import build_rewrite_jobs
from src.shared import config

GenerateFn = Callable[[str, str], str]
OnSectionFn = Callable[[str, str, int, int], None]


def auto_retry_missing_enabled() -> bool:
    return os.environ.get("REWRITE_AUTO_RETRY_MISSING", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "n",
    }


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
) -> Tuple[Dict[str, str], RewriteValidationReport]:
    """
    Rewrite only missing/empty sections until coverage passes or rounds exhausted.
    Returns updated rewritten map and final validation report.
    """
    from src.modules.generation.parallel_rewrite import resolve_context_overlap_chars

    exam = is_exam_oriented_mode() if exam_oriented is None else exam_oriented
    system = rewrite_system_prompt(exam_oriented=exam)
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
                print(f"        [!] No job for {sid} — skip")
                continue
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
            )
            text = (generate(system, prompt) or "").strip()
            if not text:
                print(f"        [!] Empty response for {sid}")
                continue
            out[sid] = text
            print(f"        [+] {sid} done ({len(text)} chars)")

        report = validate_rewrite_coverage(hierarchy, out)

    return out, report
