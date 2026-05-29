"""Run full pipeline: PDF ingestion + note generation from 15d sections."""
from __future__ import annotations

import os
import re
import sys
import threading
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
    flat_chapter_blocks,
)
from src.modules.generation.rewrite_prompts import (
    default_section_max_tokens,
    is_compact_exam_mode,
    is_exam_oriented_mode,
    rewrite_system_prompt,
)
from src.modules.generation.toc_sections import (
    load_chapter_hierarchy_json,
    load_rewrite_sections,
    load_rewrite_sections_from_15e,
    load_ultimate_sections_json,
)
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.pipeline import run_pipeline
from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider
from src.modules.storage.knowledge_store import KnowledgeStore
from src.modules.generation.rewrite_validation import (
    default_rewritten_map_path,
    save_rewritten_map,
    validate_rewrite_coverage,
    write_validation_report,
)
from src.modules.generation.bundled_rewrite import rewrite_bundles_parallel
from src.modules.generation.missing_section_rewrite import (
    auto_retry_missing_enabled,
    resolve_missing_max_rounds,
    retry_missing_sections,
)
from src.modules.generation.section_bundler import (
    bundle_export_enabled,
    resolve_bundle_size,
    resolve_chapter_page_breaks,
)
from src.modules.generation.parallel_rewrite import (
    resolve_context_overlap_chars,
    resolve_parallel_workers,
    rewrite_sections_parallel,
)


def _provider_label() -> str:
    backend = normalize_chat_provider(config.REWRITE_PROVIDER_ORDER or config.LLM_PROVIDER or "openai")
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
    return ""


