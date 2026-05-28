"""
Fast LLM for Stage 15b (classification + revalidation).

Backend is driven by LLM_PROVIDER (via config.DOUBTED_RESOLVER_LLM).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.modules.pipeline.llm_chat_client import LlmChatClient, normalize_chat_provider

_VALID_CATEGORIES = frozenset({"metadata", "toc", "real_content"})

_CLASSIFY_SYSTEM = """You classify law textbook PDF excerpts.
Categories: metadata (publisher/ISBN/title), toc (index/syllabus/exam Q lists only), real_content (chapter body with law text or cases).
JSON only: {"category":"metadata"|"toc"|"real_content","confidence":0.0-1.0}"""

_REVALIDATE_SYSTEM = """You audit law textbook structure classifications.
Given a draft label (metadata/toc/real_content) and local context, confirm or correct it.
Rules:
1) Integrated chapter openers (Chapter N + chapter questions + topic list) are real_content, NOT toc.
2) Classify as toc only when there is explicit TOC evidence (dot leaders, index-style trailing page numbers,
   or repeated table-of-contents listing format).
3) If heading is exactly "Chapter N" and no explicit TOC evidence exists, choose real_content.

Reply JSON only:
{"category":"metadata"|"toc"|"real_content","confidence":0.0-1.0,"keep_heading":true|false,"reason":"must mention concrete evidence"}"""


def _segment_excerpt(
    heading_text: str,
    lines: List[Dict[str, Any]],
    *,
    max_chars: int = 1800,
) -> str:
    parts: List[str] = []
    if heading_text:
        parts.append(f"Heading: {heading_text.strip()}")
    for line in lines[:30]:
        t = (line.get("text") or "").strip()
        if t:
            pg = line.get("page_number")
            parts.append(f"p{pg}: {t}" if pg else t)
    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[:max_chars] + "\n..."
    return text


def _parse_category_json(raw: str) -> Optional[Tuple[str, float]]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\"category\"[^{}]*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    cat = str(data.get("category", "")).strip().lower()
    if cat not in _VALID_CATEGORIES:
        return None
    try:
        conf = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        conf = 0.7
    return cat, max(0.0, min(1.0, conf))


def _parse_revalidate_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\"category\"[^{}]*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    cat = str(data.get("category", "")).strip().lower()
    if cat not in _VALID_CATEGORIES:
        return None
    try:
        conf = float(data.get("confidence", 0.8))
    except (TypeError, ValueError):
        conf = 0.8
    keep = data.get("keep_heading", True)
    if isinstance(keep, str):
        keep = keep.lower() in ("true", "1", "yes")
    return {
        "category": cat,
        "confidence": max(0.0, min(1.0, conf)),
        "keep_heading": bool(keep),
        "reason": str(data.get("reason", ""))[:200],
    }


class FastSegmentLlm:
    """Small instruct model via the unified LLM provider."""

    def __init__(self, backend: str, *, model_override: str = "") -> None:
        self.backend = normalize_chat_provider(backend)
        self._client = LlmChatClient(
            self.backend,
            model_override=model_override,
            temperature=0.0,
        )

    @property
    def enabled(self) -> bool:
        return self._client.chat_enabled

    def _chat(self, system: str, user: str, *, max_tokens: int = 72) -> Optional[str]:
        return self._client.chat(system=system, user=user, max_tokens=max_tokens)

    def classify(
        self,
        heading_text: str,
        lines: List[Dict[str, Any]],
        *,
        page_start: int = 0,
        page_end: int = 0,
    ) -> Optional[Tuple[str, float]]:
        if not self.enabled:
            return None
        excerpt = _segment_excerpt(heading_text, lines)
        if not excerpt.strip():
            return None
        user = f"Pages {page_start}-{page_end}\n{excerpt}\nCategory?"
        raw = self._chat(_CLASSIFY_SYSTEM, user)
        parsed = _parse_category_json(raw or "")
        return parsed

    def revalidate(
        self,
        *,
        heading_text: str,
        current_label: str,
        current_method: str,
        context_text: str,
        neighbor_headings: List[str],
        page_start: int = 0,
        page_end: int = 0,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        neighbors = "\n".join(f"- {h}" for h in neighbor_headings[:12] if h)
        user = (
            f"Pages {page_start}-{page_end}\n"
            f"Draft: {current_label} (via {current_method})\n"
            f"Heading: {heading_text}\n"
            f"Nearby headings:\n{neighbors or '(none)'}\n\n"
            f"Context:\n{context_text[:2200]}\n\n"
            "Correct category?"
        )
        raw = self._chat(_REVALIDATE_SYSTEM, user, max_tokens=96)
        return _parse_revalidate_json(raw or "")


_classifier: Optional[FastSegmentLlm] = None
_revalidation_classifier: Optional[FastSegmentLlm] = None


def get_segment_llm_classifier() -> FastSegmentLlm:
    global _classifier
    if _classifier is None:
        from src import config

        backend = (config.DOUBTED_RESOLVER_LLM or "off").strip().lower()
        _classifier = FastSegmentLlm(backend)
    return _classifier


def get_revalidation_classifier() -> FastSegmentLlm:
    global _revalidation_classifier
    if _revalidation_classifier is None:
        from src import config

        backend = (config.DOUBTED_RESOLVER_LLM or "off").strip().lower()
        model = (getattr(config, "DOUBTED_REVALIDATION_MODEL", None) or "").strip()
        _revalidation_classifier = FastSegmentLlm(backend, model_override=model)
    return _revalidation_classifier
