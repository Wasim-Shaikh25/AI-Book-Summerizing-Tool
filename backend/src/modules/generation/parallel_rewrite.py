"""Parallel section rewrite with adjacent context overlap."""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.modules.generation.rewrite_prompts import build_section_user_prompt_with_context
from src.shared import config

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class _RewriteJob:
    index: int
    section_id: str
    heading: str
    source_text: str
    prev_heading: str
    prev_overlap: str
    next_heading: str
    next_overlap: str


def _overlap_tail(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if not t or max_chars <= 0:
        return ""
    if len(t) <= max_chars:
        return t
    chunk = t[-max_chars:]
    space = chunk.find(" ")
    if space > 40:
        chunk = chunk[space + 1 :]
    return chunk.strip()


def _overlap_head(text: str, *, max_chars: int) -> str:
    t = (text or "").strip()
    if not t or max_chars <= 0:
        return ""
    if len(t) <= max_chars:
        return t
    chunk = t[:max_chars]
    space = chunk.rfind(" ")
    if space > 40:
        chunk = chunk[:space]
    return chunk.strip()


def build_rewrite_jobs(
    sections: List[Dict[str, Any]],
    *,
    max_source_chars: int,
    overlap_chars: int,
) -> List[_RewriteJob]:
    """One job per section with prev/next overlap snippets for continuity."""
    jobs: List[_RewriteJob] = []
    for idx, sec in enumerate(sections):
        sid = str(sec.get("section_id") or idx + 1)
        heading = str(sec.get("heading") or "").strip()
        source = str(sec.get("text") or "")[:max_source_chars]

        prev_heading = ""
        prev_overlap = ""
        if idx > 0:
            prev = sections[idx - 1]
            prev_heading = str(prev.get("heading") or "").strip()
            prev_overlap = _overlap_tail(str(prev.get("text") or ""), max_chars=overlap_chars)

        next_heading = ""
        next_overlap = ""
        if idx + 1 < len(sections):
            nxt = sections[idx + 1]
            next_heading = str(nxt.get("heading") or "").strip()
            next_overlap = _overlap_head(str(nxt.get("text") or ""), max_chars=overlap_chars)

        jobs.append(
            _RewriteJob(
                index=idx + 1,
                section_id=sid,
                heading=heading,
                source_text=source,
                prev_heading=prev_heading,
                prev_overlap=prev_overlap,
                next_heading=next_heading,
                next_overlap=next_overlap,
            )
        )
    return jobs


def resolve_parallel_workers(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 1:
        return explicit
    raw = os.environ.get(
        "REWRITE_PARALLEL_WORKERS",
        str(getattr(config, "REWRITE_PARALLEL_WORKERS", 8)),
    )
    try:
        n = int(raw or "1")
    except ValueError:
        n = 1
    return max(1, n)


def resolve_context_overlap_chars(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 0:
        return explicit
    raw = os.environ.get(
        "REWRITE_CONTEXT_OVERLAP_CHARS",
        str(getattr(config, "REWRITE_CONTEXT_OVERLAP_CHARS", 600)),
    )
    try:
        n = int(raw or "0")
    except ValueError:
        n = 0
    return max(0, n)


def rewrite_sections_parallel(
    sections: List[Dict[str, Any]],
    *,
    user_instruction: str,
    system: str,
    generate: Callable[[str, str], str],
    max_tokens: int = 1200,
    max_source_chars: Optional[int] = None,
    overlap_chars: Optional[int] = None,
    workers: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    """
    Rewrite all sections in parallel. Returns section_id -> notes text.
    Final document order is unchanged — callers assemble via 15f hierarchy.
    """
    _ = max_tokens  # reserved for callers passing through generate closures
    if not sections:
        return {}

    cap = max_source_chars or int(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000)
    overlap = resolve_context_overlap_chars(overlap_chars)
    pool_size = resolve_parallel_workers(workers)

    jobs = build_rewrite_jobs(sections, max_source_chars=cap, overlap_chars=overlap)
    if pool_size <= 1 or len(jobs) <= 1:
        return _rewrite_sequential(
            jobs,
            user_instruction=user_instruction,
            system=system,
            generate=generate,
            on_progress=on_progress,
        )

    rewritten: Dict[str, str] = {}
    done = 0
    lock = threading.Lock()
    total = len(jobs)

    def _run(job: _RewriteJob) -> Tuple[str, str]:
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
        return job.section_id, text

    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        futures = {pool.submit(_run, job): job for job in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                sid, text = fut.result()
            except Exception as exc:
                logger.warning("Parallel rewrite failed for %s: %s", job.section_id, exc)
                sid, text = job.section_id, ""
            if text:
                rewritten[sid] = text
            with lock:
                done += 1
                if on_progress:
                    on_progress(done, total, job.heading)

    return rewritten


def _rewrite_sequential(
    jobs: List[_RewriteJob],
    *,
    user_instruction: str,
    system: str,
    generate: Callable[[str, str], str],
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    rewritten: Dict[str, str] = {}
    total = len(jobs)
    for job in jobs:
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
        if text:
            rewritten[job.section_id] = text
        if on_progress:
            on_progress(job.index, total, job.heading)
    return rewritten
