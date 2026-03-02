from typing import List

from src.structure.raw_span_builder import RawSpan


def build_structural_context(lines: List[str], span: RawSpan) -> str:
    before_start = max(0, span.heading_index - 3)
    before_lines = lines[before_start:span.heading_index]

    after_end = min(len(lines), span.heading_index + 4)  # heading + 3 lines after
    after_lines = lines[span.heading_index + 1 : after_end]

    heading_text = (span.heading_text or "").strip()

    block_parts: List[str] = []
    block_parts.extend(before_lines)

    block_parts.append("<<<CANDIDATE_HEADING_START>>>")
    block_parts.append(f"**{heading_text}**")
    block_parts.append("<<<CANDIDATE_HEADING_END>>>")

    block_parts.extend(after_lines)

    return "\n".join(block_parts)
