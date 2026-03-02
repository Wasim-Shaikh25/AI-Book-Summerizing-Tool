from dataclasses import dataclass
from typing import List

from src.utils.debug_logger import debug_log


@dataclass
class RawSpan:
    span_id: int
    heading_index: int
    start_index: int
    end_index: int
    heading_text: str
    content_lines: List[str]


def build_raw_spans(lines: List[str], heading_indices: List[int]) -> List[RawSpan]:
    if not heading_indices:
        return []

    spans: List[RawSpan] = []

    for i, idx in enumerate(heading_indices):
        next_idx = heading_indices[i + 1] if i + 1 < len(heading_indices) else len(lines)

        heading_text = lines[idx]
        content_lines = lines[idx + 1 : next_idx]

        spans.append(
            RawSpan(
                span_id=i,
                heading_index=idx,
                start_index=idx,
                end_index=next_idx - 1,
                heading_text=heading_text,
                content_lines=content_lines,
            )
        )

    debug_log(
        "RAW SPANS",
        [
            {
                "span_id": s.span_id,
                "heading_text": (s.heading_text or "").strip(),
                "word_count": sum(len((ln or "").split()) for ln in s.content_lines),
                "content_preview": " ".join(s.content_lines).strip()[:150],
            }
            for s in spans
        ],
    )

    return spans
