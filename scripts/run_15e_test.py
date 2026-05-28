"""Run stage 15e chapter hierarchy on existing 15d logs + optional limited rewrite."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src import config
from src.modules.export.output_manager import OutputManager
from src.modules.export.document_formatter import (
    assemble_notes_document,
    chapter_blocks_from_hierarchy,
    cover_from_hierarchy_meta,
)
from src.modules.generation.rewrite_prompts import build_section_user_prompt, rewrite_system_prompt
from src.modules.generation.toc_sections import (
    load_rewrite_sections_from_15e,
    load_ultimate_sections_json,
)
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
from src.modules.storage.knowledge_store import KnowledgeStore


def _provider_label() -> str:
    backend = normalize_chat_provider(config.CHAPTER_HIERARCHY_LLM or config.LLM_PROVIDER or "openai")
    if backend == "openai":
        return f"openai ({config.OPENAI_MODEL})"
    if backend == "gemini":
        return f"gemini ({config.GEMINI_MODEL})"
    return backend


def _user_instruction() -> str:
    for key in ("REWRITE_USER_INSTRUCTION", "REWRITE_ASK", "PIPELINE_REWRITE_ASK"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return "short easy notes, do not add extra details"


def main() -> int:
    log_dir = os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46").strip()
    pdf_path = os.environ.get(
        "PIPELINE_PDF",
        r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
    )
    max_sections = int(os.environ.get("CHAPTER_HIERARCHY_MAX_SECTIONS", "12") or "12")
    max_rewrite = int(os.environ.get("FULL_REWRITE_MAX_CHUNKS", "5") or "5")
    run_rewrite = os.environ.get("RUN_REWRITE", "1").strip().lower() not in {"0", "false", "no", "n"}

    log_path = Path(log_dir)
    ultimate_path = log_path / "15d_ultimate_sections.json"
    hierarchy_path = log_path / "15e_chapter_hierarchy.json"

    if not ultimate_path.exists():
        print(f"[!] Missing {ultimate_path}")
        return 1
    if not os.path.exists(pdf_path):
        print(f"[!] PDF not found: {pdf_path}")
        return 1

    print("=" * 60)
    print("STAGE 15e — CHAPTER HIERARCHY TEST")
    print(f"  log_dir        = {log_path}")
    print(f"  15e provider   = {_provider_label()}")
    print(f"  max_sections   = {max_sections}")
    print(f"  max_rewrite    = {max_rewrite}")
    print("=" * 60)

    ultimate = load_ultimate_sections_json(ultimate_path)
    hierarchy_rows = json.loads((log_path / "15a_heading_hierarchy.json").read_text(encoding="utf-8")).get("items") or []

    print(f"\n[1/3] Building 15e from {ultimate_path.name} ({len(ultimate.get('sections') or [])} sections)...")
    chapter_hierarchy = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=max_sections,
    )

    meta = chapter_hierarchy.get("meta") or {}
    print(
        f"      method={meta.get('assignment_method')} "
        f"chapters={meta.get('total_chapters')} "
        f"sections={meta.get('processed_section_count')} "
        f"topics={meta.get('total_topics')}"
    )
    for ch in chapter_hierarchy.get("chapters") or []:
        sec_ids = [s.get("section_id") for s in ch.get("sections") or []]
        print(f"      {ch.get('chapter_id')}: {str(ch.get('heading') or '')[:60]} -> {sec_ids}")

    envelope = {
        "run_id": log_path.name.replace("run_", ""),
        "stage": "15e_chapter_hierarchy",
        "pdf_file": Path(pdf_path).name,
        "timestamp": datetime.utcnow().isoformat(),
        "total_items": len(chapter_hierarchy.get("chapters") or []),
        "items": chapter_hierarchy,
    }
    hierarchy_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[+] Wrote {hierarchy_path}")

    if not run_rewrite:
        return 0

    user_instruction = _user_instruction()
    max_pages = int(os.environ.get("PIPELINE_MAX_PAGES", "0") or "0")
    lines, _, _ = extract_pdf(pdf_path, max_pages=max_pages or None)

    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT book_id, title FROM books ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("[!] No book in DB.")
        return 1
    book_id, title = row[0], row[1]

    sections = load_rewrite_sections_from_15e(chapter_hierarchy, lines=lines)
    work = sections[:max_rewrite] if max_rewrite > 0 else sections
    print(f"\n[2/3] Rewrite test ({len(work)} sections) via {normalize_chat_provider(config.LLM_PROVIDER)}...")
    print(f"      ask: {user_instruction[:80]}")

    client = LlmChatClient.from_config(temperature=0.2)
    system = rewrite_system_prompt()

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", title).strip("_") or "Generated_Notes"
    md_path = out_dir / f"{safe}_15e_test_{ts}.md"

    rewritten: dict[str, str] = {}

    for idx, sec in enumerate(work, start=1):
        heading = sec["heading"]
        print(f"      {idx}/{len(work)}: {heading[:72]!r}", flush=True)
        user_prompt = build_section_user_prompt(
            user_instruction=user_instruction,
            heading=heading,
            source_text=str(sec["text"])[:6000],
        )
        text = client.chat(system=system, user=user_prompt, max_tokens=1200)
        rewritten[str(sec.get("section_id"))] = (text or "").strip()

    print(f"\n[3/3] Writing hierarchical markdown -> {md_path}")
    chapter_blocks, toc_entries = chapter_blocks_from_hierarchy(chapter_hierarchy, rewritten)
    cover = cover_from_hierarchy_meta(
        title=title,
        hierarchy=chapter_hierarchy,
        source_pdf=Path(pdf_path).name,
        user_instruction=user_instruction,
    )
    response = assemble_notes_document(
        cover=cover,
        toc_entries=toc_entries,
        chapter_blocks=chapter_blocks,
        include_toc=True,
    )
    md_path.write_text(response, encoding="utf-8")
    print(f"[+] Done. Markdown: {md_path}")
    print(f"    chapters={len(toc_entries)} rewrite_sections={len(work)} chars={len(response)}")

    if os.environ.get("EXPORT_DOCX", "0").strip().lower() in {"1", "true", "yes", "y"}:
        docx_path = OutputManager(str(out_dir)).export_to_word(
            response, f"{safe}_15e_test_{ts}.docx", title
        )
        if docx_path:
            print(f"[+] Word: {docx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
