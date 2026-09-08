"""Group consecutive sections (within a chapter) for combined rewrite calls."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from src.shared import config


@dataclass(frozen=True)
class RewriteBundle:
    """A batch of sections rewritten in one LLM call."""

    bundle_id: str
    chapter_heading: str
    section_ids: List[str]
    headings: List[str]
    sections: List[Dict[str, Any]]

    @property
    def label(self) -> str:
        if len(self.headings) == 1:
            return self.headings[0]
        return f"{self.headings[0]} … ({len(self.headings)} topics)"


def resolve_bundle_size(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 0:
        return max(1, explicit) if explicit > 1 else explicit
    raw = os.environ.get("REWRITE_BUNDLE_SIZE", "").strip()
    if raw:
        try:
            n = int(raw)
            return max(0, n)
        except ValueError:
            pass
    from src.modules.generation.rewrite_prompts import is_compact_exam_mode

    if is_compact_exam_mode():
        return int(getattr(config, "REWRITE_BUNDLE_SIZE", 6) or 6)
    return int(getattr(config, "REWRITE_BUNDLE_SIZE", 1) or 1)


def resolve_bundle_max_chars(explicit: Optional[int] = None) -> int:
    if explicit is not None and explicit >= 0:
        return explicit
    raw = os.environ.get(
        "REWRITE_BUNDLE_MAX_CHARS",
        str(getattr(config, "REWRITE_BUNDLE_MAX_CHARS", 12000)),
    )
    try:
        return max(1000, int(raw or "12000"))
    except ValueError:
        return 12000


def bundle_export_enabled() -> bool:
    return os.environ.get(
        "REWRITE_BUNDLE_EXPORT",
        str(getattr(config, "REWRITE_BUNDLE_EXPORT", "1")),
    ).strip().lower() not in {"0", "false", "no", "n"}


def resolve_chapter_page_breaks(
    *,
    compact_toc: bool = False,
    use_bundles: bool = False,
) -> bool:
    """
    Whether each chapter starts on a new page in Word/markdown export.

    REWRITE_CHAPTER_PAGE_BREAKS:
      - unset / auto: off for compact/bundled exports (avoids blank pages), on otherwise
      - 1 / true: always on
      - 0 / false: always off
    """
    raw = os.environ.get(
        "REWRITE_CHAPTER_PAGE_BREAKS",
        str(getattr(config, "REWRITE_CHAPTER_PAGE_BREAKS", "auto") or "auto"),
    ).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return not (compact_toc or use_bundles)


def build_rewrite_bundles(
    sections: Sequence[Dict[str, Any]],
    *,
    bundle_size: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> List[RewriteBundle]:
    """
    Group consecutive sections sharing the same chapter_heading.
    Never splits a chapter across bundles unless char cap forces a flush.
    """
    size = resolve_bundle_size(bundle_size)
    if size <= 1:
        return [
            RewriteBundle(
                bundle_id=f"B{i}",
                chapter_heading=str(sec.get("chapter_heading") or ""),
                section_ids=[str(sec.get("section_id") or i)],
                headings=[str(sec.get("heading") or "").strip()],
                sections=[dict(sec)],
            )
            for i, sec in enumerate(sections, start=1)
        ]

    char_cap = resolve_bundle_max_chars(max_chars)
    bundles: List[RewriteBundle] = []
    current_secs: List[Dict[str, Any]] = []
    current_chars = 0
    current_chapter = ""
    bundle_no = 0

    def _flush() -> None:
        nonlocal bundle_no, current_secs, current_chars
        if not current_secs:
            return
        bundle_no += 1
        sids = [str(s.get("section_id") or "") for s in current_secs]
        headings = [str(s.get("heading") or "").strip() for s in current_secs]
        bundles.append(
            RewriteBundle(
                bundle_id=f"B{bundle_no}",
                chapter_heading=current_chapter,
                section_ids=sids,
                headings=headings,
                sections=list(current_secs),
            )
        )
        current_secs = []
        current_chars = 0

    for sec in sections:
        ch = str(sec.get("chapter_heading") or "")
        text = str(sec.get("text") or "")
        sec_chars = len(text)

        if current_secs and ch != current_chapter:
            _flush()
            current_chapter = ch
        elif not current_secs:
            current_chapter = ch

        would_exceed = current_secs and (
            len(current_secs) >= size or (current_chars + sec_chars > char_cap and len(current_secs) >= 1)
        )
        if would_exceed:
            _flush()
            current_chapter = ch

        current_secs.append(dict(sec))
        current_chars += sec_chars

        if len(current_secs) >= size:
            _flush()

    _flush()
    return bundles
