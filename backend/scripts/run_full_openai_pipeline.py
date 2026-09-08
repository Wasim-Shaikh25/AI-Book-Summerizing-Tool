"""Run full pipeline: PDF ingestion + note generation from 15d sections."""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get('PROJECT_ROOT', str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src import config
from src.modules.export.docx_theme import resolve_docx_theme
from src.modules.export.output_manager import OutputManager
from src.modules.export.document_formatter import (
    assemble_notes_document,
    chapter_blocks_from_hierarchy,
    cover_from_hierarchy_meta,
    flat_chapter_blocks,
    resolve_export_book_title,
)
from src.modules.generation.rewrite_prompts import (
    default_section_max_tokens,
    resolve_rewrite_profile,
    rewrite_system_prompt,
)
from src.modules.interaction.command_parser import IntentResult, effective_user_instruction
from src.modules.interaction.intent_catalog import is_rewrite_task
from src.modules.interaction.intent_router import IntentRouter, use_llm_intent
from src.modules.structure.final_structuring.heading_cleanup import (
    disambiguate_duplicate_section_headings,
)
from src.modules.generation.toc_sections import (
    load_chapter_hierarchy_json,
    load_rewrite_sections,
    load_rewrite_sections_from_15e,
    load_ultimate_sections_json,
)
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.ingestion.profile import _active_profile_name, _apply_overrides, profile_overrides
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
from src.shared.llm_cache import cached_generate


def _provider_label() -> str:
    from src.shared.llm_provider import active_chat_provider, rewrite_provider_order

    backend = rewrite_provider_order()[0] if rewrite_provider_order() else active_chat_provider()
    if backend == "openai":
        return f"openai ({config.OPENAI_MODEL})"
    if backend == "gemini":
        return f"gemini ({config.GEMINI_MODEL})"
    if backend == "openrouter":
        return f"openrouter ({config.OPENROUTER_MODEL})"
    return backend


def _user_instruction() -> str:
    for key in ("REWRITE_USER_INSTRUCTION", "REWRITE_ASK", "PIPELINE_REWRITE_ASK"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return ""


def _pdf_page_count(pdf_path: str) -> int:
    try:
        import fitz

        doc = fitz.open(pdf_path)
        count = int(doc.page_count)
        doc.close()
        return count
    except Exception:
        return 0


def main() -> int:
    pdf_path = os.environ.get(
        "PIPELINE_PDF",
        r"C:\Users\Shaikh Wasim\Downloads\The Constitution Of India By Jhavala.pdf",
    )
    if not os.path.exists(pdf_path):
        print(f"[!] PDF not found: {pdf_path}")
        return 1

    page_count = _pdf_page_count(pdf_path)
    if page_count > 0:
        os.environ["PIPELINE_PAGE_COUNT"] = str(page_count)

    # Apply ingestion profile (fast_local default): skips 15b LLM, 15j, intent LLM, etc.
    _apply_overrides(profile_overrides())
    print(f"  ingestion_profile = {_active_profile_name()}")

    user_instruction = _user_instruction()
    if not user_instruction:
        print("[!] Set REWRITE_USER_INSTRUCTION (or REWRITE_ASK) with how you want notes rewritten.")
        print('    Example: REWRITE_USER_INSTRUCTION=short easy notes, no extra details')
        return 1

    rewrite_intent: IntentResult | None = None
    if use_llm_intent():
        parsed = IntentRouter(use_llm=True).parse_intent(user_instruction)
        if isinstance(parsed, IntentResult):
            rewrite_intent = parsed
            if not is_rewrite_task(parsed.task_type):
                print(f"[!] Instruction classified as {parsed.task_type}, not a full-book rewrite task.")
                if parsed.task_type in {"question_answer", "explain_section"}:
                    print("[!] Use the chat/API Q&A path for questions about the book.")
                elif parsed.task_type == "export":
                    print("[!] Use export from existing notes — this script generates new content.")
                elif parsed.task_type == "clarify":
                    msg = parsed.clarification_message or "Please clarify your request."
                    print(f"[!] {msg}")
                print("[!] Set USE_LLM_INTENT=0 to skip routing and run rewrite anyway.")
                return 1
            print(f"  intent_router  = {parsed.routing_method} task={parsed.task_type} depth={parsed.depth}")
            if parsed.refinement_method:
                print(f"  refiner        = {parsed.refinement_method}")
            if parsed.refined_instruction and parsed.refined_instruction.strip() != user_instruction.strip():
                ri = parsed.refined_instruction
                print(f"  polished ask   = {ri[:80]}{'...' if len(ri) > 80 else ''} (executor uses original)")

    effective_instruction = effective_user_instruction(rewrite_intent, user_instruction)

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
    print(f"  docx_theme     = {resolve_docx_theme()}")
    from src.shared.notes_export_style import resolve_notes_export_style

    print(f"  notes_style    = {resolve_notes_export_style()}")
    if page_count > 0:
        print(f"  pdf_pages      = {page_count}")
    print(f"  user ask       = {user_instruction[:80]}{'...' if len(user_instruction) > 80 else ''}")
    print("  section source = 15f/15e chapter hierarchy (fallback 15d)")
    if max_pages > 0:
        print(f"  max_pages      = {max_pages} (test mode)")
    if max_sections > 0:
        print(f"  max_sections   = {max_sections} (test mode)")
    profile = resolve_rewrite_profile(effective_instruction, intent=rewrite_intent)
    exam_oriented = profile.exam_oriented
    compact_exam = profile.compact
    include_diagrams = profile.include_diagrams
    parallel_workers = resolve_parallel_workers()
    overlap_chars = resolve_context_overlap_chars()
    print(f"  routing        = {rewrite_intent.routing_method if rewrite_intent else 'direct'}")
    if rewrite_intent and rewrite_intent.refinement_method:
        print(f"  refinement     = {rewrite_intent.refinement_method}")
    print(f"  depth          = {profile.depth}")
    print(f"  compact_exam   = {compact_exam}")
    print(f"  diagrams       = {include_diagrams}")
    print(f"  parallel       = {parallel_workers} workers, {overlap_chars} char overlap")
    bundle_size = resolve_bundle_size()
    bundle_export = bundle_export_enabled()
    print(f"  bundle_size    = {bundle_size} sections/call, export grouped={bundle_export}")
    from src.modules.generation.structure_fix_runner import (
        resolve_structure_fix_engine,
        structure_fix_drop_low_grounding,
        structure_fix_enabled,
        structure_fix_merge_duplicates,
    )

    print(
        f"  structure_fix  = {structure_fix_enabled()} "
        f"(engine={resolve_structure_fix_engine()}, "
        f"merge={structure_fix_merge_duplicates()}, "
        f"drop_low_grounding={structure_fix_drop_low_grounding()})"
    )
    print("=" * 60)

    skip_structure = os.environ.get("SKIP_STRUCTURE", "").strip().lower() in {"1", "true", "yes", "y"}
    logger = None
    ultimate_path: Path | None = None
    hierarchy_path: Path | None = None
    pipeline_log_dir: Path | None = None
    pipeline_lines = None

    if skip_structure:
        print("\n[1/4] Structure pipeline skipped (SKIP_STRUCTURE=1).")
        log_dir = os.environ.get("PIPELINE_LOG_DIR", "").strip()
        if not log_dir:
            print("[!] SKIP_STRUCTURE requires PIPELINE_LOG_DIR=logs/run_...")
            return 1
        pipeline_log_dir = Path(log_dir)
        from src.modules.pipeline.stage_registry import (
            STAGE_15D,
            require_artifact,
            resolve_chapter_hierarchy_artifact,
        )

        try:
            ultimate_path = require_artifact(log_dir, STAGE_15D)
        except FileNotFoundError as exc:
            print(f"[!] {exc}")
            return 1
        hierarchy_path = resolve_chapter_hierarchy_artifact(log_dir)
    else:
        print("\n[1/4] Structure pipeline (PDF -> headings + 15d/15g)...", flush=True)
        if max_pages > 0:
            os.environ["PIPELINE_MAX_PAGES"] = str(max_pages)
        _result, logger = run_pipeline(pdf_path, enable_logs=True, persist_to_db=True)
        pipeline_lines = list(_result.lines)
        if logger is not None:
            from src.modules.pipeline.stage_registry import (
                STAGE_15D,
                require_artifact,
                resolve_chapter_hierarchy_artifact,
            )

            pipeline_log_dir = Path(logger.run_dir)
            ultimate_path = require_artifact(logger.run_dir, STAGE_15D)
            hierarchy_path = resolve_chapter_hierarchy_artifact(logger.run_dir)
            print(f"      logs: {logger.run_dir}", flush=True)

    if pipeline_lines is not None:
        lines = pipeline_lines
    else:
        lines, _, _ = extract_pdf(pdf_path, max_pages=max_pages or None)

    pdf_name = Path(pdf_path).name
    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT book_id, title FROM books WHERE source_file_name = ? ORDER BY processed_at DESC LIMIT 1",
        (pdf_name,),
    ).fetchone()
    if not row:
        row = store.get_connection().execute(
            "SELECT book_id, title FROM books ORDER BY processed_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        print("[!] No book persisted to DB.")
        return 1
    book_id, db_title = row[0], row[1]

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

    hierarchy = None
    if hierarchy_path and hierarchy_path.exists():
        hierarchy = load_chapter_hierarchy_json(hierarchy_path)
        disambiguate_duplicate_section_headings(hierarchy.get("chapters") or [])
        hmeta = hierarchy.get("meta") or {}
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

    document_profile = None
    if pipeline_log_dir:
        from src.modules.ingestion.document_profile import load_document_profile

        document_profile = load_document_profile(pipeline_log_dir)
    if document_profile is not None:
        overlap_chars = int(document_profile.rewrite_overlap_chars)
        max_source_chars = int(document_profile.rewrite_max_source_chars)
        print(
            f"      document_profile overlap={overlap_chars} "
            f"max_tokens={document_profile.rewrite_max_tokens} "
            f"strict_headings={document_profile.require_strict_heading_match}",
            flush=True,
        )

    profile = resolve_rewrite_profile(effective_instruction, intent=rewrite_intent)
    compact_exam = profile.compact
    exam_oriented = profile.exam_oriented
    bundle_size = resolve_bundle_size()
    bundled = bundle_size > 1
    system = rewrite_system_prompt(
        bundled=bundled,
        user_instruction=effective_instruction,
        intent=rewrite_intent,
        enforce_single_topic=bool(document_profile and document_profile.enforce_single_topic_prompt),
    )
    rewrite_max_tokens = int(
        os.environ.get(
            "REWRITE_SECTION_MAX_TOKENS",
            str(
                document_profile.rewrite_max_tokens
                if document_profile is not None
                else default_section_max_tokens(
                    bundle_size=bundle_size if bundled else 1,
                    user_instruction=effective_instruction,
                    intent=rewrite_intent,
                )
            ),
        )
        or str(
            document_profile.rewrite_max_tokens
            if document_profile is not None
            else default_section_max_tokens(
                bundle_size=bundle_size if bundled else 1,
                user_instruction=effective_instruction,
                intent=rewrite_intent,
            )
        )
    )

    title = (
        resolve_export_book_title(
            hierarchy=hierarchy,
            pdf_path=pdf_path,
            log_dir=pipeline_log_dir,
        )
        or db_title
        or Path(pdf_path).stem
    )

    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", title).strip("_") or "Generated_Notes"
    md_path = out_dir / f"{safe}_{ts}.md"

    unit_label = f"{len(work)} sections" if not bundled else f"{len(work)} sections in ~{len(work)//bundle_size + 1} bundles"
    print(f"\n[2/4] Generating notes via {_provider_label()} ({unit_label})...")
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

    _generate = cached_generate(_generate, max_tokens=rewrite_max_tokens)

    def _on_progress(done: int, total: int, heading: str) -> None:
        with _progress_lock:
            line = f"      {done}/{total}: {heading[:72]!r}"
            try:
                print(line, flush=True)
            except UnicodeEncodeError:
                print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)

    if bundled:
        rewritten = rewrite_bundles_parallel(
            work,
            user_instruction=effective_instruction,
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
            user_instruction=effective_instruction,
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

    if hierarchy is None and hierarchy_path and hierarchy_path.exists():
        hierarchy = load_chapter_hierarchy_json(hierarchy_path)
        disambiguate_duplicate_section_headings(hierarchy.get("chapters") or [])
    if hierarchy and hierarchy.get("chapters"):
        validation = validate_rewrite_coverage(hierarchy, rewritten)
        sidecar = default_rewritten_map_path(md_path)
        auto_retry_summary: dict = {}
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
            auto_retry_summary["missing_before"] = len(validation.missing_section_ids) + len(
                validation.empty_section_ids
            )
            rewritten, validation = retry_missing_sections(
                hierarchy=hierarchy,
                rewritten=rewritten,
                sections=work,
                user_instruction=effective_instruction,
                generate=_generate,
                exam_oriented=exam_oriented,
                max_source_chars=max_source_chars,
                overlap_chars=overlap_chars,
                intent=rewrite_intent,
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
            auto_retry_summary["missing_after"] = len(validation.missing_section_ids) + len(
                validation.empty_section_ids
            )
            auto_retry_summary["coverage_ratio"] = validation.coverage_ratio
        from src.modules.generation.rewrite_fidelity import get_last_fidelity_stats

        fidelity_summary = get_last_fidelity_stats().to_dict()
        meta = hierarchy.setdefault("meta", {})
        if auto_retry_summary:
            meta["rewrite_auto_retry_summary"] = auto_retry_summary
        meta["rewrite_fidelity_summary"] = fidelity_summary
        if hierarchy_path and hierarchy_path.exists():
            hierarchy_path.write_text(
                json.dumps(hierarchy, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
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
        from src.modules.structure.final_structuring.hierarchy_export import refine_hierarchy_for_export

        hierarchy = refine_hierarchy_for_export(hierarchy)
        title = resolve_export_book_title(
            hierarchy=hierarchy,
            pdf_path=pdf_path,
            log_dir=pipeline_log_dir,
        ) or db_title
        chapter_blocks, toc_entries = chapter_blocks_from_hierarchy(
            hierarchy,
            rewritten,
            bundle_size=bundle_size,
            bundle_export=bundle_export,
        )
        cover = cover_from_hierarchy_meta(
            title=title,
            hierarchy=hierarchy,
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
        title = resolve_export_book_title(
            pdf_path=pdf_path,
            log_dir=pipeline_log_dir,
        ) or db_title
        cover = cover_from_hierarchy_meta(
            title=title,
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

    structure_fix_report_path: Path | None = None
    from src.modules.generation.structure_fix_runner import (
        propagate_titles_to_hierarchy,
        run_structure_fix,
        structure_fix_enabled,
        write_structure_fix_report,
    )

    if structure_fix_enabled():
        print("\n[3/4] Structural cleanup (headings, list numbering)...", flush=True)
        try:
            response, fix_report = run_structure_fix(
                response,
                log_dir=pipeline_log_dir,
            )
            structure_fix_report_path = md_path.with_suffix(".structure_fix.json")
            write_structure_fix_report(fix_report, structure_fix_report_path)
            print(
                f"      engine={fix_report.engine} repaired={fix_report.headings_repaired}/"
                f"{fix_report.headings_noisy} low_grounding_flagged={fix_report.low_grounding_flagged}",
                flush=True,
            )
            if structure_fix_report_path:
                print(f"      report: {structure_fix_report_path}", flush=True)
        except Exception as exc:
            print(f"[!] Structural cleanup failed (continuing with pre-fix markdown): {exc}", flush=True)
    else:
        print("\n[3/4] Structural cleanup skipped (NOTES_STRUCTURE_FIX_ENABLED=0).", flush=True)

    # Sync the final Markdown titles into the hierarchy so the DOCX export and the
    # audit (AC-04 reads the on-disk hierarchy artifact) use the same clean titles
    # the reader sees — otherwise both fall back to raw, noisy hierarchy headings.
    if hierarchy and hierarchy.get("chapters"):
        try:
            synced = propagate_titles_to_hierarchy(
                response,
                hierarchy,
                hierarchy_path=hierarchy_path
                if hierarchy_path and hierarchy_path.exists()
                else None,
            )
            if synced:
                print(f"      synced {synced} titles into hierarchy (DOCX + audit)", flush=True)
        except Exception as exc:
            print(f"[!] Title sync to hierarchy failed (continuing): {exc}", flush=True)

    # Opt-in: body structure audit [3.5/4] — deterministic checks on rewritten section bodies.
    if os.getenv("BODY_STRUCTURE_AUDIT_ENABLED", "0").strip() == "1":
        try:
            from src.modules.generation.body_audit_runner import run_body_audit

            # Build section list from rewritten map for audit
            _audit_sections = [
                {"section_id": sid, "heading": "", "body": body}
                for sid, body in (rewritten.items() if isinstance(rewritten, dict) else {}.items())
            ]
            _source_by_id: dict = {}
            run_body_audit(
                _audit_sections,
                source_by_id=_source_by_id,
                log_dir=pipeline_log_dir,
            )
        except Exception as exc:
            print(f"[!] Body audit failed (continuing): {exc}", flush=True)

    # Opt-in: additionally rebuild hierarchy section order from final Markdown.
    if os.getenv("SYNC_HIERARCHY_FROM_MD", "0").strip() == "1":
        try:
            from src.modules.generation.structure_fix_runner import sync_hierarchy_from_markdown

            synced_artifact = pipeline_log_dir / "s15k_synced_hierarchy.json" if pipeline_log_dir else None
            hierarchy, sync_report = sync_hierarchy_from_markdown(
                md_path if md_path.exists() else Path(response[:0]),
                hierarchy,
                write_path=synced_artifact,
            )
            print(
                f"      sync_from_md patched={sync_report['patched']} skipped={sync_report['skipped']}",
                flush=True,
            )
        except Exception as exc:
            print(f"[!] sync_hierarchy_from_markdown failed (continuing): {exc}", flush=True)

    md_path.write_text(response, encoding="utf-8")
    print(f"\n[+] Markdown: {md_path}")
    print(f"    units={len(work)} chars={len(response)}")

    docx_path = None
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

    from src.modules.quality.service import audit_enabled, run_quality_audit

    if audit_enabled():
        if pipeline_log_dir and pipeline_log_dir.exists():
            print("\n[4/4] Notes quality audit...", flush=True)
            try:
                _, audit_result, audit_paths = run_quality_audit(
                    pdf_path=Path(pdf_path),
                    log_dir=pipeline_log_dir,
                    md_path=md_path,
                    docx_path=Path(docx_path) if docx_path else None,
                    label=safe,
                    out_dir=out_dir,
                )
                print(
                    f"[+] Quality verdict: {audit_result.verdict_scores.get('overall')}",
                    flush=True,
                )
                print(f"[+] Quality report: {audit_paths['txt']}", flush=True)
                if audit_paths["insights"].exists():
                    print(f"[+] Quality insights: {audit_paths['insights']}", flush=True)
            except Exception as exc:
                print(f"[!] Quality audit failed: {exc}", flush=True)
        else:
            print("[!] Quality audit skipped: pipeline log directory unavailable", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
