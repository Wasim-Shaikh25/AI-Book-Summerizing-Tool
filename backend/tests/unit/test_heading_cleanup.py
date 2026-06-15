"""Unit tests for stage 15f heading cleanup rules."""
from __future__ import annotations

from src.modules.generation.rewrite_validation import is_weak_section_heading
from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry, is_sentence_like_title
from src.modules.structure.final_structuring.heading_cleanup import (
    _collapse_generic_disambiguation,
    _rule_clean_heading,
    clean_heading_hierarchy,
    disambiguate_duplicate_section_headings,
    merge_duplicate_named_chapters,
)


def test_rule_clean_art_only() -> None:
    out = _rule_clean_heading("(Art. 21)")
    assert out == "Article 21"
    assert not is_weak_section_heading(out)


def test_rule_strip_number_prefix() -> None:
    out = _rule_clean_heading("1. Equality before the law (Art. 14)")
    assert out == "Equality before the law (Art. 14)"
    assert not is_weak_section_heading(out)


def test_rule_clean_roman_fragment_uses_subheading_not_preview() -> None:
    preview = "He must have resided in India for not less than five years immediately preceding the date."
    out = _rule_clean_heading(
        "(ii)",
        preview=preview,
        subheadings=[{"heading": "Citizenship by descent (Art. 5)"}],
    )
    assert out == "Citizenship by descent (Art. 5)"
    assert not is_sentence_like_title(out)


def test_rule_clean_year_art_uses_subheading_not_preview() -> None:
    preview = "It will be seen that items (a), (b) and (c) above refer to different modes of acquisition."
    out = _rule_clean_heading(
        "1950. (Art. 5)",
        preview=preview,
        subheadings=[{"heading": "Modes of acquiring citizenship"}],
    )
    assert out == "Modes of acquiring citizenship"
    assert not is_sentence_like_title(out)


def test_dropped_prose_cannot_return_as_title() -> None:
    registry = DroppedHeadingRegistry()
    registry.register(text="He must have resided in India for not less than five years")
    hierarchy = {
        "meta": {},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Citizenship",
                "sections": [
                    {
                        "section_id": "S11",
                        "heading": "He must have resided in India for not less than five years",
                        "fragment": {
                            "preview": "He must have resided in India for not less than five years immediately preceding the date."
                        },
                        "subheadings": [{"heading": "Residence requirement (Art. 5)"}],
                    }
                ],
            }
        ],
    }
    ultimate = [{"section_id": "S11", "heading": "(ii)"}]
    cleaned = clean_heading_hierarchy(
        hierarchy,
        ultimate_sections=ultimate,
        dropped_registry=registry,
        use_llm=False,
    )
    title = cleaned["chapters"][0]["sections"][0]["heading"]
    assert title == "Residence requirement (Art. 5)"
    assert not is_sentence_like_title(title)


def test_rules_only_backend_skips_cloud_llm() -> None:
    hierarchy = {
        "meta": {},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "Fundamental Rights",
                "sections": [
                    {
                        "section_id": "S1",
                        "heading": "(Art. 21)",
                        "fragment": {"preview": "Right to life and personal liberty"},
                        "subheadings": [],
                    }
                ],
            }
        ],
    }
    cleaned = clean_heading_hierarchy(hierarchy, use_llm=False)
    assert cleaned["meta"]["heading_cleanup_backend"] in {"rules_only", "minilm", "openai", "openrouter", ""}


def test_rule_dedupe_chapters() -> None:
    hierarchy = {
        "meta": {},
        "chapters": [
            {
                "chapter_id": "C1",
                "heading": "The Union Executive",
                "page_start": 72,
                "sections": [{"section_id": "S1", "heading": "President", "fragment": {"preview": "President"}}],
            },
            {
                "chapter_id": "C2",
                "heading": "The Union Executive",
                "page_start": 86,
                "sections": [{"section_id": "S2", "heading": "Prime Minister", "fragment": {"preview": "PM"}}],
            },
        ],
    }
    cleaned = clean_heading_hierarchy(hierarchy, use_llm=False)
    names = [c["heading"] for c in cleaned["chapters"]]
    assert names[0] != names[1]
    assert "72" in names[0] or "86" in names[1]