def main() -> int:
    pdf_path = os.environ.get(
        "PIPELINE_PDF",
        r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
    )
    if not os.path.exists(pdf_path):
        print(f"[!] PDF not found: {pdf_path}")
        return 1

    user_instruction = _user_instruction()
    if not user_instruction:
        print("[!] Set REWRITE_USER_INSTRUCTION (or REWRITE_ASK) with how you want notes rewritten.")
        print('    Example: REWRITE_USER_INSTRUCTION=short easy notes, no extra details')
        return 1

    max_sections = int(os.environ.get("FULL_REWRITE_MAX_CHUNKS", "0") or "0")
    max_pages = int(os.environ.get("PIPELINE_MAX_PAGES", str(config.PIPELINE_MAX_PAGES or 0)) or "0")
    export_docx = os.environ.get("EXPORT_DOCX", "1").strip().lower() not in {"0", "false", "no", "n"}
    max_source_chars = int(
        os.environ.get(
            "ULTIMATE_MAX_REWRITE_SECTION_CHARS",
            str(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000),
        )
        or "6000"
    )

    print("=" * 60)
    print("FULL PIPELINE")
    print(f"  LLM_PROVIDER = {config.LLM_PROVIDER}")
    print(f"  provider       = {_provider_label()}")
    print(f"  PDF            = {pdf_path}")
    print(f"  user ask       = {user_instruction[:80]}{'...' if len(user_instruction) > 80 else ''}")
    print("  section source = 15f/15e chapter hierarchy (fallback 15d)")
    if max_pages > 0:
        print(f"  max_pages      = {max_pages} (test mode)")
    if max_sections > 0:
        print(f"  max_sections   = {max_sections} (test mode)")
    exam_oriented = is_exam_oriented_mode()
    compact_exam = is_compact_exam_mode()
    parallel_workers = resolve_parallel_workers()
    overlap_chars = resolve_context_overlap_chars()
    print(f"  exam_oriented  = {exam_oriented}")
    print(f"  compact_exam   = {compact_exam}")
    print(f"  parallel       = {parallel_workers} workers, {overlap_chars} char overlap")
    bundle_size = resolve_bundle_size()
    bundle_export = bundle_export_enabled()
    print(f"  bundle_size    = {bundle_size} sections/call, export grouped={bundle_export}")
    print("=" * 60)

    skip_structure = os.environ.get("SKIP_STRUCTURE", "").strip().lower() in {"1", "true", "yes", "y"}
    logger = None
    ultimate_path: Path | None = None
    hierarchy_path: Path | None = None

    if skip_structure:
        print("\n[1/2] Structure pipeline skipped (SKIP_STRUCTURE=1).")
        log_dir = os.environ.get("PIPELINE_LOG_DIR", "").strip()
        if not log_dir:
            print("[!] SKIP_STRUCTURE requires PIPELINE_LOG_DIR=logs/run_...")
            return 1
        ultimate_path = Path(log_dir) / "15d_ultimate_sections.json"
        h15f = Path(log_dir) / "15f_heading_cleanup.json"
        h15e = Path(log_dir) / "15e_chapter_hierarchy.json"
        hierarchy_path = h15f if h15f.exists() else h15e
        if not ultimate_path.exists():
            print(f"[!] Missing {ultimate_path}")
            return 1
    else:
        print("\n[1/2] Structure pipeline (PDF -> headings + 15d/15e/15f)...", flush=True)
        if max_pages > 0:
            os.environ["PIPELINE_MAX_PAGES"] = str(max_pages)
        _result, logger = run_pipeline(pdf_path, enable_logs=True, persist_to_db=True)
        if logger is not None:
            ultimate_path = Path(logger.run_dir) / "15d_ultimate_sections.json"
            h15f = Path(logger.run_dir) / "15f_heading_cleanup.json"
            h15e = Path(logger.run_dir) / "15e_chapter_hierarchy.json"
            hierarchy_path = h15f if h15f.exists() else h15e
            print(f"      logs: {logger.run_dir}", flush=True)

    lines, _, _ = extract_pdf(pdf_path, max_pages=max_pages or None)

    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT book_id, title FROM books ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("[!] No book persisted to DB.")
        return 1
    book_id, title = row[0], row[1]

    sections = load_rewrite_sections(
        store,
        book_id=book_id,
        pdf_path=pdf_path,
        ultimate_sections_path=ultimate_path,
        chapter_hierarchy_path=hierarchy_path if hierarchy_path and hierarchy_path.exists() else None,
        lines=lines,
        prefer_15e=True,
        prefer_15d=True,
    )

    if hierarchy_path and hierarchy_path.exists():
        hmeta = load_chapter_hierarchy_json(hierarchy_path).get("meta") or {}
        stage = "15f" if hierarchy_path.name.startswith("15f") else "15e"
        print(
            f"      {stage} method={hmeta.get('heading_cleanup_method') or hmeta.get('assignment_method')} "
            f"chapters={hmeta.get('total_chapters')} sections={hmeta.get('total_sections')} "
            f"weak_titles={hmeta.get('weak_section_headings_after', '?')}"
        )
    elif ultimate_path and ultimate_path.exists():
        meta = load_ultimate_sections_json(ultimate_path).get("meta") or {}
        print(
            f"      15d profile={meta.get('threshold_profile')} "
            f"sections={meta.get('total_sections')} subs={meta.get('total_subheadings')}"
        )

    print(f"      book_id={book_id}")
    print(f"      rewrite_units={len(sections)}")
    if not sections:
        print("[!] No 15d sections with text found.")
        return 1

    work = sections[:max_sections] if max_sections > 0 else sections
    compact_exam = is_compact_exam_mode()
    bundle_size = resolve_bundle_size()
    bundled = bundle_size > 1
    system = rewrite_system_prompt(exam_oriented=exam_oriented, compact=compact_exam, bundled=bundled)
    rewrite_max_tokens = int(
        os.environ.get(
            "REWRITE_SECTION_MAX_TOKENS",
            str(
                default_section_max_tokens(
                    exam_oriented=exam_oriented,
                    compact=compact_exam,
                    bundle_size=bundle_size if bundled else 1,
                )
            ),
        )
        or str(
            default_section_max_tokens(
                exam_oriented=exam_oriented,
                compact=compact_exam,
                bundle_size=bundle_size if bundled else 1,
            )
        )
    )

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", title).strip("_") or "Generated_Notes"
    md_path = out_dir / f"{safe}_{ts}.md"

    unit_label = f"{len(work)} sections" if not bundled else f"{len(work)} sections in ~{len(work)//bundle_size + 1} bundles"
    print(f"\n[2/2] Generating notes via {_provider_label()} ({unit_label})...")
    print(f"      output: {md_path}", flush=True)

    _tls = threading.local()
    _progress_lock = threading.Lock()
    _first_model: list[str] = []

    def _client() -> LlmChatClient:
        if getattr(_tls, "client", None) is None:
            _tls.client = LlmChatClient.from_config(temperature=0.2)
        return _tls.client

    def _generate(system_prompt: str, user_prompt: str) -> str:
        text = _client().chat(system=system_prompt, user=user_prompt, max_tokens=rewrite_max_tokens) or ""
        if not _first_model:
            with _progress_lock:
                if not _first_model:
                    _first_model.append(_client().last_model_label())
                    print(f"      model={_first_model[0]}", flush=True)
        return text

    def _on_progress(done: int, total: int, heading: str) -> None:
        with _progress_lock:
            print(f"      {done}/{total}: {heading[:72]!r}", flush=True)

    if bundled:
        rewritten = rewrite_bundles_parallel(
            work,
            user_instruction=user_instruction,
            system=system,
            generate=_generate,
            max_source_chars=max_source_chars,
            bundle_size=bundle_size,
            workers=parallel_workers,
            on_progress=_on_progress,
        )
    else:
        rewritten = rewrite_sections_parallel(
            work,
            user_instruction=user_instruction,
            system=system,
            generate=_generate,
            max_tokens=rewrite_max_tokens,
            max_source_chars=max_source_chars,
            workers=parallel_workers,
            overlap_chars=overlap_chars,
            on_progress=_on_progress,
        )

    if not rewritten:
        print("[!] No sections rewritten.")
        return 1

    hierarchy = load_chapter_hierarchy_json(hierarchy_path) if hierarchy_path and hierarchy_path.exists() else None
    if hierarchy and hierarchy.get("chapters"):
        validation = validate_rewrite_coverage(hierarchy, rewritten)
        sidecar = default_rewritten_map_path(md_path)
        save_rewritten_map(
            sidecar,
            rewritten,
            meta={
                "pdf": pdf_path,
                "hierarchy_path": str(hierarchy_path) if hierarchy_path else "",
                "sections_requested": len(work),
                "bundle_size": bundle_size,
                "bundle_export": bundle_export,
            },
        )
        val_path = md_path.with_name(md_path.stem + ".rewrite_validation.json")
        write_validation_report(val_path, validation)
        print("\n      Rewrite validation:")
        for line in validation.summary_lines():
            print(f"        {line}")
        if not validation.ok and auto_retry_missing_enabled():
            rewritten, validation = retry_missing_sections(
                hierarchy=hierarchy,
                rewritten=rewritten,
                sections=work,
                user_instruction=user_instruction,
                generate=_generate,
                exam_oriented=exam_oriented,
                max_source_chars=max_source_chars,
                overlap_chars=overlap_chars,
            )
            save_rewritten_map(
                sidecar,
                rewritten,
                meta={
                    "pdf": pdf_path,
                    "hierarchy_path": str(hierarchy_path) if hierarchy_path else "",
                    "sections_requested": len(work),
                    "auto_retry": True,
                },
            )
            write_validation_report(val_path, validation)
            print("\n      Post-retry validation:")
            for line in validation.summary_lines():
                print(f"        {line}")
        if not validation.ok:
            strict = os.environ.get("REWRITE_REQUIRE_FULL_COVERAGE", "1").strip().lower() not in {
                "0",
                "false",
                "no",
            }
            if strict:
                print("[!] Rewrite validation failed after auto-retry — fix remaining sections manually.")
                return 1
            print("[!] Continuing with partial coverage (REWRITE_REQUIRE_FULL_COVERAGE=0).")

    if hierarchy and hierarchy.get("chapters"):
        chapter_blocks, toc_entries = chapter_blocks_from_hierarchy(
            hierarchy,
            rewritten,
            bundle_size=bundle_size,
            bundle_export=bundle_export,
        )
        cover = cover_from_hierarchy_meta(
            title=title,
            hierarchy=hierarchy,
            source_pdf=Path(pdf_path).name,
            user_instruction=user_instruction,
        )
        response = assemble_notes_document(
            cover=cover,
            toc_entries=toc_entries,
            chapter_blocks=chapter_blocks,
            hierarchy=hierarchy,
            include_toc=True,
        )
    else:
        flat_pairs = [
            (str(sec["heading"]), rewritten.get(str(sec.get("section_id") or i), ""))
            for i, sec in enumerate(work, start=1)
        ]
        chapter_blocks, toc_entries = flat_chapter_blocks(flat_pairs)
        cover = cover_from_hierarchy_meta(
            title=title,
            source_pdf=Path(pdf_path).name,
            user_instruction=user_instruction,
        )
        cover.section_count = len(work)
        response = assemble_notes_document(
            cover=cover,
            toc_entries=toc_entries,
            chapter_blocks=chapter_blocks,
            include_toc=True,
        )

    if not response or len(response) < 40:
        print("[!] Note generation produced no content.")
        return 1

    md_path.write_text(response, encoding="utf-8")
    print(f"\n[+] Done. Markdown: {md_path}")
    print(f"    units={len(work)} chars={len(response)}")

    if export_docx:
        docx_name = f"{safe}_{ts}.docx"
        om = OutputManager(str(out_dir))
        if hierarchy and hierarchy.get("chapters"):
            compact_toc = bundle_export and bundle_size > 1
            chapter_page_breaks = resolve_chapter_page_breaks(
                compact_toc=compact_toc,
                use_bundles=compact_toc,
            )
            docx_path = om.export_to_word(
                response,
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
        else:
            docx_path = om.export_to_word(response, docx_name, title)
        if docx_path:
            print(f"[+] Word: {docx_path}")
        else:
            print("[!] Word export failed (is Pandoc installed? reference.docx present?)")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
