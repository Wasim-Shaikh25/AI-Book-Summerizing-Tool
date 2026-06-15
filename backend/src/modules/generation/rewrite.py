from __future__ import annotations



import logging

import re

import threading

from datetime import datetime

from pathlib import Path

from typing import Any, Dict, List, Optional, Sequence



from src import config

from src.modules.export.output_manager import OutputManager

from src.modules.export.document_formatter import (
    assemble_notes_document,
    chapter_blocks_from_hierarchy,
    cover_from_hierarchy_meta,
    flat_chapter_blocks,
)

from src.modules.generation.model_router import RewriteModelRouter

from src.modules.generation.parallel_rewrite import (
    resolve_context_overlap_chars,
    resolve_parallel_workers,
    rewrite_sections_parallel,
)
from src.modules.generation.rewrite_prompts import (
    resolve_rewrite_profile,
    rewrite_system_prompt,
)
from src.modules.interaction.command_parser import IntentResult
from src.modules.structure.final_structuring.chapter_placement import enforce_chapter_structure

from src.modules.generation.toc_sections import load_chapter_hierarchy_json, load_rewrite_sections

from src.modules.storage.knowledge_store import KnowledgeStore

from src.shared.models import NormalizedLine



logger = logging.getLogger(__name__)





class RewriteEngine:

    """Generate rewritten notes from persisted 15d sections or TOC fragments."""



    def __init__(

        self,

        store: KnowledgeStore,

        *,

        book_id: str,

        book_title: str,

        output_folder: Optional[str] = None,

    ) -> None:

        self.store = store

        self.book_id = book_id

        self.book_title = book_title or "Generated Notes"

        self.router = RewriteModelRouter()

        self.output = OutputManager(output_folder or config.OUTPUT_FOLDER)
        self._last_auto_retry_summary: Dict[str, Any] = {}
        self._last_fidelity_summary: Dict[str, Any] = {}



    def rewrite_sections(

        self,

        sections: List[Dict[str, Any]],

        *,

        user_instruction: str,

        max_sections: int = 0,

        max_tokens: int = 1800,

        max_source_chars: Optional[int] = None,

        chapter_hierarchy: Optional[Dict[str, Any]] = None,

        source_pdf: str = "",

        intent: Optional[IntentResult] = None,

        document_profile: Optional[Any] = None,

    ) -> str:

        work = sections[:max_sections] if max_sections > 0 else sections

        if document_profile is not None:
            cap = max_source_chars or int(document_profile.rewrite_max_source_chars)
            if max_tokens == 1800:
                max_tokens = int(document_profile.rewrite_max_tokens)
            overlap = int(document_profile.rewrite_overlap_chars)
        else:
            cap = max_source_chars or int(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000)
            overlap = resolve_context_overlap_chars()

        profile = resolve_rewrite_profile(user_instruction, intent=intent)
        if max_tokens == 1800 and document_profile is None:
            max_tokens = profile.max_tokens
        system = rewrite_system_prompt(
            user_instruction=user_instruction,
            intent=intent,
            enforce_single_topic=document_profile.enforce_single_topic_prompt if document_profile else False,
        )
        workers = resolve_parallel_workers()

        _tls = threading.local()

        def _router() -> RewriteModelRouter:
            if getattr(_tls, "router", None) is None:
                _tls.router = RewriteModelRouter()
            return _tls.router

        def _generate(system_prompt: str, user_prompt: str) -> str:
            out = _router().generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
            return out.get("text") or ""

        from src.shared.llm_cache import cached_generate

        _generate = cached_generate(_generate, max_tokens=max_tokens)

        rewritten = rewrite_sections_parallel(
            work,
            user_instruction=user_instruction,
            system=system,
            generate=_generate,
            max_tokens=max_tokens,
            max_source_chars=cap,
            workers=workers,
            overlap_chars=overlap,
            on_progress=lambda done, total, heading: logger.info(
                "Rewrite %s/%s: %s", done, total, heading[:60]
            ),
        )

        if chapter_hierarchy and chapter_hierarchy.get("chapters"):
            from src.modules.generation.missing_section_rewrite import (
                auto_retry_missing_enabled,
                resolve_auto_retry_max_passes,
                resolve_auto_retry_min_coverage,
                retry_missing_sections,
            )
            from src.modules.generation.rewrite_validation import validate_rewrite_coverage

            auto_retry_summary: Dict[str, Any] = {}
            if auto_retry_missing_enabled():
                min_coverage = resolve_auto_retry_min_coverage()
                report = validate_rewrite_coverage(chapter_hierarchy, rewritten)
                auto_retry_summary["missing_before"] = len(report.missing_section_ids) + len(
                    report.empty_section_ids
                )
                if report.coverage_ratio < min_coverage:
                    rewritten, report = retry_missing_sections(
                        hierarchy=chapter_hierarchy,
                        rewritten=rewritten,
                        sections=work,
                        user_instruction=user_instruction,
                        generate=_generate,
                        max_source_chars=cap,
                        overlap_chars=0,
                        max_rounds=resolve_auto_retry_max_passes(),
                        intent=intent,
                    )
                    logger.info(
                        "Auto-retry coverage: %s (%s/%s sections)",
                        f"{report.coverage_ratio:.0%}",
                        report.rewritten_count,
                        report.total_sections,
                    )
                auto_retry_summary["missing_after"] = len(report.missing_section_ids) + len(
                    report.empty_section_ids
                )
                auto_retry_summary["coverage_ratio"] = report.coverage_ratio
            self._last_auto_retry_summary = auto_retry_summary

            from src.modules.generation.rewrite_fidelity import get_last_fidelity_stats

            self._last_fidelity_summary = get_last_fidelity_stats().to_dict()

            chapter_blocks, toc_entries = chapter_blocks_from_hierarchy(chapter_hierarchy, rewritten)

            cover = cover_from_hierarchy_meta(

                title=self.book_title,

                hierarchy=chapter_hierarchy,

                source_pdf=source_pdf,

                user_instruction=user_instruction,

            )

            return assemble_notes_document(

                cover=cover,

                toc_entries=toc_entries,

                chapter_blocks=chapter_blocks,

                include_toc=True,

            )

        flat_pairs = [(str(sec["heading"]), rewritten.get(str(sec.get("section_id") or i), "")) for i, sec in enumerate(work, start=1)]

        chapter_blocks, toc_entries = flat_chapter_blocks(flat_pairs)

        cover = cover_from_hierarchy_meta(

            title=self.book_title,

            source_pdf=source_pdf,

            user_instruction=user_instruction,

        )

        cover.section_count = len(work)

        return assemble_notes_document(

            cover=cover,

            toc_entries=toc_entries,

            chapter_blocks=chapter_blocks,

            include_toc=True,

        )



    def run(

        self,

        *,

        user_instruction: str,

        export_to_word: bool = False,

        max_sections: int = 0,

        pdf_path: Optional[str] = None,

        ultimate_sections_path: Optional[str | Path] = None,

        chapter_hierarchy_path: Optional[str | Path] = None,

        lines: Optional[Sequence[NormalizedLine]] = None,

        intent: Optional[IntentResult] = None,

        document_profile: Optional[Any] = None,

        pipeline_log_dir: Optional[str | Path] = None,

    ) -> Dict[str, Any]:

        sections = load_rewrite_sections(

            self.store,

            book_id=self.book_id,

            pdf_path=pdf_path,

            ultimate_sections_path=ultimate_sections_path,

            chapter_hierarchy_path=chapter_hierarchy_path,

            lines=lines,

            prefer_15e=True,

            prefer_15d=True,

        )

        if not sections:

            return {"error": "No sections with text found (15e/15d or TOC)."}

        chapter_hierarchy = None

        if chapter_hierarchy_path and Path(chapter_hierarchy_path).exists():

            chapter_hierarchy = load_chapter_hierarchy_json(chapter_hierarchy_path)
            enforce_chapter_structure(chapter_hierarchy)

        if document_profile is None and pipeline_log_dir:
            from src.modules.ingestion.document_profile import load_document_profile

            document_profile = load_document_profile(pipeline_log_dir)



        cap = max_sections or int(config.FULL_REWRITE_MAX_CHUNKS or 0)

        markdown = self.rewrite_sections(

            sections,

            user_instruction=user_instruction,

            max_sections=cap,

            chapter_hierarchy=chapter_hierarchy,

            source_pdf=Path(pdf_path).name if pdf_path else "",

            intent=intent,

            document_profile=document_profile,

        )

        if not markdown or markdown.count("\n") < 2:

            return {"error": "Note generation produced no content (check LLM_PROVIDER / API keys)."}



        result: Dict[str, Any] = {

            "markdown": markdown,

            "section_count": len(sections[:cap] if cap > 0 else sections),

            "auto_retry_summary": getattr(self, "_last_auto_retry_summary", {}),

            "fidelity_summary": getattr(self, "_last_fidelity_summary", {}),

        }

        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", self.book_title).strip("_") or "Generated_Notes"

        ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

        md_path = Path(config.OUTPUT_FOLDER) / f"{safe}_{ts}.md"

        md_path.write_text(markdown, encoding="utf-8")

        result["markdown_path"] = str(md_path)



        if export_to_word:

            docx_name = f"{safe}_{ts}.docx"

            docx_path = self.output.export_to_word(markdown, docx_name, self.book_title)

            if docx_path:

                result["docx"] = docx_path

        return result


