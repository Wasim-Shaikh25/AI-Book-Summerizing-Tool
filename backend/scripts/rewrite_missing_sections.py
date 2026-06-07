"""Rewrite only missing sections, merge into MD, validate, and export DOCX."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get('PROJECT_ROOT', str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

os.environ.setdefault("CHAPTER_HIERARCHY_USE_LLM", "0")

from src import config
from src.modules.export.document_formatter import cover_from_hierarchy_meta, rebuild_notes_markdown
from src.modules.export.output_manager import OutputManager
from src.modules.generation.missing_section_rewrite import retry_missing_sections
from src.modules.generation.rewrite_prompts import is_exam_oriented_mode
from src.modules.generation.rewrite_validation import (
    default_rewritten_map_path,
    load_rewritten_map,
    missing_sections_from_report,
    save_rewritten_map,
    validate_rewrite_coverage,
    write_validation_report,
)
from src.modules.generation.toc_sections import load_chapter_hierarchy_json, load_rewrite_sections_from_15e
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline.llm_chat_client import LlmChatClient
from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy


def _user_instruction() -> str:
    for key in ("REWRITE_USER_INSTRUCTION", "REWRITE_ASK", "PIPELINE_REWRITE_ASK"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return "short easy notes, do not add extra details"


def _load_hierarchy(log_dir: Path) -> dict:
    path_15f = log_dir / "15f_heading_cleanup.json"
    path_15e = log_dir / "15e_chapter_hierarchy.json"
    if path_15f.exists():
        return load_chapter_hierarchy_json(path_15f)
    if path_15e.exists():
        return load_chapter_hierarchy_json(path_15e)
    ultimate = json.loads((log_dir / "15d_ultimate_sections.json").read_text(encoding="utf-8"))["items"]
    hierarchy_rows = json.loads((log_dir / "15a_heading_hierarchy.json").read_text(encoding="utf-8")).get("items") or []
    return build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=0,
    )


def main() -> int:
    md_path = Path(
        os.environ.get(
            "NOTES_MD",
            str(PROJECT_ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-29_10-49-23.md"),
        )
    )
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-29_10-46-24"))
    pdf_path = os.environ.get(
        "PIPELINE_PDF",
        r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
    )
    docx_name = os.environ.get(
        "DOCX_NAME",
        md_path.stem + "_exam_formatted.docx",
    )

    if not md_path.exists():
        sidecar_probe = default_rewritten_map_path(md_path)
        if not sidecar_probe.exists():
            print(f"[!] Markdown not found: {md_path}")
            return 1
        print(f"  sidecar exists — will create markdown: {md_path.name}")
    if not Path(pdf_path).exists():
        print(f"[!] PDF not found: {pdf_path}")
        return 1

    hierarchy = _load_hierarchy(log_dir)
    meta = hierarchy.get("meta") or {}
    sidecar = default_rewritten_map_path(md_path)

    if sidecar.exists():
        rewritten = load_rewritten_map(sidecar)
        print(f"Loaded sidecar: {sidecar.name} ({len(rewritten)} sections)")
    else:
        from src.modules.export.docx_notes_exporter import resolve_rewritten_map

        md_text = md_path.read_text(encoding="utf-8")
        rewritten = resolve_rewritten_map(hierarchy, md_text=md_text)
        print(f"Built map from markdown ({len(rewritten)} sections)")

    report = validate_rewrite_coverage(hierarchy, rewritten)
    missing = missing_sections_from_report(report)
    print("Initial validation:")
    for line in report.summary_lines():
        print(f"  {line}")

    if not missing:
        print("[+] No missing sections — rebuilding MD and exporting DOCX only.")
    else:
        lines, _, _ = extract_pdf(pdf_path)
        units = load_rewrite_sections_from_15e(hierarchy, lines=lines)
        max_chars = int(
            os.environ.get(
                "ULTIMATE_MAX_REWRITE_SECTION_CHARS",
                str(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000),
            )
            or 6000
        )
        max_tokens = int(os.environ.get("REWRITE_SECTION_MAX_TOKENS", "1200" if is_exam_oriented_mode() else "1800") or "1200")
        client = LlmChatClient.from_config(temperature=0.2)

        def _generate(system: str, user: str) -> str:
            return client.chat(system=system, user=user, max_tokens=max_tokens) or ""

        rewritten, report = retry_missing_sections(
            hierarchy=hierarchy,
            rewritten=rewritten,
            sections=units,
            user_instruction=_user_instruction(),
            generate=_generate,
            max_source_chars=max_chars,
        )
        print("\nPost-rewrite validation:")
        for line in report.summary_lines():
            print(f"  {line}")
        if not report.ok:
            print("[!] Still missing sections after partial rewrite.")
            write_validation_report(md_path.with_name(md_path.stem + ".rewrite_validation.json"), report)
            return 1

    save_rewritten_map(
        sidecar,
        rewritten,
        meta={"updated_by": "rewrite_missing_sections", "md": str(md_path)},
    )
    write_validation_report(md_path.with_name(md_path.stem + ".rewrite_validation.json"), report)

    title = md_path.stem.replace("_2026-", " ").split("_2026")[0]
    if "By_" in md_path.stem:
        title = "The Constitution Of India By Jhavala"

    cover = cover_from_hierarchy_meta(
        title=title,
        hierarchy=hierarchy,
        source_pdf=Path(pdf_path).name,
        user_instruction=_user_instruction(),
    )
    new_md = rebuild_notes_markdown(cover=cover, hierarchy=hierarchy, rewritten=rewritten)

    backup = md_path.with_suffix(".md.bak")
    if md_path.exists() and not backup.exists():
        shutil.copy2(md_path, backup)
        print(f"Backup: {backup.name}")

    md_path.write_text(new_md, encoding="utf-8")
    print(f"[+] Updated markdown: {md_path} ({len(new_md)} chars, {len(rewritten)} sections)")

    out = OutputManager(str(md_path.parent)).export_to_word(
        new_md,
        docx_name,
        title,
        cover=cover,
        hierarchy=hierarchy,
        rewritten=rewritten,
    )
    if not out:
        print("[!] DOCX export failed (close file in Word if open)")
        return 1
    print(f"[+] Word: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
