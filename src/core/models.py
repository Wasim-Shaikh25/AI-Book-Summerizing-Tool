from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True, slots=True)
class NormalizedLine:
    id: int
    text: str
    page_number: Optional[int]


@dataclass(frozen=True, slots=True)
class HeadingCandidate:
    id: str
    text: str
    start_line: int
    end_line: int
    before_context: List[str]
    after_context: List[str]
    full_context_preview: str
    is_valid: Optional[bool] = None


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
