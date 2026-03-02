from typing import Dict, List

from src.structure.raw_span_builder import RawSpan
from src.utils.debug_logger import debug_log


def merge_invalid_spans(raw_spans: List[RawSpan], validation_map: Dict[int, bool]) -> List[RawSpan]:
    if not raw_spans:
        return []

    merged: List[RawSpan] = []
    buffer_content: List[str] = []

    last_valid_span_id = None

    for span in raw_spans:
        is_valid = bool(validation_map.get(span.span_id, False))

        decision = {
            "span_id": span.span_id,
            "heading": (span.heading_text or "").strip(),
            "is_valid": is_valid,
            "merged_into": None,
        }

        if is_valid:
            if buffer_content:
                # buffered invalid content merges into this valid span
                span.content_lines = buffer_content + span.content_lines
                buffer_content = []
            merged.append(span)
            last_valid_span_id = span.span_id
        else:
            # by design, invalid spans will be merged into the next valid span
            # (or into the last valid span if no future valid exists)
            decision["merged_into"] = last_valid_span_id
            buffer_content.extend(span.content_lines)

        debug_log("MERGE DECISION", decision)

    if buffer_content and merged:
        merged[-1].content_lines.extend(buffer_content)

    for i, span in enumerate(merged):
        span.span_id = i

    debug_log(
        "FINAL MERGED SPANS",
        [
            {
                "fragment_id": i + 1,
                "heading_text": (s.heading_text or "").strip(),
                "word_count": sum(len((ln or "").split()) for ln in s.content_lines),
                "content_preview": " ".join(s.content_lines).strip()[:200],
            }
            for i, s in enumerate(merged)
        ],
    )

    return merged
