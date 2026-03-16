from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True, slots=True)
class NormalizedLine:
    # Core identity
    line_id: int
    text: str
    page_number: Optional[int]

    # Layout metadata (PyMuPDF-derived)
    y_pos: float
    page_height: float
    font_size: float
    is_bold: bool
    x_center: float
    page_width: float
    vertical_gap_above: float
    is_link: bool

    # Derived signals (per-page)
    centered: bool
    large_font: bool
    large_gap: bool

    # Noise marking (never delete lines)
    is_noise: bool = False
    noise_type: Optional[str] = None


@dataclass(frozen=True, slots=True)
class HeadingCandidate:
    id: str
    text: str
    start_line: int
    end_line: int
    before_context: List[str]
    after_context: List[str]
    full_context_preview: str

    # Gemini call #1
    is_valid: Optional[bool] = None
    valid_reason: Optional[str] = None

    # Gemini call #2
    is_toc: Optional[bool] = None
    toc_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Fragment:
    fragment_id: str
    start_line: int
    end_line: int
    text: str
    assigned_heading_id: Optional[str]


@dataclass(frozen=True, slots=True)
class FinalHeading:
    id: str
    text: str
    level: Optional[int]
    fragment_id: Optional[str]

    # Hierarchy metadata (optional; may be filled by AI or heuristics)
    parent_heading: Optional[str] = None
    reason: Optional[str] = None
    signals_used: Optional[List[str]] = None
    confidence: Optional[float] = None
