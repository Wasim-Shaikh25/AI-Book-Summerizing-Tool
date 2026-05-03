from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedLine:
    line_id: int
    text: str
    page_number: Optional[int] = None
    y_pos: float = 0.0
    font_size: float = 10.0
    page_height: Optional[float] = None
    page_width: Optional[float] = None
    x0: float = 0.0
    x1: float = 0.0
    y0: float = 0.0
    y1: float = 0.0
    x_center: float = 0.0
    is_bold: bool = False
    is_mix_bold: bool = False
    is_italic: bool = False
    is_upper: bool = False
    is_centered: bool = False
    centered: bool = False
    is_link: bool = False
    large_font: bool = False
    large_gap: bool = False
    is_noise: bool = False
    noise_type: str = ""
    before_context: str = ""
    after_context: str = ""
    word_count: int = 0
    indent_level: int = 0
    vertical_gap_above: float = 0.0
    vertical_gap_below: float = 0.0
    source: str = ""  # "": normal text  |  "table": inside table cell  |  "image_ocr": from OCR


@dataclass
class HeadingCandidate:
    id: str
    text: str
    start_line: int
    end_line: int
    full_context_preview: str = ""
    before_context: str = ""
    after_context: str = ""
    is_valid: bool = True
    valid_reason: str = ""
    is_toc: bool = False
    toc_reason: str = ""
    confidence: float = 0.0
    line_id: Optional[int] = None
    source_line_id: Optional[int] = None
    selected: Optional[bool] = None


@dataclass
class Fragment:
    id: str = ""
    start_line: int = 0
    end_line: int = 0
    fragment_id: str = ""
    assigned_heading_id: str = ""
    heading_ids: List[str] = field(default_factory=list)
    page_number: Optional[int] = None
    text: str = ""

    def __post_init__(self) -> None:
        if not self.id and self.fragment_id:
            self.id = self.fragment_id
        elif not self.fragment_id and self.id:
            self.fragment_id = self.id


@dataclass
class FinalHeading:
    id: str
    text: str
    line_id: int = 0
    fragment_id: Optional[str] = None
    parent_heading: Optional[str] = None
    signals_used: Optional[List[str]] = None
    confidence: Optional[float] = None
    level: int = 1
    page_number: Optional[int] = None
    is_toc: bool = False
    in_toc_section: bool = False
    reason: Optional[str] = None
    hierarchy_model: Optional[str] = None
    hierarchy_latency_ms: Optional[float] = None

    def __post_init__(self) -> None:
        if self.line_id is None:
            self.line_id = 0
        if self.signals_used is None:
            self.signals_used = []


@dataclass
class PipelineResult:
    final_headings: List[FinalHeading] = field(default_factory=list)
    fragments: List[Fragment] = field(default_factory=list)
    heading_to_fragment_id: Dict[str, str] = field(default_factory=dict)


@dataclass
class HeadingGateTraceRecord:
    line_id: Optional[int] = None
    id: Optional[int] = None
    text: str = ""
    page_number: Optional[int] = None
    decision: str = ""
    reason: str = ""
    signals: List[str] = field(default_factory=list)
    stage: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "line_id": self.line_id,
            "id": self.id,
            "text": self.text,
            "page_number": self.page_number,
            "decision": self.decision,
            "reason": self.reason,
            "signals": list(self.signals),
            "stage": self.stage,
        }
        return payload
