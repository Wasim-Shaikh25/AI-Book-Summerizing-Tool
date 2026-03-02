import re
from typing import List, Dict, Any


class HeadingSpanBuilder:
    """
    Converts heading candidates into structural spans.

    Each heading gets:
        - start_index
        - end_index
        - span_word_count
        - span_line_count
        - span_non_empty_count

    Then evaluates structural strength.
    """

    def build_spans(
        self,
        lines: List[str],
        heading_metadata: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        if not heading_metadata:
            return []

        # Sort by index to ensure proper order
        heading_metadata = sorted(heading_metadata, key=lambda x: x["index"])

        spans = []

        for i, heading in enumerate(heading_metadata):
            start_idx = heading["index"]

            # Determine end index
            if i + 1 < len(heading_metadata):
                next_idx = heading_metadata[i + 1]["index"]
                end_idx = next_idx - 1
            else:
                end_idx = len(lines) - 1

            span_lines = lines[start_idx + 1 : end_idx + 1]

            span_word_count = sum(len(re.findall(r"\w+", ln)) for ln in span_lines)

            span_line_count = len(span_lines)

            span_non_empty = sum(1 for ln in span_lines if ln.strip())

            spans.append(
                {
                    "title": heading["line"],
                    "start_index": start_idx,
                    "end_index": end_idx,
                    "span_word_count": span_word_count,
                    "span_line_count": span_line_count,
                    "span_non_empty_count": span_non_empty,
                    "heading_score": heading.get("heading_score", 0.0),
                }
            )

        return spans

    def filter_structural_headings(
        self, spans: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Keep only structurally strong headings.

        Rules:
        - Must have meaningful content after it
        - OR must be structured numeric heading (1.1, 2.3 etc.)
        """

        filtered = []

        for span in spans:
            title = span["title"].strip()

            is_structured_numeric = bool(re.match(r"^\d+(\.\d+)+", title))

            is_roman = bool(re.match(r"^[IVXLCDM]+[.)\s-]", title, re.IGNORECASE))

            # Structural numeric headings are privileged
            if is_structured_numeric or is_roman:
                filtered.append(span)
                continue

            # Non-numeric headings must have real content
            if span["span_word_count"] >= 40 and span["span_non_empty_count"] >= 3:
                filtered.append(span)

        return filtered
