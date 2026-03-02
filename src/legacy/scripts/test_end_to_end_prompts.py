import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.pdf_reader import PDFReader
from src.core.text_normalizer import PDFTextNormalizer

from src.structure.raw_span_builder import build_raw_spans
from src.structure.span_merger import merge_invalid_spans

from src.core.ai.heading_filter_prompt import build_heading_filter_prompt
from src.core.ai.hierarchy_prompt import build_hierarchy_prompt
from src.core.ai.rewrite_prompt import build_rewrite_prompt

from src.utils.json_utils import safe_json_parse


def main():
    # Load + normalize PDF into a single line stream
    reader = PDFReader(pdf_folder="reference_files")
    pages_data, book_title = reader.read_all_pdfs()

    normalizer = PDFTextNormalizer()
    result = normalizer.normalize(pages_data)

    lines = result["lines"]
    heading_metadata = result.get("heading_metadata", [])
    heading_indices = sorted(int(h["index"]) for h in heading_metadata if "index" in h)

    # Stage A: Raw spans
    raw_spans = build_raw_spans(lines, heading_indices)

    print("Book:", book_title)
    print("Lines:", len(lines))
    print("Heading indices:", len(heading_indices))
    print("Raw spans:", len(raw_spans))
    print("=" * 80)

    # Stage B: Heading filter prompt for first batch (sample)
    batch_spans = raw_spans[:20]
    system_prompt, user_prompt = build_heading_filter_prompt(lines, batch_spans)

    print("HEADING FILTER SYSTEM PROMPT (first 20) [chars]:", len(system_prompt))
    print("HEADING FILTER USER PROMPT JSON (first 20) [chars]:", len(user_prompt))

    print("\n" + "=" * 80)
    print("HEADING FILTER SYSTEM PROMPT (FULL):")
    print("=" * 80)
    print(system_prompt)

    print("\n" + "=" * 80)
    print("HEADING FILTER USER PROMPT JSON (FULL):")
    print("=" * 80)
    print(user_prompt)

    parsed_user = safe_json_parse(user_prompt)
    assert parsed_user is not None, "Heading filter user prompt must be valid JSON"
    assert "headings" in parsed_user and isinstance(parsed_user["headings"], list)
    assert len(parsed_user["headings"]) == len(batch_spans)
    print("Heading filter user JSON OK")
    print("-" * 80)

    # Stop here so we can see CONTEXT BLOCK debug logs without later output truncation.
    return

    # Stage C: Merge invalid spans (simulate a validation map: mark short titles invalid)
    validation_map = {}
    for s in raw_spans:
        title_words = len((s.heading_text or "").split())
        validation_map[s.span_id] = title_words <= 12  # simplistic, just for e2e wiring test

    merged_spans = merge_invalid_spans(raw_spans, validation_map)

    print("Merged spans:", len(merged_spans))
    assert len(merged_spans) <= len(raw_spans)
    print("Span merge OK")
    print("-" * 80)

    # Stage D: Hierarchy prompt (first 40 validated spans)
    hier_system, hier_user = build_hierarchy_prompt(merged_spans[:40])
    print("HIERARCHY SYSTEM PROMPT [chars]:", len(hier_system))
    print("HIERARCHY USER PROMPT JSON [chars]:", len(hier_user))

    parsed_hier_user = safe_json_parse(hier_user)
    assert parsed_hier_user is not None, "Hierarchy user prompt must be valid JSON"
    assert "validated_headings" in parsed_hier_user
    print("Hierarchy user JSON OK")
    print("-" * 80)

    # Stage E: Rewrite prompt (first merged span)
    rw_system, rw_user = build_rewrite_prompt(merged_spans[0], previous_overlap_text="")
    print("REWRITE SYSTEM PROMPT [chars]:", len(rw_system))
    print("REWRITE USER PROMPT [chars]:", len(rw_user))
    assert isinstance(rw_user, str) and len(rw_user) > 0
    print("Rewrite prompt OK")


if __name__ == "__main__":
    main()
