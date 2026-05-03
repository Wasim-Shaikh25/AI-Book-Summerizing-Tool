from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from src.core.models import NormalizedLine

_PAGE_NUM_PATTERNS = [
    re.compile(r"^\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s*:?\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*-\s*\d+\s*-\s*$", re.IGNORECASE),
    # Spaced-letter variants: "29| P a g e", "13 | P a g e", "P a g e | 29"
    re.compile(r"^\s*\d+\s*\|\s*[Pp]\s*[Aa]\s*[Gg]\s*[Ee]\s*$"),
    re.compile(r"^\s*[Pp]\s*[Aa]\s*[Gg]\s*[Ee]\s*\|?\s*\d+\s*$"),
    # Plain spaced "P a g e" without a number (just the word)
    re.compile(r"^\s*[Pp]\s*[Aa]\s*[Gg]\s*[Ee]\s*$"),
]


def _normalize_for_header_footer(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\d+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_in_top_margin(line: NormalizedLine) -> bool:
    return line.page_height > 0 and line.y_pos <= (line.page_height * 0.08)


def _is_in_bottom_margin(line: NormalizedLine) -> bool:
    return line.page_height > 0 and line.y_pos >= (line.page_height * 0.92)


def _margin_bucket(line: NormalizedLine) -> str:
    """
    Coarse positional bucketing for deterministic noise decisions.
    """
    if line.page_height <= 0:
        return "unknown"
    if _is_in_top_margin(line):
        return "top"
    if _is_in_bottom_margin(line):
        return "bottom"
    return "body"


def _looks_like_page_number(text: str) -> bool:
    for rx in _PAGE_NUM_PATTERNS:
        if rx.match(text or ""):
            return True
    return False


def _should_protect_from_noise(line: NormalizedLine) -> bool:
    """
    Protection rule:
    - Don't mark potential headings as noise just because they're visually emphasized.
    - Exception: page numbers should always be eligible for noise detection even if bold/centered.
    NOTE: Repeated headers/footers are handled separately in mark_noise() and can be marked even if bold/centered.
    """
    if _looks_like_page_number(line.text) or re.search(r"\bpage\s+\d+\s+of\s+\d+\b", (line.text or "").lower()):
        return False
    return bool(line.is_bold or line.large_font or line.centered)


def mark_noise(lines: Sequence[NormalizedLine]) -> tuple[List[NormalizedLine], List[Dict[str, Any]]]:
    """
    Deterministic noise marking (never deletes lines).

    Updated rules (deterministic):
    - For each page, inspect the top N and bottom N lines (N=3) by y_pos.
    - Candidate noise lines come only from these margin samples.
    - Mark as noise if:
        1) looks like a page number (any margin) AND appears consistently across pages
           (by normalized form + coarse margin bucket), OR
        2) header/footer text repeats on >30% of pages (by normalized text + margin bucket).
    - Still respects "protected" lines: bold OR large_font OR centered => never marked noise.

    Returns:
      (updated_lines, log_entries)
    """
    if not lines:
        return [], []

    N = 3

    # Page universe
    pages = sorted({ln.page_number for ln in lines if ln.page_number is not None})
    total_pages = len(pages)
    # Header/footer repetition rule (updated): mark as noise if it appears on 20+ pages.
    threshold_pages = 20 if total_pages >= 20 else total_pages if total_pages > 0 else 0

    # Group lines by page
    by_page: Dict[int, List[NormalizedLine]] = {}
    for ln in lines:
        if ln.page_number is None:
            continue
        by_page.setdefault(int(ln.page_number), []).append(ln)

    # Select top/bottom N sample lines per page.
    # Important: we INCLUDE even bold/centered lines here, otherwise repeated headers/footers won't be detected.
    sampled_line_ids: set[int] = set()
    sampled: List[NormalizedLine] = []

    for p, page_lines in by_page.items():
        # ignore empty text lines for sampling so headers/footers don't get pushed out by blanks
        non_empty = [ln for ln in page_lines if (ln.text or "").strip()]
        page_lines_sorted = sorted(non_empty, key=lambda x: (x.y_pos, x.line_id))
        top = page_lines_sorted[:N]
        bottom = page_lines_sorted[-N:] if len(page_lines_sorted) > N else page_lines_sorted

        for ln in list(top) + list(bottom):
            if ln.line_id in sampled_line_ids:
                continue
            sampled_line_ids.add(ln.line_id)
            sampled.append(ln)

    # Build repetition stats over sampled lines
    # header/footer repetition (normalized text + bucket)
    text_occurrences: Dict[tuple[str, str], set[int]] = {}
    # page-number repetition (normalized digits-stripped key + bucket)
    page_num_occurrences: Dict[tuple[str, str], set[int]] = {}

    for ln in sampled:
        bucket = _margin_bucket(ln)
        if bucket not in ("top", "bottom"):
            continue

        key_text = _normalize_for_header_footer(ln.text)
        if key_text:
            text_occurrences.setdefault((key_text, bucket), set()).add(int(ln.page_number))

        # Detect common page number formats, including "Page X of Y"
        if _looks_like_page_number(ln.text) or re.search(r"\bpage\s+\d+\s+of\s+\d+\b", (ln.text or "").lower()):
            # Keep a stable "page number family" key.
            key_num = "__page_number__"
            page_num_occurrences.setdefault((key_num, bucket), set()).add(int(ln.page_number))

    frequent_text_keys = {
        k for k, pset in text_occurrences.items() if threshold_pages and len(pset) >= threshold_pages
    }
    # Page-number detection should still work on single-page PDFs: if a line looks like a page number
    # in a margin, mark it as noise even if it appears on only 1 page.
    frequent_page_num_keys = {
        k
        for k, pset in page_num_occurrences.items()
        if (threshold_pages and len(pset) >= threshold_pages) or (total_pages == 1 and len(pset) == 1)
    }

    out: List[NormalizedLine] = []
    logs: List[Dict[str, Any]] = []

    for ln in lines:
        decision = "keep"
        noise_type = None
        reason = None

        if ln.page_number is not None and ln.line_id in sampled_line_ids:
            bucket = _margin_bucket(ln)
            if bucket in ("top", "bottom"):
                norm_text = _normalize_for_header_footer(ln.text)

                # 1) Page number noise (any margin) if repeated across pages in same bucket
                looks_like_page_num = _looks_like_page_number(ln.text) or re.search(
                    r"\bpage\s+\d+\s+of\s+\d+\b", (ln.text or "").lower()
                )
                if looks_like_page_num and ("__page_number__", bucket) in frequent_page_num_keys:
                    decision = "noise"
                    noise_type = "page_number"
                    pages_hit = len(page_num_occurrences.get(("__page_number__", bucket), set()))
                    reason = f"page_number_pattern + repeats_on_{pages_hit}_pages + bucket={bucket}"

                # 2) Header/Footer repetition noise (allow even if bold/centered/large_font, since it's margin + repeats)
                if decision == "keep" and (norm_text, bucket) in frequent_text_keys:
                    decision = "noise"
                    noise_type = "header" if bucket == "top" else "footer"
                    pages_hit = len(text_occurrences.get((norm_text, bucket), set()))
                    reason = f"repeats_on_{pages_hit}_pages(>=2) + bucket={bucket}"

        # 3) Spaced-letter page footer: "29| P a g e" etc. — appears on many pages
        # These can have y_pos=0.0 due to PDF coordinate quirks and miss the margin sampler.
        if decision == "keep" and _looks_like_page_number(ln.text):
            norm_key = _normalize_for_header_footer(ln.text)  # "| p a g e" or "p a g e"
            # Count how many pages this normalised form appeared on (any bucket)
            pages_with_this = sum(
                len(pset)
                for (k, _b), pset in text_occurrences.items()
                if k == norm_key
            )
            if pages_with_this == 0:
                # Fall back: count raw occurrences across all lines in this run
                pages_with_this = sum(
                    1 for l2 in lines
                    if _normalize_for_header_footer(l2.text) == norm_key
                       and l2.page_number != ln.page_number
                )
            min_pages = max(2, threshold_pages // 2)
            if pages_with_this >= min_pages:
                decision = "noise"
                noise_type = "page_number"
                reason = f"spaced_page_pattern + seen_on_{pages_with_this}_pages"

        if decision == "noise":
            out.append(
                NormalizedLine(
                    line_id=ln.line_id,
                    text=ln.text,
                    page_number=ln.page_number,
                    y_pos=ln.y_pos,
                    page_height=ln.page_height,
                    font_size=ln.font_size,
                    is_bold=ln.is_bold,
                    x_center=ln.x_center,
                    page_width=ln.page_width,
                    vertical_gap_above=ln.vertical_gap_above,
                    is_link=ln.is_link,
                    centered=ln.centered,
                    large_font=ln.large_font,
                    large_gap=ln.large_gap,
                    is_noise=True,
                    noise_type=noise_type,
                )
            )
            bucket = _margin_bucket(ln)
            logs.append(
                {
                    "line_id": ln.line_id,
                    "text": ln.text,
                    "page_number": ln.page_number,
                    "decision": "noise",
                    "noise_type": noise_type,
                    "reason": reason,
                    "margin_position": bucket,
                    "confidence": 1.0,
                }
            )
        else:
            out.append(ln)

    # Prepend a small deterministic summary block for quick debugging
    # Stage log should contain only per-line records per spec.
    return out, logs