def test_disambiguate_duplicate_generic_headings() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Federal Scheme",
            "sections": [
                {
                    "section_id": "S1",
                    "heading": "Brief historical background",
                    "page_number": 165,
                    "fragment": {"preview": "The Government of India Act 1935 introduced provincial autonomy."},
                }
            ],
        },
        {
            "chapter_id": "C2",
            "heading": "Constitutional History",
            "sections": [
                {
                    "section_id": "S2",
                    "heading": "Brief historical background",
                    "page_number": 172,
                    "fragment": {"preview": "Main Provisions of the 1947 Act transferred power to India."},
                }
            ],
        },
        {
            "chapter_id": "C3",
            "heading": "Landmark Cases",
            "sections": [
                {
                    "section_id": "S3",
                    "heading": "[Art. 143]",
                    "page_number": 220,
                    "fragment": {"preview": "Case No. 37 IN RE. AYODHYA REFERENCE under Article 143."},
                },
                {
                    "section_id": "S4",
                    "heading": "[Art. 143]",
                    "page_number": 225,
                    "fragment": {"preview": "Advisory opinion sought on Kerala Educational Bill reference."},
                },
            ],
        },
    ]
    changed = disambiguate_duplicate_section_headings(chapters)
    assert changed >= 4
    titles = [s["heading"] for ch in chapters for s in ch["sections"]]
    assert len(set(titles)) == len(titles)
    assert "Constitutional History" in titles[1] or "172" in titles[1]
    assert "AYODHYA" in titles[2].upper() or "Case" in titles[2]
    assert "172" in titles[1] or "Constitutional History" in titles[1]


def test_numbered_subclause_not_merged_with_parent_section() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Fundamental Rights",
            "sections": [
                {
                    "section_id": "S15",
                    "heading": "III. Protection In Respect Of Conviction For Offences (Art. 20)",
                    "page_number": 38,
                    "fragment": {"preview": ""},
                    "subheadings": [],
                },
                {
                    "section_id": "S16",
                    "heading": "(3) Protection against self-incrimination [Art. 20(3)]",
                    "page_number": 39,
                    "fragment": {"preview": "Art. 20(3) provides that no person accused"},
                    "subheadings": [
                        {"heading": "III. Protection In Respect Of Conviction For Offences (Art. 20)"},
                    ],
                },
            ],
        }
    ]
    changed = disambiguate_duplicate_section_headings(chapters)
    s16 = chapters[0]["sections"][1]["heading"]
    assert " — " not in s16
    assert s16 == "(3) Protection against self-incrimination [Art. 20(3)]"
    assert changed >= 0


def test_sanitize_strips_truncated_merge_suffix() -> None:
    from src.modules.structure.final_structuring.heading_cleanup import sanitize_merged_section_titles

    chapters = [
        {
            "chapter_id": "C1",
            "heading": "FR",
            "sections": [
                {
                    "section_id": "S15",
                    "heading": "III. Protection In Respect Of Conviction For Offences (Art. 20)",
                    "page_number": 38,
                },
                {
                    "section_id": "S16",
                    "heading": "(3) Protection against self-incrimination [Art. 20(3)] — III. Protection In Respect Of Conviction Fo",
                    "page_number": 39,
                },
            ],
        }
    ]
    n = sanitize_merged_section_titles(chapters)
    assert n == 1
    assert chapters[0]["sections"][1]["heading"] == "(3) Protection against self-incrimination [Art. 20(3)]"


def test_merge_duplicate_named_chapters() -> None:
    chapters = [
        {
            "chapter_id": "C3",
            "heading": "Offences Relating to Property",
            "page_start": 207,
            "sections": [{"section_id": "S1", "heading": "A", "page_number": 207}],
        },
        {
            "chapter_id": "C4",
            "heading": "Offences Relating to Property",
            "page_start": 227,
            "sections": [{"section_id": "S2", "heading": "B", "page_number": 227}],
        },
    ]
    merged, count = merge_duplicate_named_chapters(chapters)
    assert count == 1
    assert len(merged) == 1
    assert len(merged[0]["sections"]) == 2


def test_collapse_generic_disambiguation_uses_suffix() -> None:
    out = _collapse_generic_disambiguation(
        "Illustrations - OF RECEIVING STOLEN PROPERTY",
        preview="",
    )
    assert out == "OF RECEIVING STOLEN PROPERTY"


def test_illustration_plural_counts_as_duplicate() -> None:
    chapters = [
        {
            "chapter_id": "C1",
            "heading": "Topics",
            "sections": [
                {
                    "section_id": "S1",
                    "heading": "Illustration",
                    "page_number": 10,
                    "fragment": {"preview": "A deceives B by pretending to be a public servant."},
                },
                {
                    "section_id": "S2",
                    "heading": "Illustrations",
                    "page_number": 20,
                    "fragment": {"preview": "A cheats by personation under Section 416."},
                },
            ],
        }
    ]
    changed = disambiguate_duplicate_section_headings(chapters)
    titles = [s["heading"] for s in chapters[0]["sections"]]
    assert changed >= 1
    assert titles[0] != titles[1]
