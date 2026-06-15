"""Unit tests for post-rewrite structural cleanup of notes Markdown."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.modules.generation.notes_structure_fix import (  # noqa: E402
    fix_notes_markdown,
    parse_notes_md,
    render_notes_md,
)
from src.modules.quality.heuristics import classify_heading  # noqa: E402


NOISY_TITLE = "Punishment for Rape — Provisions for Rape Punishment — Candidate, electoral right defined."

SAMPLE_MD = """\
<div style="text-align: center;">

# Sample Book

### Textbook Notes

</div>

# Table of Contents

## 1. Criminal Offences
- {noisy}
- Theft Provisions

```{{=openxml}}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Criminal Offences

## {noisy} <!-- sid:S1 -->

**Rape Punishment Provisions** describe the penalties for the offence of rape and related conduct under the new code.

## Theft Provisions <!-- sid:S2 -->

Theft is punishable with imprisonment. The penalty for stealing property can extend to three years or a fine or both.
""".format(noisy=NOISY_TITLE)


def test_parse_and_render_roundtrip_preserves_body() -> None:
    doc = parse_notes_md(SAMPLE_MD)
    assert len(doc.chapters) == 1
    chapter = doc.chapters[0]
    assert chapter.title == "Criminal Offences"
    assert [s.sid for s in chapter.sections] == ["S1", "S2"]

    rendered = render_notes_md(doc)
    assert "**Rape Punishment Provisions** describe the penalties" in rendered
    assert "<!-- sid:S1 -->" in rendered
    assert "<!-- sid:S2 -->" in rendered


def test_offline_heading_repair_fixes_noisy_title() -> None:
    new_md, report = fix_notes_markdown(SAMPLE_MD, engine="minilm", chat=None)
    assert report.headings_noisy >= 1
    assert report.headings_repaired >= 1

    doc = parse_notes_md(new_md)
    s1 = doc.chapters[0].sections[0]
    assert s1.sid == "S1"
    # The prose fragment heading must be replaced by a clean topic title.
    assert s1.title != NOISY_TITLE
    assert classify_heading(s1.title) == "looks_ok"
    # A clean heading is left untouched.
    assert doc.chapters[0].sections[1].title == "Theft Provisions"


def test_llm_heading_repair_uses_batched_titles() -> None:
    def fake_chat(system: str, user: str, max_tokens: int):
        return '{"S1": "Definitions And Interpretation"}'

    new_md, report = fix_notes_markdown(SAMPLE_MD, engine="hybrid", chat=fake_chat)
    doc = parse_notes_md(new_md)
    s1 = doc.chapters[0].sections[0]
    assert s1.title == "Definitions And Interpretation"
    assert any(c.kind == "heading" and "llm" in c.detail for c in report.changes)


def test_toc_is_regenerated_from_repaired_headings() -> None:
    def fake_chat(system: str, user: str, max_tokens: int):
        return '{"S1": "Definitions And Interpretation"}'

    new_md, _ = fix_notes_markdown(SAMPLE_MD, engine="hybrid", chat=fake_chat)
    toc_block = new_md.split("# Table of Contents", 1)[1].split("```{=openxml}", 1)[0]
    assert "- Definitions And Interpretation" in toc_block
    assert "electoral right defined" not in toc_block


def test_noisy_chapter_title_is_repaired() -> None:
    noisy_chapter_md = """\
# Table of Contents

## 1. {noisy}
- Bribery Offences
- Election Offences

```{{=openxml}}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# {noisy}

## Bribery Offences <!-- sid:S1 -->

Bribery involves offering money to a public servant to influence official duty.

## Election Offences <!-- sid:S2 -->

Election offences include undue influence and personation at elections.
""".format(noisy=NOISY_TITLE)

    def fake_chat(system: str, user: str, max_tokens: int):
        return '{"C0": "Bribery And Election Offences"}'

    new_md, report = fix_notes_markdown(noisy_chapter_md, engine="hybrid", chat=fake_chat)
    doc = parse_notes_md(new_md)
    assert doc.chapters[0].title == "Bribery And Election Offences"
    assert any(c.kind == "heading" and "chapter" in c.detail for c in report.changes)


def test_low_grounding_sections_are_flagged_and_dropped() -> None:
    index_source = "\n".join(
        ["169. Candidate, electoral right defined.", "170. Bribery.", "171. Undue influence.", "172. Personation."]
    )
    source_by_id = {"S1": index_source, "S2": "Theft is dishonestly taking property with full prose content here." * 4}

    _, report_flag = fix_notes_markdown(SAMPLE_MD, engine="minilm", chat=None, source_by_id=source_by_id)
    assert report_flag.low_grounding_flagged == 1
    assert report_flag.low_grounding_dropped == 0

    new_md, report_drop = fix_notes_markdown(
        SAMPLE_MD, engine="minilm", chat=None, source_by_id=source_by_id, drop_low_grounding=True
    )
    assert report_drop.low_grounding_dropped == 1
    assert "<!-- sid:S1 -->" not in new_md
    assert "<!-- sid:S2 -->" in new_md


def test_duplicate_sections_flagged_and_optionally_merged() -> None:
    dup_md = """\
# Table of Contents

## 1. Offences
- Bribery Offence
- Bribery Offence Repeated

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Offences

## Bribery Offence <!-- sid:S1 -->

Bribery involves offering money to a public servant to influence official duty unlawfully.

## Bribery Offence Repeated <!-- sid:S2 -->

Bribery involves offering money to a public servant to influence official duty unlawfully.
"""
    _, flagged = fix_notes_markdown(dup_md, engine="minilm", chat=None)
    assert flagged.duplicate_pairs >= 1
    assert flagged.duplicates_merged == 0

    merged_md, merged = fix_notes_markdown(dup_md, engine="minilm", chat=None, merge_duplicates_apply=True)
    assert merged.duplicates_merged >= 1
    assert "<!-- sid:S2 -->" not in merged_md


def test_low_grounding_skipped_without_source() -> None:
    _, report = fix_notes_markdown(SAMPLE_MD, engine="minilm", chat=None)
    assert report.low_grounding_flagged == 0
    assert any("skipped" in n.lower() for n in report.notes)
