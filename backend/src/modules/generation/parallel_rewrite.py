"""Parallel section rewrite with adjacent context overlap."""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.modules.generation.rewrite_fidelity import (
    fidelity_strict_prompt_prefix,
    get_last_fidelity_stats,
    needs_regeneration,
    reset_fidelity_stats,
    section_overlap_score,
    source_is_low_grounding,
)
from src.modules.generation.rewrite_prompts import (
    build_section_user_prompt_with_context,
    normalize_rewritten_section,
)
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
    chapter_heading: str = ""
    subheadings: tuple[str, ...] = ()


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

        sub_labels = tuple(
            h
            for s in (sec.get("subheadings") or [])
            if (h := (s["heading"].strip() if isinstance(s, dict) else str(s).strip()))
        )
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
                chapter_heading=str(sec.get("chapter_heading") or "").strip(),
                subheadings=sub_labels,
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


def _semantic_split_enabled() -> bool:
    raw = os.environ.get("SEMANTIC_SPLIT_ENABLED", "0").strip().lower()
    return raw in {"1", "true", "yes"}


def _semantic_split_threshold() -> int:
    try:
        return int(os.environ.get("SEMANTIC_SPLIT_THRESHOLD", "2000"))
    except ValueError:
        return 2000


def _build_prompt(
    job: _RewriteJob,
    *,
    user_instruction: str,
    overlap_chars: int,
    strict: bool = False,
    semantic_chunks: Optional[List[dict]] = None,
    rag_context: Optional[str] = None,
) -> str:
    prefix = fidelity_strict_prompt_prefix() if strict else ""
    body = build_section_user_prompt_with_context(
        user_instruction=user_instruction,
        heading=job.heading,
        source_text=job.source_text,
        prev_heading=job.prev_heading,
        prev_overlap="" if strict else job.prev_overlap,
        next_heading=job.next_heading,
        next_overlap="" if strict else job.next_overlap,
        chapter_heading=job.chapter_heading,
        subheadings=list(job.subheadings),
        semantic_chunks=semantic_chunks,
    )
    result = prefix + body
    if rag_context:
        result += (
            "\n\n---\nRelated context (do not repeat, use for continuity only):\n"
            + rag_context
            + "\n---"
        )
    return result


def _rewrite_job(
    job: _RewriteJob,
    *,
    user_instruction: str,
    system: str,
    generate: Callable[[str, str], str],
    overlap_chars: int,
) -> Tuple[str, str]:
    # Index/contents-style or thin sources give the model nothing to ground on,
    # so it expands from prior knowledge. Force strict source-only mode up front.
    low_grounding = source_is_low_grounding(job.source_text)
    if low_grounding:
        stats = get_last_fidelity_stats()
        stats.low_grounding_sections += 1

    # Opt-in: semantic splitting pre-LLM. Skipped for low-grounding sections where
    # strict mode is already enforced and chunking would reduce source grounding.
    semantic_chunks: Optional[List[dict]] = None
    if _semantic_split_enabled() and not low_grounding:
        try:
            from src.modules.generation.semantic_splitter import semantic_split_section as _split_fn

            chunks = _split_fn(
                job.source_text,
                job.heading,
                threshold=_semantic_split_threshold(),
                max_chunks=4,
                overlap_sents=1,
            )
            if len(chunks) > 1:
                semantic_chunks = chunks
        except Exception:
            semantic_chunks = None

    # Opt-in: inject same-book RAG context for rewrite continuity.
    rag_context: Optional[str] = None
    if os.environ.get("REWRITE_RAG_CONTEXT", "0").strip() == "1" and not low_grounding:
        try:
            from src.modules.rag.service import RagService

            _rag = RagService()
            _candidates = _rag.retrieve(
                job.heading,
                book_id=getattr(job, "book_id", ""),
                sections=[],
                top_k=3,
            )
            # Exclude the current section to avoid self-reference
            _candidates = [c for c in _candidates if c.get("section_id") != job.section_id][:2]
            if _candidates:
                rag_context = "\n".join(c.get("text", "")[:200] for c in _candidates)[:400]
        except Exception:
            rag_context = None

    prompt = _build_prompt(
        job,
        user_instruction=user_instruction,
        overlap_chars=0 if low_grounding else overlap_chars,
        strict=low_grounding,
        semantic_chunks=semantic_chunks,
        rag_context=rag_context,
    )
    text = normalize_rewritten_section(
        (generate(system, prompt) or "").strip(),
        user_instruction=user_instruction,
        heading=job.heading,
        chapter_heading=job.chapter_heading,
    )
    attempts = 1
    score = section_overlap_score(source=job.source_text, generated=text)

    if not low_grounding and needs_regeneration(score) and job.source_text.strip():
        retry_prompt = _build_prompt(
            job,
            user_instruction=user_instruction,
            overlap_chars=0,
            strict=True,
        )
        retry_text = normalize_rewritten_section(
            (generate(system, retry_prompt) or "").strip(),
            user_instruction=user_instruction,
            heading=job.heading,
            chapter_heading=job.chapter_heading,
        )
        attempts = 2
        retry_score = section_overlap_score(source=job.source_text, generated=retry_text)
        if retry_score > score and retry_text.strip():
            text = retry_text
            score = retry_score
            stats = get_last_fidelity_stats()
            stats.drift_regenerated += 1

    stats = get_last_fidelity_stats()
    stats.attempts_per_section[job.section_id] = attempts
    _ = score
    return job.section_id, text


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

    reset_fidelity_stats()
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
            overlap_chars=overlap,
            on_progress=on_progress,
        )

    rewritten: Dict[str, str] = {}
    done = 0
    lock = threading.Lock()
    total = len(jobs)

    def _run(job: _RewriteJob) -> Tuple[str, str]:
        return _rewrite_job(
            job,
            user_instruction=user_instruction,
            system=system,
            generate=generate,
            overlap_chars=overlap,
        )

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
    overlap_chars: int,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    rewritten: Dict[str, str] = {}
    total = len(jobs)
    for job in jobs:
        sid, text = _rewrite_job(
            job,
            user_instruction=user_instruction,
            system=system,
            generate=generate,
            overlap_chars=overlap_chars,
        )
        if text:
            rewritten[sid] = text
        if on_progress:
            on_progress(job.index, total, job.heading)
    return rewritten
