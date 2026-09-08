"""Audit pipeline section topics against PDF source text."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import fitz

from src.modules.generation.rewrite_validation import is_weak_section_heading, normalize_heading
from src.modules.structure.dropped_heading_registry import is_sentence_like_title

LOG_DIR = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else PROJECT_ROOT / "logs" / "run_2026-06-07_15-30-21"
)
PDF_PATH = Path(
    sys.argv[2]
    if len(sys.argv) > 2
    else BACKEND_ROOT / "src/modules/debug/pdf_files/The Constitution Of India By Jhavala.pdf"
)


def _load_json(name: str) -> dict | list | None:
    path = LOG_DIR / name
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items") if isinstance(data, dict) and "items" in data else data


def _section_rows(hierarchy: dict) -> list[dict]:
    rows: list[dict] = []
    for ch in hierarchy.get("chapters") or []:
        for sec in ch.get("sections") or []:
            rows.append(
                {
                    "chapter": ch.get("heading"),
                    "section_id": sec.get("section_id"),
                    "heading": str(sec.get("heading") or "").strip(),
                    "page": sec.get("page_number"),
                    "sub_count": len(sec.get("subheadings") or []),
                }
            )
    return rows


def classify(title: str) -> str:
    if not title:
        return "empty"
    if is_sentence_like_title(title):
        return "prose_not_topic"
    if is_weak_section_heading(title):
        return "weak_fragment"
    if re.search(r"\bA\.?\s*I\.?\s*R\.?", title, re.I) and ")" in title:
        return "case_line"
    if re.search(r"^\d{4}\s+NOC", title, re.I):
        return "case_line"
    if re.search(r"\(p\.\s*\d+\)\s*$", title):
        return "disambiguation_noise"
    if title.endswith("?") and len(title.split()) > 6:
        return "question_prose"
    if len(title) > 95:
        return "too_long"
    return "looks_ok"


def pdf_match(title: str, page_hint: int | None, page_text: list[str]) -> tuple[str, int | None]:
    t = title.strip()
    if not t:
        return "empty", None
    pages: list[int] = []
    if isinstance(page_hint, int):
        for pg in range(max(1, page_hint - 1), min(len(page_text), page_hint + 2) + 1):
            if t.lower() in page_text[pg - 1].lower():
                pages.append(pg)
    if not pages:
        for pg, text in enumerate(page_text, start=1):
            if t.lower() in text.lower():
                pages.append(pg)
    if not pages:
        return "not_in_pdf", None
    if classify(t) in {"prose_not_topic", "question_prose", "too_long"}:
        return "in_pdf_as_body", pages[0]
    return "in_pdf", pages[0]


def main() -> int:
    hierarchy = _load_json("s15g_title_validation.json") or _load_json("s15f_heading_cleanup.json") or _load_json("s15e_chapter_hierarchy.json")
    ultimate = _load_json("s15d_ultimate_sections.json")
    if not hierarchy or not isinstance(hierarchy, dict):
        print("No hierarchy found")
        return 1

    doc = fitz.open(PDF_PATH)
    page_text = [doc.load_page(i).get_text("text") for i in range(doc.page_count)]
    rows = _section_rows(hierarchy)
    ult_map = {
        str(s.get("section_id")): str(s.get("heading") or "")
        for s in (ultimate or {}).get("sections") or []
    }

    classes = Counter(classify(r["heading"]) for r in rows)
    ok = classes["looks_ok"]
    bad = len(rows) - ok

    print("=== SECTION TOPIC AUDIT ===")
    print(f"Log: {LOG_DIR.name}")
    print(f"PDF pages: {doc.page_count} | Pipeline sections: {len(rows)}")
    print(f"Quality: {dict(classes)}")
    print(f"looks_ok: {ok} ({ok / len(rows) * 100:.0f}%)")
    print(f"problematic: {bad} ({bad / len(rows) * 100:.0f}%)")

    print("\nPDF text presence by class:")
    for label in sorted(classes):
        subset = [r for r in rows if classify(r["heading"]) == label]
        hits = sum(1 for r in subset if pdf_match(r["heading"], r["page"], page_text)[0].startswith("in_pdf"))
        print(f"  {label}: n={len(subset)} found_in_pdf={hits}")

    print("\n=== BAD TOPICS (prose / questions promoted to section titles) ===")
    for r in rows:
        if classify(r["heading"]) not in {"prose_not_topic", "question_prose", "too_long"}:
            continue
        st, pg = pdf_match(r["heading"], r["page"], page_text)
        orig = ult_map.get(str(r["section_id"]), "")
        print(
            f"  {r['section_id']} p.{r['page']} | orig={orig[:45]!r} | "
            f"topic={r['heading'][:70]!r} | {st} p.{pg}"
        )

    print("\n=== CASE-LINE FRAGMENTS AS TOPICS (partial citations) ===")
    count = 0
    for r in rows:
        if classify(r["heading"]) != "case_line":
            continue
        count += 1
        if count <= 15:
            st, pg = pdf_match(r["heading"], r["page"], page_text)
            print(f"  {r['section_id']} p.{r['page']} | {r['heading'][:85]} | {st} p.{pg}")
    print(f"  ... total case_line topics: {count}")

    print("\n=== GOOD TOPICS (sample, verified in PDF) ===")
    shown = 0
    for r in rows:
        if classify(r["heading"]) != "looks_ok":
            continue
        st, pg = pdf_match(r["heading"], r["page"], page_text)
        if st != "in_pdf":
            continue
        print(f"  {r['section_id']} p.{r['page']} | {r['heading'][:85]}")
        shown += 1
        if shown >= 20:
            break

    print("\n=== 15f RENAMES THAT CREATED BAD TOPICS ===")
    renamed_bad = 0
    for r in rows:
        sid = str(r["section_id"])
        orig = ult_map.get(sid, "")
        if normalize_heading(orig) == normalize_heading(r["heading"]):
            continue
        if classify(r["heading"]) == "looks_ok":
            continue
        renamed_bad += 1
        if renamed_bad <= 15:
            print(f"  {sid}: {orig[:55]!r} -> {r['heading'][:70]!r}")
    print(f"total bad renames from 15f: {renamed_bad}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
