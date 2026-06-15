"""Rewrite bundled sections in parallel and split output back to section_ids."""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Sequence

from src.modules.generation.rewrite_prompts import build_bundle_user_prompt, normalize_rewritten_section
from src.modules.generation.section_bundler import RewriteBundle, build_rewrite_bundles
from src.modules.generation.parallel_rewrite import ProgressCallback, resolve_parallel_workers

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str, str], str]

_SID_HEADING = re.compile(
    r"^###\s+(.+?)\s*(?:<!--\s*sid:([A-Za-z0-9_]+)\s*-->)?\s*$",
    re.MULTILINE,
)


def parse_bundled_rewrite(
    raw: str,
    bundle: RewriteBundle,
    *,
    user_instruction: str = "",
) -> Dict[str, str]:
    """Split bundled LLM output into section_id -> body using sid tags or headings."""
    text = (raw or "").strip()
    if not text:
        return {}

    by_sid: Dict[str, str] = {}
    parts = re.split(r"(?=^###\s+)", text, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part.startswith("###"):
            continue
        first_line, _, rest = part.partition("\n")
        m = _SID_HEADING.match(first_line)
        if not m:
            continue
        heading = (m.group(1) or "").strip()
        sid = (m.group(2) or "").strip()
        body = rest.strip()
        if not body:
            continue
        if sid:
            by_sid[sid] = body
            continue
        for i, h in enumerate(bundle.headings):
            if h.lower() == heading.lower() or heading.lower() in h.lower() or h.lower() in heading.lower():
                sid_guess = bundle.section_ids[i]
                by_sid[sid_guess] = body
                break

    if len(by_sid) < len(bundle.section_ids):
        for sid in bundle.section_ids:
            if sid in by_sid:
                continue
            tag = f"<!-- sid:{sid} -->"
            idx = text.find(tag)
            if idx == -1:
                continue
            chunk = text[idx + len(tag) :].lstrip()
            nxt = re.search(r"\n###\s+", chunk)
            body = chunk[: nxt.start()].strip() if nxt else chunk.strip()
            if body:
                by_sid[sid] = body

    return {
        sid: normalize_rewritten_section(body, user_instruction=user_instruction)
        for sid, body in by_sid.items()
    }


def rewrite_bundles_parallel(
    sections: Sequence[Dict[str, Any]],
    *,
    user_instruction: str,
    system: str,
    generate: GenerateFn,
    max_source_chars: int,
    bundle_size: Optional[int] = None,
    workers: Optional[int] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, str]:
    """Rewrite grouped sections; returns flat section_id -> notes map."""
    bundles = build_rewrite_bundles(sections, bundle_size=bundle_size)
    if not bundles:
        return {}

    pool_size = resolve_parallel_workers(workers)
    rewritten: Dict[str, str] = {}
    done = 0
    lock = threading.Lock()
    total = len(bundles)

    def _run(bundle: RewriteBundle) -> Dict[str, str]:
        prompt = build_bundle_user_prompt(
            user_instruction=user_instruction,
            bundle=bundle,
            max_source_chars=max_source_chars,
        )
        raw = generate(system, prompt)
        return parse_bundled_rewrite(raw or "", bundle, user_instruction=user_instruction)

    if pool_size <= 1 or total <= 1:
        for bundle in bundles:
            parsed = _run(bundle)
            rewritten.update(parsed)
            if on_progress:
                on_progress(done + 1, total, bundle.label)
            done += 1
        return rewritten

    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        futures = {pool.submit(_run, b): b for b in bundles}
        for fut in as_completed(futures):
            bundle = futures[fut]
            try:
                parsed = fut.result()
                rewritten.update(parsed)
            except Exception as exc:
                logger.warning("Bundle rewrite failed %s: %s", bundle.bundle_id, exc)
            with lock:
                done += 1
                if on_progress:
                    on_progress(done, total, bundle.label)

    return rewritten
