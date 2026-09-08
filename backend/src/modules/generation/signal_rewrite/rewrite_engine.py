"""Signal-Sections rewrite engine.

One ``LlmChatClient`` call per high-signal section through OpenRouter
(``google/gemini-2.5-flash-lite-preview`` by default, overridable).

* No prompt construction here — the prompt comes from ``hierarchy_prompt``.
* No section-id mangling, no chapter renumbering.
* Every output is post-validated through ``inner_heading_decider`` so the
  model cannot invent ``###`` sub-topics beyond the declared inner_headings.
* Parallel via ``concurrent.futures.ThreadPoolExecutor`` (existing pattern in
  ``parallel_rewrite.py``).
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.modules.pipeline.llm_chat_client import LlmChatClient
from src.modules.generation.signal_rewrite.hierarchy_prompt import (
    build_signal_section_prompt,
    build_signal_system_prompt,
)
from src.modules.generation.signal_rewrite.inner_heading_decider import (
    DeciderReport,
    validate_inner_headings,
)

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
DEFAULT_PROVIDER = "openrouter"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2500
DEFAULT_OVERLAP_CHARS = 600
DEFAULT_WORKERS = 4


@dataclass
class SectionRewriteResult:
    chapter_id: str
    section_id: str
    heading: str
    model: str
    success: bool
    body_md: str
    elapsed_s: float
    decider: DeciderReport = field(default_factory=DeciderReport)
    error: str = ""
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "section_id": self.section_id,
            "heading": self.heading,
            "model": self.model,
            "success": bool(self.success),
            "body_md": self.body_md,
            "elapsed_s": round(float(self.elapsed_s), 3),
            "decider": self.decider.to_dict(),
            "error": self.error,
            "attempts": int(self.attempts),
        }


def _resolve_int_env(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        return int(default)
    try:
        return int(v)
    except ValueError:
        return int(default)


def _resolve_float_env(name: str, default: float) -> float:
    v = (os.getenv(name) or "").strip()
    if not v:
        return float(default)
    try:
        return float(v)
    except ValueError:
        return float(default)


def resolve_signal_rewrite_settings() -> Dict[str, Any]:
    """Read ``SIGNAL_REWRITE_*`` env vars; fall back to project defaults."""
    return {
        "provider": (os.getenv("SIGNAL_REWRITE_PROVIDER") or DEFAULT_PROVIDER).strip().lower(),
        "model": (os.getenv("SIGNAL_REWRITE_MODEL") or DEFAULT_MODEL).strip(),
        "temperature": _resolve_float_env("SIGNAL_REWRITE_TEMPERATURE", DEFAULT_TEMPERATURE),
        "max_tokens": _resolve_int_env("SIGNAL_REWRITE_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        "overlap_chars": _resolve_int_env("SIGNAL_REWRITE_OVERLAP_CHARS", DEFAULT_OVERLAP_CHARS),
        "workers": max(1, _resolve_int_env("SIGNAL_REWRITE_PARALLEL_WORKERS", DEFAULT_WORKERS)),
        "user_instruction": (
            os.getenv("SIGNAL_REWRITE_USER_INSTRUCTION")
            or os.getenv("REWRITE_USER_INSTRUCTION")
            or ""
        ).strip(),
    }


@dataclass
class _SectionJob:
    chapter_no: int
    chapter_heading: str
    section_no: int
    chapter_id: str
    section: Dict[str, Any]
    prev_section: Optional[Dict[str, Any]]
    next_section: Optional[Dict[str, Any]]


def _flatten_sections_with_chapters(hierarchy: Dict[str, Any]) -> List[_SectionJob]:
    """Walk the hierarchy and produce one ``_SectionJob`` per section in PDF order."""
    jobs: List[_SectionJob] = []
    flat: List[Dict[str, Any]] = []  # for prev/next lookup
    for ch_idx, ch in enumerate(hierarchy.get("chapters") or [], start=1):
        ch_heading = str(ch.get("heading") or "").strip()
        ch_id = str(ch.get("chapter_id") or f"C{ch_idx}")
        for sec_idx, sec in enumerate(ch.get("sections") or [], start=1):
            flat.append(
                {
                    "chapter_no": ch_idx,
                    "chapter_heading": ch_heading,
                    "chapter_id": ch_id,
                    "section_no": sec_idx,
                    "section": sec,
                }
            )

    for i, row in enumerate(flat):
        prev_section = flat[i - 1]["section"] if i > 0 else None
        next_section = flat[i + 1]["section"] if i + 1 < len(flat) else None
        jobs.append(
            _SectionJob(
                chapter_no=int(row["chapter_no"]),
                chapter_heading=row["chapter_heading"],
                section_no=int(row["section_no"]),
                chapter_id=row["chapter_id"],
                section=row["section"],
                prev_section=prev_section,
                next_section=next_section,
            )
        )
    return jobs


def _build_job_prompt(
    *,
    job: _SectionJob,
    book_title: str,
    overlap_chars: int,
) -> str:
    sec = job.section
    prev = job.prev_section or {}
    nxt = job.next_section or {}
    return build_signal_section_prompt(
        book_title=book_title,
        chapter_number=job.chapter_no,
        chapter_heading=job.chapter_heading,
        section_number=job.section_no,
        section_heading=str(sec.get("heading") or ""),
        section_page_start=sec.get("page_number"),
        section_page_end=sec.get("page_number"),
        source_text=str(sec.get("body") or ""),
        inner_headings=list(sec.get("inner_headings") or []),
        prev_section_heading=str(prev.get("heading") or ""),
        prev_section_tail=str(prev.get("body") or ""),
        next_section_heading=str(nxt.get("heading") or ""),
        next_section_head=str(nxt.get("body") or ""),
        overlap_chars=int(overlap_chars),
    )


def _run_one(
    *,
    job: _SectionJob,
    book_title: str,
    client: LlmChatClient,
    provider: str,
    system_prompt: str,
    max_tokens: int,
    overlap_chars: int,
) -> SectionRewriteResult:
    sec = job.section
    heading = str(sec.get("heading") or "")
    started = time.monotonic()

    # Skip LLM if there is literally no body to rewrite — emit empty body so
    # the exporter writes the heading + a "no content" notice (preserves structure).
    source_text = str(sec.get("body") or "").strip()
    if not source_text:
        return SectionRewriteResult(
            chapter_id=job.chapter_id,
            section_id=str(sec.get("section_id") or ""),
            heading=heading,
            model="",
            success=False,
            body_md="",
            elapsed_s=time.monotonic() - started,
            decider=DeciderReport(notes=["empty_source"]),
            error="empty_source",
            attempts=0,
        )

    user_prompt = _build_job_prompt(
        job=job, book_title=book_title, overlap_chars=overlap_chars
    )

    attempts = 0
    text: Optional[str] = None
    last_error = ""
    for attempt in range(2):
        attempts += 1
        try:
            text = client.chat_with_provider(
                provider,
                system=system_prompt,
                user=user_prompt,
                max_tokens=int(max_tokens),
            )
            if text:
                break
            last_error = "empty_response"
        except Exception as exc:  # pragma: no cover — network errors
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Signal rewrite call failed for %s (attempt %d): %s",
                sec.get("section_id"),
                attempt + 1,
                exc,
            )
        time.sleep(0.5 * (attempt + 1))

    elapsed = time.monotonic() - started
    if not text:
        return SectionRewriteResult(
            chapter_id=job.chapter_id,
            section_id=str(sec.get("section_id") or ""),
            heading=heading,
            model=client.last_model_label(),
            success=False,
            body_md="",
            elapsed_s=elapsed,
            decider=DeciderReport(notes=[last_error or "no_text"]),
            error=last_error or "no_text",
            attempts=attempts,
        )

    cleaned, report = validate_inner_headings(
        generated_text=text,
        section_heading=heading,
        inner_headings=list(sec.get("inner_headings") or []),
    )
    return SectionRewriteResult(
        chapter_id=job.chapter_id,
        section_id=str(sec.get("section_id") or ""),
        heading=heading,
        model=client.last_model_label(),
        success=bool(cleaned),
        body_md=cleaned,
        elapsed_s=elapsed,
        decider=report,
        attempts=attempts,
    )


def rewrite_signal_sections(
    *,
    hierarchy: Dict[str, Any],
    settings: Optional[Dict[str, Any]] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    client: Optional[LlmChatClient] = None,
) -> List[SectionRewriteResult]:
    """Run one rewrite call per section in the signal hierarchy.

    Args:
        hierarchy: payload from ``pdf_hierarchy_assembler.assemble_hierarchy``.
        settings: optional overrides; defaults come from
            ``resolve_signal_rewrite_settings()``.
        on_progress: callback ``(done, total, section_id)`` called after each
            section completes.
        client: optional pre-built ``LlmChatClient``. Useful for tests; in
            production we build one from settings.

    Returns one ``SectionRewriteResult`` per section in original PDF order.
    """
    cfg = dict(resolve_signal_rewrite_settings())
    if settings:
        cfg.update({k: v for k, v in settings.items() if v is not None})

    if client is None:
        client = LlmChatClient(
            cfg["provider"],
            model_override=cfg["model"],
            temperature=float(cfg["temperature"]),
        )
    system_prompt = build_signal_system_prompt(user_instruction=cfg["user_instruction"])
    book_title = str(hierarchy.get("book_title") or "")
    jobs = _flatten_sections_with_chapters(hierarchy)
    total = len(jobs)
    if total == 0:
        return []

    results: Dict[str, SectionRewriteResult] = {}
    workers = max(1, int(cfg["workers"]))

    if workers == 1:
        for i, job in enumerate(jobs, start=1):
            res = _run_one(
                job=job,
                book_title=book_title,
                client=client,
                provider=cfg["provider"],
                system_prompt=system_prompt,
                max_tokens=int(cfg["max_tokens"]),
                overlap_chars=int(cfg["overlap_chars"]),
            )
            results[res.section_id or f"S{i}"] = res
            if on_progress is not None:
                on_progress(i, total, res.section_id)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_job = {
                pool.submit(
                    _run_one,
                    job=job,
                    book_title=book_title,
                    client=client,
                    provider=cfg["provider"],
                    system_prompt=system_prompt,
                    max_tokens=int(cfg["max_tokens"]),
                    overlap_chars=int(cfg["overlap_chars"]),
                ): job
                for job in jobs
            }
            done = 0
            for fut in as_completed(future_to_job):
                done += 1
                try:
                    res = fut.result()
                except Exception as exc:  # pragma: no cover — defensive
                    job = future_to_job[fut]
                    res = SectionRewriteResult(
                        chapter_id=job.chapter_id,
                        section_id=str(job.section.get("section_id") or ""),
                        heading=str(job.section.get("heading") or ""),
                        model="",
                        success=False,
                        body_md="",
                        elapsed_s=0.0,
                        decider=DeciderReport(notes=[f"exception: {exc}"]),
                        error=str(exc),
                        attempts=0,
                    )
                results[res.section_id or f"S{done}"] = res
                if on_progress is not None:
                    on_progress(done, total, res.section_id)

    # Re-order results in PDF order (matches the jobs list).
    ordered: List[SectionRewriteResult] = []
    for job in jobs:
        sid = str(job.section.get("section_id") or "")
        if sid in results:
            ordered.append(results[sid])
    return ordered
