"""Re-export DOCX using structured cover + TOC + chapter page breaks."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

os.environ.setdefault("CHAPTER_HIERARCHY_USE_LLM", "0")

from src.modules.export.document_formatter import cover_from_hierarchy_meta
from src.modules.export.docx_notes_exporter import (
    parse_section_bodies_from_markdown,
    rewritten_map_from_section_bodies,
)
from src.modules.export.output_manager import OutputManager
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
from src.modules.storage.knowledge_store import KnowledgeStore


def main() -> int:
    md_path = Path(
        os.environ.get(
            "NOTES_MD",
            str(ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-28_14-30-12.md"),
        )
    )
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46"))
    ultimate_path = log_dir / "15d_ultimate_sections.json"

    if not md_path.exists():
        print(f"[!] Markdown not found: {md_path}")
        return 1
    if not ultimate_path.exists():
        print(f"[!] Missing {ultimate_path}")
        return 1

    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT title FROM books ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    title = row[0] if row else md_path.stem

    print("Rebuilding consolidated 15e (rule-based)...")
    ultimate = json.loads(ultimate_path.read_text(encoding="utf-8"))["items"]
    hierarchy_rows = json.loads((log_dir / "15a_heading_hierarchy.json").read_text(encoding="utf-8")).get("items") or []
    hierarchy = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=0,
    )
    meta = hierarchy.get("meta") or {}
    print(f"  chapters={meta.get('total_chapters')} sections={meta.get('total_sections')}")

    md_text = md_path.read_text(encoding="utf-8")
    section_bodies = parse_section_bodies_from_markdown(md_text)
    rewritten = rewritten_map_from_section_bodies(hierarchy, section_bodies)
    print(f"  mapped sections={len(rewritten)}")

    cover = cover_from_hierarchy_meta(
        title=title,
        hierarchy=hierarchy,
        source_pdf="The Constitution Of India By Jhavala.pdf",
        user_instruction=os.environ.get("REWRITE_USER_INSTRUCTION", "short easy notes, do not add extra details"),
    )

    docx_name = os.environ.get("DOCX_NAME", md_path.stem + "_formatted.docx")
    print(f"  docx = {md_path.parent / docx_name}")

    out = OutputManager(str(md_path.parent)).export_to_word(
        md_text,
        docx_name,
        title,
        cover=cover,
        hierarchy=hierarchy,
        rewritten=rewritten,
    )
    if not out:
        print("[!] DOCX export failed (close the file in Word if open, then retry)")
        return 1
    print(f"[+] Word: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
