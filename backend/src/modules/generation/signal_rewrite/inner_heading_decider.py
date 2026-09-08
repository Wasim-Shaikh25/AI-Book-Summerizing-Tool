r"""Validate and fix LLM output for one signal section.

Rules enforced after the LLM responds:
1. Strip an accidental top ``# ...`` / ``## ...`` line — the exporter prints
   the section title; the model must not.
2. Strip code-fence wrapping (except valid ```mermaid blocks).
3. Every ``### <inner heading>`` line in the output must match (by normalized
   comparison) one of the inner headings declared for this section. Any
   ``### ...`` that does not match is downgraded to plain bold text + paragraph
   so we do not invent new sub-topics.
4. Empty or whitespace-only output stays empty (caller decides retry).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple


_LEADING_HASH_RE = re.compile(r"^\s*#{1,2}\s+", re.MULTILINE)
_INNER_HEADING_RE = re.compile(r"^###\s+(.*?)\s*$", re.MULTILINE)
_FENCE_OPEN_RE = re.compile(r"^\s*```(\w+)?\s*$")
_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip()).lower()


@dataclass
class DeciderReport:
    inner_emitted: int = 0
    inner_accepted: int = 0
    inner_downgraded: int = 0
    top_level_stripped: int = 0
    fence_unwrapped: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inner_emitted": int(self.inner_emitted),
            "inner_accepted": int(self.inner_accepted),
            "inner_downgraded": int(self.inner_downgraded),
            "top_level_stripped": int(self.top_level_stripped),
            "fence_unwrapped": bool(self.fence_unwrapped),
            "notes": list(self.notes),
        }


def _strip_outer_fence(text: str) -> Tuple[str, bool]:
    """If the whole answer is wrapped in a single non-mermaid code fence, unwrap it."""
    if not text.strip():
        return text, False
    lines = text.splitlines()
    if len(lines) < 3:
        return text, False
    first = lines[0].strip()
    last = lines[-1].strip()
    m_open = _FENCE_OPEN_RE.match(first)
    if not m_open or last != "```":
        return text, False
    lang = (m_open.group(1) or "").lower()
    if lang == "mermaid":
        return text, False  # valid mermaid block, keep it
    # Strip the wrapping fence (model wrapped the whole markdown by mistake)
    return "\n".join(lines[1:-1]).strip(), True


def _strip_top_title(text: str, *, section_heading: str) -> Tuple[str, int]:
    """Remove an accidental ``# / ##`` echo of the section title at the top."""
    if not text.strip():
        return text, 0
    stripped = 0
    out_lines: List[str] = []
    consumed_top = False
    for i, raw in enumerate(text.splitlines()):
        line = raw.rstrip()
        if not consumed_top:
            # Allow leading blank lines through
            if not line.strip():
                out_lines.append(line)
                continue
            stripped_match = re.match(r"^\s*(#{1,2})\s+(.+?)\s*$", line)
            if stripped_match:
                title = stripped_match.group(2)
                if _norm(title) == _norm(section_heading):
                    stripped += 1
                    consumed_top = True
                    continue
            consumed_top = True
        out_lines.append(line)
    return "\n".join(out_lines).strip(), stripped


def _validate_inner_headings(
    text: str,
    *,
    inner_headings: Sequence[Dict[str, Any]],
) -> Tuple[str, int, int]:
    """Downgrade any ``###`` line whose text does not match a declared inner heading.

    Returns ``(text, accepted_count, downgraded_count)``.
    """
    if "###" not in text:
        return text, 0, 0
    allowed_norm = {
        _norm(str(h.get("text") or ""))
        for h in (inner_headings or [])
        if str(h.get("text") or "").strip()
    }
    accepted = 0
    downgraded = 0

    def _replace(match: "re.Match[str]") -> str:
        nonlocal accepted, downgraded
        title = match.group(1).strip()
        if _norm(title) in allowed_norm and title:
            accepted += 1
            return f"### {title}"
        downgraded += 1
        # Downgrade to bold paragraph so the structure is not invented.
        return f"**{title}**" if title else ""

    new_text = _INNER_HEADING_RE.sub(_replace, text)
    return new_text, accepted, downgraded


def validate_inner_headings(
    *,
    generated_text: str,
    section_heading: str,
    inner_headings: Sequence[Dict[str, Any]],
) -> Tuple[str, DeciderReport]:
    """Post-process one LLM rewrite for a single section."""
    report = DeciderReport()
    text = (generated_text or "").strip()
    if not text:
        report.notes.append("empty_output")
        return text, report

    text, fence_unwrapped = _strip_outer_fence(text)
    if fence_unwrapped:
        report.fence_unwrapped = True
        report.notes.append("outer_code_fence_unwrapped")

    text, top_stripped = _strip_top_title(text, section_heading=section_heading)
    report.top_level_stripped = top_stripped

    # Count emitted ### before validation
    emitted = len(_INNER_HEADING_RE.findall(text))
    report.inner_emitted = emitted

    text, accepted, downgraded = _validate_inner_headings(
        text, inner_headings=inner_headings
    )
    report.inner_accepted = accepted
    report.inner_downgraded = downgraded
    if downgraded:
        report.notes.append(f"downgraded_{downgraded}_undeclared_inner_headings")

    return text.strip(), report
