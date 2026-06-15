"""Tests for strict markdown format normalization."""

from __future__ import annotations

from src.modules.generation.markdown_format_normalizer import strict_normalize_markdown
from src.modules.generation.rewrite_prompts import normalize_rewritten_section


def test_splits_runon_bullets():
    raw = (
        "- Section 2 applies Personal Law to Muslims. - It overrides customs. "
        "- It covers ten main topics:"
    )
    out = strict_normalize_markdown(raw)
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(lines) == 3


def test_callout_label_numbered_list(monkeypatch):
    # "Key Points" is a legitimate callout; numbered run-on becomes a bullet list (study mode).
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    raw = (
        "Key Points: 1. Identify the nature and scope of personal laws. "
        "2. Understand traditional systems. 3. View family law as a system."
    )
    out = strict_normalize_markdown(raw)
    assert "**Key Points**" in out
    assert out.count("- ") >= 3


def test_course_outcomes_dropped_as_syllabus():
    # Syllabus-admin labels must be dropped from note bodies (deliberate policy).
    raw = (
        "Course Outcomes: 1. Identify the nature and scope of personal laws. "
        "2. Understand traditional systems."
    )
    out = strict_normalize_markdown(raw)
    assert "Course Outcomes" not in out


def test_expands_inline_numbered_sublist():
    raw = "- It covers ten main topics: 1. Intestate succession. 2. Dissolution of marriage. 3. Maintenance."
    out = strict_normalize_markdown(raw)
    assert "- It covers ten main topics:" in out
    assert "1. Intestate succession." in out
    assert "2. Dissolution of marriage." in out


def test_section_subheading_promoted():
    raw = "Section 1: Short title and extent"
    out = strict_normalize_markdown(raw)
    assert out.startswith("### Section 1:")


def test_normalize_rewritten_section_applies_strict_format(monkeypatch):
    monkeypatch.delenv("REWRITE_USER_INSTRUCTION", raising=False)
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    # Full pipeline splits the run-on numbered list into items and preserves content.
    # (The standalone callout label is intentionally stripped by postprocess.)
    raw = "Key Points: 1. First point about the rule. 2. Second point about the rule."
    out = normalize_rewritten_section(raw)
    assert "First point about the rule" in out
    assert "Second point about the rule" in out
    assert out.count("- ") >= 2


def test_split_inline_bold_subheadings_mid_sentence():
    raw = (
        "Therefore, a Muslim is generally seen as having reached puberty at 15 years. "
        "After this age, individuals can give their own consent for marriage. "
        "**Soundness of Mind** Both parties must be of sound mind at the time of marriage. "
        "A person who is not of sound mind cannot legally consent. "
        "**Muslim Identity** Both parties in a marriage must be Muslims."
    )
    from src.modules.generation.markdown_format_normalizer import strict_normalize_markdown

    out = strict_normalize_markdown(raw, user_instruction="paragraph notes no bullets")
    assert "**Soundness of Mind**" in out
    assert "**Muslim Identity**" in out
    assert ". **Soundness" not in out
    assert out.index("**Soundness of Mind**") < out.index("Both parties must be of sound mind")
    assert out.index("**Muslim Identity**") < out.index("Both parties in a marriage")


def test_strips_also_cover_lines():
    raw = "Some notes here.\n\n**Also cover:** Quran; Sunna; Custom.\n\nMore notes."
    out = strict_normalize_markdown(raw)
    assert "Also cover" not in out
    assert "Some notes here." in out


def test_cleans_bold_label_dash_artifacts(monkeypatch):
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    raw = "**Key Points - -**\n- First point."
    out = strict_normalize_markdown(raw)
    assert "**Key Points**" in out
    assert "- -" not in out.split("**Key Points**")[1][:20]


def test_bulletizes_prose_after_bold_subheading(monkeypatch):
    # Bulletizing applies in study (bullet) mode; default export style is book/paragraph.
    monkeypatch.setenv("NOTES_EXPORT_STYLE", "study")
    raw = (
        "**The Law of Allah**\n"
        "Judicial decision refers to how judges follow earlier cases.\n"
        "Lower courts must follow rules set by higher courts."
    )
    out = strict_normalize_markdown(raw)
    assert "**The Law of Allah**" in out
    assert "- Judicial decision refers" in out
    assert "- Lower courts must follow" in out


def test_attach_continuation_numbered_lists():
    raw = (
        "- Section 2 applies to Muslims:\n"
        "1. Intestate succession.\n"
        "2. Dissolution of marriage.\n"
        "3. Maintenance."
    )
    out = strict_normalize_markdown(raw)
    assert "1. Intestate succession." in out
    assert "2. Dissolution of marriage." in out


def test_unpack_runon_bold_paragraph(monkeypatch):
    monkeypatch.setenv(
        "REWRITE_USER_INSTRUCTION",
        "do not use bullet points only where necessary paragraphs",
    )
    raw = (
        "she remarries. **Maintenance Under The Muslim Women Act, 1986** - **During Iddat:** - "
        "A divorced woman is entitled to fair maintenance during the Iddat period. - **After Iddat:** - "
        "If she remains unmarried she can seek maintenance from relatives."
    )
    from src.modules.generation.markdown_format_normalizer import strict_normalize_markdown

    out = strict_normalize_markdown(
        raw,
        user_instruction="do not use bullet points only where necessary",
    )
    assert "**During Iddat:**" in out
    assert "**After Iddat:**" in out
    assert "A divorced woman is entitled" in out


def test_renumber_ordered_list_blocks_restarts_after_break() -> None:
    from src.modules.generation.markdown_format_normalizer import renumber_ordered_list_blocks

    lines = [
        "1. First point",
        "2. Second point",
        "3. Third point",
        "",
        "6. Should restart",
        "7. As two",
    ]
    out = renumber_ordered_list_blocks(lines)
    assert out[0] == "1. First point"
    assert out[4] == "1. Should restart"
    assert out[5] == "2. As two"


def test_renumber_ordered_list_blocks_restarts_new_topic_numbers() -> None:
    from src.modules.generation.markdown_format_normalizer import renumber_ordered_list_text

    topic_a = "1. Alpha\n2. Beta\n3. Gamma\n4. Delta\n5. Epsilon"
    topic_b = "6. Zeta\n7. Eta"
    out = renumber_ordered_list_text(f"{topic_a}\n\nSome prose.\n\n{topic_b}")
    assert "1. Zeta" in out
    assert "2. Eta" in out
    assert "6. Zeta" not in out
    assert " - **During" not in out
