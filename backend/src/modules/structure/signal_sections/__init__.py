"""Signal-Sections pipeline (parallel V2).

Mirrors the source PDF's chapter / section / inner-heading structure verbatim
instead of inventing study chapters or renaming PDF headings.

See ``ai-agent-workflow/change-plan-signal-sections-pipeline.md`` for design.

Public modules:
    signal_classifier     - pick high-signal boundary headings
    signal_partitioner    - build sections (boundary -> next boundary)
    pdf_chapter_grouper   - group sections into chapters (PDF markers only)
    pdf_hierarchy_assembler - assemble final hierarchy dict
    signal_logger         - write artifacts to logs/run_signal_<ts>/
"""
