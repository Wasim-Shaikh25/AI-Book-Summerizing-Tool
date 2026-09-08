import json
from pathlib import Path

def summarize(log: str) -> None:
    p = Path(log)
    ult = json.loads((p / "s15d_ultimate_sections.json").read_text(encoding="utf-8"))["items"]
    meta = ult.get("meta") or {}
    h = json.loads((p / "s15f_heading_cleanup.json").read_text(encoding="utf-8"))["items"]
    secs = sum(len(c.get("sections") or []) for c in h.get("chapters") or [])
    subs = sum(
        len(s.get("subheadings") or [])
        for c in h.get("chapters") or []
        for s in c.get("sections") or []
    )
    print("===", p.name, "===")
    for k in (
        "page_count",
        "section_budget",
        "sections_before_compress",
        "sections_compressed_merges",
        "total_sections",
        "kept_heading_count",
        "total_subheadings",
    ):
        print(f"  {k}: {meta.get(k)}")
    print(f"  15f sections: {secs}, subheadings in tree: {subs}")
    print(f"  15f restored: {(h.get('meta') or {}).get('heading_cleanup_restored_from_ultimate')}")
    bad_phrases = ("It will be seen", "He must have resided", "The scheme of distribution")
    for ch in h.get("chapters") or []:
        for sec in ch.get("sections") or []:
            title = str(sec.get("heading") or "")
            if any(b in title for b in bad_phrases):
                print(f"  BAD PHRASE: {sec.get('section_id')}: {title[:90]}")


if __name__ == "__main__":
    for log in [
        "../logs/run_2026-06-07_15-30-21",
        "../logs/run_2026-06-07_17-00-37",
    ]:
        summarize(log)
