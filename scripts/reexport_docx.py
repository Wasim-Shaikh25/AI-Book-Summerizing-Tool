"""Re-export notes: saved 15e hierarchy + sidecar -> MD rebuild + structured DOCX."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.modules.export.document_formatter import cover_from_hierarchy_meta, rebuild_notes_markdown
from src.modules.export.docx_notes_exporter import resolve_rewritten_map
from src.modules.export.output_manager import OutputManager
from src.modules.generation.missing_section_rewrite import auto_retry_missing_enabled, retry_missing_sections
from src.modules.generation.section_bundler import (
    bundle_export_enabled,
    resolve_bundle_size,
    resolve_chapter_page_breaks,
)
from src.modules.generation.rewrite_validation import (
    default_rewritten_map_path,
    load_rewritten_map,
    save_rewritten_map,
    validate_rewrite_coverage,
    write_validation_report,
)
from src.modules.generation.toc_sections import load_chapter_hierarchy_json, load_rewrite_sections_from_15e
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline.llm_chat_client import LlmChatClient
from src.modules.storage.knowledge_store import KnowledgeStore


def _load_hierarchy(log_dir: Path) -> dict:
    """Load chapter hierarchy: prefer 15f, else run 15f on saved 15e, else rebuild 15e."""
    path_15f = log_dir / "15f_heading_cleanup.json"
    path_15e = log_dir / "15e_chapter_hierarchy.json"
    rebuild = os.environ.get("REBUILD_15E", "0").strip().lower() in {"1", "true", "yes", "y"}
    rerun_15f = os.environ.get("RUN_15F", "0").strip().lower() in {"1", "true", "yes", "y"}

    if path_15f.exists() and not rerun_15f and not rebuild:
        print(f"Using saved 15f: {path_15f.name}")
        return load_chapter_hierarchy_json(path_15f)

    if not rebuild and path_15e.exists():
        print(f"Using 15e + running stage 15f heading cleanup...")
        raw = load_chapter_hierarchy_json(path_15e)
        from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy

        cleaned = clean_heading_hierarchy(raw)
        meta = cleaned.get("meta") or {}
        print(
            f"  15f method={meta.get('heading_cleanup_method')} "
            f"weak_after={meta.get('weak_section_headings_after')} "
            f"dup_chapters={meta.get('duplicate_chapter_names_after')}"
        )
        if os.environ.get("SAVE_15F", "1").strip().lower() not in {"0", "false", "no"}:
            payload = {"run_id": log_dir.name.replace("run_", ""), "stage": "15f_heading_cleanup", "items": cleaned}
            path_15f.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  saved {path_15f.name}")
        return cleaned

    if not (log_dir / "15d_ultimate_sections.json").exists():
        raise FileNotFoundError(f"Missing 15d and no saved 15e in {log_dir}")

    os.environ.setdefault("CHAPTER_HIERARCHY_USE_LLM", "0")
    from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
    from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy

    print("Rebuilding 15e (REBUILD_15E=1)...")
    ultimate = json.loads((log_dir / "15d_ultimate_sections.json").read_text(encoding="utf-8"))["items"]
    hierarchy_rows = json.loads((log_dir / "15a_heading_hierarchy.json").read_text(encoding="utf-8")).get("items") or []
    raw = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=0,
    )
    return clean_heading_hierarchy(raw)


def main() -> int:
    md_path = Path(
        os.environ.get(
            "NOTES_MD",
            str(ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-28_14-30-12.md"),
        )
    )
    log_dir = Path(os.environ.get("PIPELINE_LOG_DIR", "logs/run_2026-05-28_13-36-46"))
    pdf_name = os.environ.get("SOURCE_PDF_NAME", "The Constitution Of India By Jhavala.pdf")

    if not log_dir.exists():
        print(f"[!] Log dir not found: {log_dir}")
        return 1

    try:
        hierarchy = _load_hierarchy(log_dir)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1

    meta = hierarchy.get("meta") or {}
    print(f"  chapters={meta.get('total_chapters')} sections={meta.get('total_sections')}")

    sidecar = default_rewritten_map_path(md_path)
    if not sidecar.exists():
        if not md_path.exists():
            print(f"[!] No sidecar and no markdown: {md_path}")
            return 1
        print(f"  no sidecar — mapping from markdown")
        md_text = md_path.read_text(encoding="utf-8")
        rewritten = resolve_rewritten_map(hierarchy, md_text=md_text)
    else:
        print(f"  sidecar={sidecar.name}")
        rewritten = load_rewritten_map(sidecar)

    print(f"  mapped sections={len(rewritten)}/{meta.get('total_sections', '?')}")

    validation = validate_rewrite_coverage(hierarchy, rewritten)
    val_path = md_path.with_name(md_path.stem + ".reexport_validation.json")
    write_validation_report(val_path, validation)
    print("  Validation:")
    for line in validation.summary_lines():
        print(f"    {line}")

    if not validation.ok and auto_retry_missing_enabled():
        pdf_path = os.environ.get(
            "PIPELINE_PDF",
            r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
        )
        if Path(pdf_path).exists():
            lines, _, _ = extract_pdf(pdf_path)
            units = load_rewrite_sections_from_15e(hierarchy, lines=lines)
            max_tokens = int(os.environ.get("REWRITE_SECTION_MAX_TOKENS", "1200") or "1200")
            client = LlmChatClient.from_config(temperature=0.2)

            def _generate(system: str, user: str) -> str:
                return client.chat(system=system, user=user, max_tokens=max_tokens) or ""

            rewritten, validation = retry_missing_sections(
                hierarchy=hierarchy,
                rewritten=rewritten,
                sections=units,
                user_instruction=os.environ.get("REWRITE_USER_INSTRUCTION", "short easy notes, do not add extra details"),
                generate=_generate,
            )
            save_rewritten_map(sidecar, rewritten, meta={"reexport_auto_retry": True})
            write_validation_report(val_path, validation)
            print("  Post-retry validation:")
            for line in validation.summary_lines():
                print(f"    {line}")

    strict = os.environ.get("REWRITE_REQUIRE_FULL_COVERAGE", "1").strip().lower() not in {"0", "false", "no"}
    if not validation.ok and strict:
        print("[!] Export blocked — missing sections remain after auto-retry.")
        return 1

    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT title FROM books ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    title = row[0] if row else md_path.stem

    cover = cover_from_hierarchy_meta(
        title=title,
        hierarchy=hierarchy,
        source_pdf=pdf_name,
        user_instruction=os.environ.get("REWRITE_USER_INSTRUCTION", "short easy notes, do not add extra details"),
    )

    bundle_size = resolve_bundle_size()
    bundle_export = bundle_export_enabled()
    compact_toc = bundle_export and bundle_size > 1
    chapter_page_breaks = resolve_chapter_page_breaks(
        compact_toc=compact_toc,
        use_bundles=compact_toc,
    )

    new_md = rebuild_notes_markdown(
        cover=cover,
        hierarchy=hierarchy,
        rewritten=rewritten,
        bundle_size=bundle_size,
        bundle_export=bundle_export,
        chapter_page_breaks=chapter_page_breaks,
    )
    if md_path.exists():
        backup = md_path.with_suffix(".md.bak")
        if not backup.exists() or os.environ.get("OVERWRITE_BACKUP", "0") == "1":
            shutil.copy2(md_path, backup)
            print(f"  backup={backup.name}")
    md_path.write_text(new_md, encoding="utf-8")
    print(f"[+] Rebuilt markdown: {md_path} ({len(new_md)} chars)")

    save_rewritten_map(sidecar, rewritten, meta={"reexport": str(md_path), "hierarchy": str(log_dir)})

    docx_name = os.environ.get("DOCX_NAME", md_path.stem + "_formatted.docx")
    print(f"  docx = {md_path.parent / docx_name}")
    print(
        f"  bundle_size={bundle_size} bundle_export={bundle_export} "
        f"compact_toc={compact_toc} chapter_page_breaks={chapter_page_breaks}"
    )

    out = OutputManager(str(md_path.parent)).export_to_word(
        new_md,
        docx_name,
        title,
        cover=cover,
        hierarchy=hierarchy,
        rewritten=rewritten,
        bundle_size=bundle_size,
        bundle_export=bundle_export,
        compact_toc=compact_toc,
        chapter_page_breaks=chapter_page_breaks,
    )
    if not out:
        print("[!] DOCX export failed (close the file in Word if open, then retry)")
        return 1
    print(f"[+] Word: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
