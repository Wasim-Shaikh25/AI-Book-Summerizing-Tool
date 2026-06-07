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
from src.modules.generation.rewrite_prompts import is_exam_oriented_mode, rewrite_system_prompt

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

    ) -> str:

        work = sections[:max_sections] if max_sections > 0 else sections

        cap = max_source_chars or int(getattr(config, "ULTIMATE_MAX_REWRITE_SECTION_CHARS", 6000) or 6000)

        exam_oriented = is_exam_oriented_mode()
        system = rewrite_system_prompt(exam_oriented=exam_oriented)
        workers = resolve_parallel_workers()
        overlap = resolve_context_overlap_chars()

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



        cap = max_sections or int(config.FULL_REWRITE_MAX_CHUNKS or 0)

        markdown = self.rewrite_sections(

            sections,

            user_instruction=user_instruction,

            max_sections=cap,

            chapter_hierarchy=chapter_hierarchy,

            source_pdf=Path(pdf_path).name if pdf_path else "",

        )

        if not markdown or markdown.count("\n") < 2:

            return {"error": "Note generation produced no content (check LLM_PROVIDER / API keys)."}



        result: Dict[str, Any] = {

            "markdown": markdown,

            "section_count": len(sections[:cap] if cap > 0 else sections),

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


