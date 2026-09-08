"""Re-export notes: saved 15e hierarchy + sidecar -> MD rebuild + structured DOCX."""
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

from src.modules.export.document_formatter import (
    cover_from_hierarchy_meta,
    rebuild_notes_markdown,
    resolve_export_book_title,
)
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
    """Load chapter hierarchy: prefer 15g/15j/15i/15h/15f, else rebuild."""
    from src.modules.pipeline.stage_registry import (
        STAGE_CLEAN_TITLES,
        STAGE_GROUP_CHAPTERS,
        STAGE_PARTITION_SECTIONS,
        STAGE_PARTITION_TREE,
        artifact_path,
        require_artifact,
        resolve_chapter_hierarchy_artifact,
        resolve_existing_artifact,
    )

    path_best = resolve_chapter_hierarchy_artifact(log_dir)
    if path_best is not None:
        print(f"Using saved hierarchy: {path_best.name}")
        return load_chapter_hierarchy_json(path_best)

    path_clean = resolve_existing_artifact(log_dir, STAGE_CLEAN_TITLES)
    path_group = resolve_existing_artifact(log_dir, STAGE_GROUP_CHAPTERS)
    rebuild = os.environ.get("REBUILD_15E", "0").strip().lower() in {"1", "true", "yes", "y"}
    rerun_clean = os.environ.get("RUN_15F", "0").strip().lower() in {"1", "true", "yes", "y"}

    if path_clean is not None and not rerun_clean and not rebuild:
        print(f"Using saved clean_titles: {path_clean.name}")
        return load_chapter_hierarchy_json(path_clean)

    if not rebuild and path_group is not None:
        print("Using group_chapters + running clean_titles heading cleanup...")
        raw = load_chapter_hierarchy_json(path_group)
        from src.modules.structure.dropped_heading_registry import load_dropped_registry_from_log_dir
        from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy

        ultimate_sections: list = []
        path_sections = resolve_existing_artifact(log_dir, STAGE_PARTITION_SECTIONS)
        if path_sections is not None:
            ultimate_sections = json.loads(path_sections.read_text(encoding="utf-8")).get("items", {}).get("sections") or []
        registry = load_dropped_registry_from_log_dir(log_dir)

        cleaned = clean_heading_hierarchy(
            raw,
            ultimate_sections=ultimate_sections,
            dropped_registry=registry,
        )
        meta = cleaned.get("meta") or {}
        print(
            f"  clean_titles method={meta.get('heading_cleanup_method')} "
            f"weak_after={meta.get('weak_section_headings_after')} "
            f"dup_chapters={meta.get('duplicate_chapter_names_after')}"
        )
        if os.environ.get("SAVE_15F", "1").strip().lower() not in {"0", "false", "no"}:
            payload = {"run_id": log_dir.name.replace("run_", ""), "stage": STAGE_CLEAN_TITLES, "items": cleaned}
            out_clean = artifact_path(log_dir, STAGE_CLEAN_TITLES, for_write=True)
            out_clean.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  saved {out_clean.name}")
        return cleaned

    if resolve_existing_artifact(log_dir, STAGE_PARTITION_SECTIONS) is None:
        raise FileNotFoundError(f"Missing partition_sections and no saved group_chapters in {log_dir}")

    os.environ.setdefault("CHAPTER_HIERARCHY_USE_LLM", "0")
    from src.modules.structure.final_structuring.chapter_hierarchy_builder import build_chapter_hierarchy
    from src.modules.structure.final_structuring.heading_cleanup import clean_heading_hierarchy

    print("Rebuilding group_chapters (REBUILD_15E=1)...")
    ultimate = json.loads(require_artifact(log_dir, STAGE_PARTITION_SECTIONS).read_text(encoding="utf-8"))["items"]
    hierarchy_rows = json.loads(require_artifact(log_dir, STAGE_PARTITION_TREE).read_text(encoding="utf-8")).get("items") or []
    raw = build_chapter_hierarchy(
        ultimate_sections=ultimate,
        hierarchy=hierarchy_rows,
        max_sections=0,
    )
    from src.modules.structure.dropped_heading_registry import load_dropped_registry_from_log_dir

    return clean_heading_hierarchy(
        raw,
        ultimate_sections=ultimate.get("sections") or [],
        dropped_registry=load_dropped_registry_from_log_dir(log_dir),
    )


def main() -> int:
    md_path = Path(
        os.environ.get(
            "NOTES_MD",
            str(PROJECT_ROOT / "output" / "The_Constitution_Of_India_By_Jhavala_2026-05-28_14-30-12.md"),
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

    # Opt-in: rebuild hierarchy headings and section order from the final Markdown.
    # Safe default is 0 — existing re-export behaviour is byte-for-byte unchanged.
    if os.getenv("SYNC_HIERARCHY_FROM_MD", "0").strip() == "1":
        from src.modules.generation.structure_fix_runner import sync_hierarchy_from_markdown

        md_candidates = sorted(log_dir.glob("*.md"))
        if not md_candidates and md_path.exists():
            md_candidates = [md_path]
        if md_candidates:
            synced_artifact = log_dir / "s15k_synced_hierarchy.json"
            hierarchy, sync_report = sync_hierarchy_from_markdown(
                md_candidates[0], hierarchy, write_path=synced_artifact
            )
            print(
                f"  [sync] Hierarchy rebuilt from Markdown: "
                f"{sync_report['patched']} patched, "
                f"{sync_report['skipped']} skipped"
            )
            for w in sync_report.get("warnings", []):
                print(f"  [sync] WARNING: {w}")

    from src.modules.ingestion.layout_enrichment import load_layout_lines_from_log_dir
    from src.modules.structure.final_structuring.chapter_placement import (
        refresh_chapter_placement_if_module_gap,
    )
    from src.modules.structure.final_structuring.hierarchy_export import refine_hierarchy_for_export

    layout_lines = load_layout_lines_from_log_dir(log_dir)
    before_ch = len(hierarchy.get("chapters") or [])
    hierarchy = refresh_chapter_placement_if_module_gap(hierarchy, layout_lines)
    after_ch = len(hierarchy.get("chapters") or [])
    if after_ch != before_ch:
        print(f"  15h refresh: chapters {before_ch} -> {after_ch}")
        hierarchy = refine_hierarchy_for_export(hierarchy)

    meta = hierarchy.get("meta") or {}
    print(f"  chapters={meta.get('total_chapters')} sections={meta.get('total_sections')}")

    sidecar = default_rewritten_map_path(md_path)
    sidecar_meta: dict = {}
    if not sidecar.exists():
        if not md_path.exists():
            print(f"[!] No sidecar and no markdown: {md_path}")
            return 1
        print(f"  no sidecar — mapping from markdown")
        md_text = md_path.read_text(encoding="utf-8")
        rewritten = resolve_rewritten_map(hierarchy, md_text=md_text)
    else:
        print(f"  sidecar={sidecar.name}")
        raw_sidecar = json.loads(sidecar.read_text(encoding="utf-8"))
        sidecar_meta = raw_sidecar.get("meta") or {}
        rewritten = raw_sidecar.get("sections") or load_rewritten_map(sidecar)

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

    title = resolve_export_book_title(
        hierarchy=hierarchy,
        md_path=md_path,
        sidecar_meta=sidecar_meta,
        pdf_path=os.environ.get("PIPELINE_PDF") or pdf_name,
        log_dir=log_dir,
    )
    print(f"  title={title}")

    cover = cover_from_hierarchy_meta(
        title=title,
        hierarchy=hierarchy,
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
